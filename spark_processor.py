import os
import sys
import json
import re
import html
from datetime import datetime, timezone
import pandas as pd
import torch

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, udf
from pyspark.sql.types import StructType, StructField, StringType, ArrayType

# --- CPU OPTIMIZATION & WORKER-SAFE MODEL LOADER ---
# Limit torch CPU threads per Spark worker to keep execution lightweight
torch.set_num_threads(2)

_domain_clf = None
_gliner = None
_sentiment = None

def get_models():
    """Lazy worker-safe model loader for lightweight CPU inference."""
    global _domain_clf, _gliner, _sentiment
    if _domain_clf is None:
        from transformers import pipeline
        from gliner import GLiNER
        
        print("[AI Engine] Initializing lightweight CPU AI models on Spark worker...")
        # Lightweight zero-shot domain classifier
        _domain_clf = pipeline(
            "zero-shot-classification",
            model="cross-encoder/nli-deberta-v3-small",
            device=-1  # Force CPU
        )
        # Lightweight entity extraction model
        _gliner = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
        # Lightweight sentiment classifier
        _sentiment = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            device=-1  # Force CPU
        )
    return _domain_clf, _gliner, _sentiment

import yaml

# --- DOMAIN CONFIGURATION & BROADCAST MAPPING ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "domain_config.yaml")
DOMAIN_CONFIG = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'r') as f:
            loaded_cfg = yaml.safe_load(f)
            DOMAIN_CONFIG = loaded_cfg.get('domains', {}) if loaded_cfg else {}
    except Exception as e:
        print(f"[Warning] Error reading domain_config.yaml: {e}")

# Fallback defaults for Influencer Promotion & Sponsorship Analysis
DEFAULT_DOMAINS = ["Tech_Creators", "Beauty_Lifestyle", "Fitness_Health", "Finance_Crypto", "Gaming_Entertainment"]
DOMAINS = list(DOMAIN_CONFIG.keys()) if DOMAIN_CONFIG else DEFAULT_DOMAINS

def _sanitize_keywords(kws):
    return [str(w).lower().strip() for w in kws if w and str(w).strip()]

TECH_KEYWORDS = _sanitize_keywords(DOMAIN_CONFIG.get("Tech_Creators", {}).get("keywords", [
    "mkbhd", "marques", "linus", "ltt", "mrwhosetheboss", "unbox therapy", "dave2d", "dbrand", "casetify", "ridge"
]))

BEAUTY_KEYWORDS = _sanitize_keywords(DOMAIN_CONFIG.get("Beauty_Lifestyle", {}).get("keywords", [
    "mikayla", "james charles", "jeffree star", "alix earle", "makeup", "skincare", "mascara", "bloom", "sephora"
]))

FITNESS_KEYWORDS = _sanitize_keywords(DOMAIN_CONFIG.get("Fitness_Health", {}).get("keywords", [
    "huberman", "liver king", "cbum", "athlean", "supplement", "ag1", "athletic greens", "protein", "gymshark"
]))

FINANCE_KEYWORDS = _sanitize_keywords(DOMAIN_CONFIG.get("Finance_Crypto", {}).get("keywords", [
    "coffeezilla", "graham stephan", "andrei jikh", "crypto", "ftx", "scam", "finfluencer", "rugpull", "robinhood"
]))

GAMING_KEYWORDS = _sanitize_keywords(DOMAIN_CONFIG.get("Gaming_Entertainment", {}).get("keywords", [
    "mrbeast", "feastables", "lunchly", "logan paul", "prime", "kai cenat", "pewdiepie", "betterhelp", "gfuel"
]))

KNOWN_INFLUENCERS = [
    "MKBHD", "Mrwhosetheboss", "Linus Tech Tips", "Dave2D", "Unbox Therapy",
    "Mikayla Nogueira", "Jeffree Star", "Alix Earle", "Emma Chamberlain", "James Charles",
    "Andrew Huberman", "Liver King", "Chris Bumstead", "Athlean-X", "Jeff Nippard",
    "Coffeezilla", "Graham Stephan", "Andrei Jikh", "Meet Kevin", "Ali Abdaal",
    "MrBeast", "Logan Paul", "KSI", "Kai Cenat", "PewDiePie", "Penguinz0"
]

KNOWN_BRANDS = [
    "Feastables", "Lunchly", "Prime Energy", "AG1", "Athletic Greens", "dbrand", "Casetify",
    "Ridge Wallet", "BetterHelp", "NordVPN", "Bloom Nutrition", "Raw Nutrition", "Gymshark",
    "FTX", "BlockFi", "L'Oreal", "Raycon", "CryptoZoo", "Sephora"
]

nlp_schema = StructType([
    StructField("domain", StringType(), True),
    StructField("sentiment", StringType(), True),
    StructField("entities", ArrayType(StringType()), True),
    StructField("aspect_sentiments", ArrayType(StringType()), True)
])

def extract_aspect_sentiments(text, entities, sentiment_clf):
    """
    Lightweight Aspect-Based Sentiment Analysis (ABSA).
    Links extracted entities with specific context-level sentiments (e.g. 'camera -> POSITIVE').
    Uses clause/sentence segmentation with sentiment caching for optimal CPU efficiency.
    """
    if not text or not entities:
        return []
    
    # Split text into distinct clauses by punctuation and contrastive conjunctions
    clauses = [
        c.strip() for c in re.split(
            r'[.!?,;\n]+|\b(?:but|however|although|yet|while|though|except)\b',
            text,
            flags=re.IGNORECASE
        ) if len(c.strip()) > 2
    ]
    
    clause_cache = {}
    aspect_results = []
    
    for entity in entities:
        if not entity or not entity.strip():
            continue
        ent_lower = entity.lower().strip()
        
        # 1. Match entity to its specific clause
        matching_clause = None
        for c in clauses:
            if ent_lower in c.lower():
                matching_clause = c
                break
        
        # 2. Fallback to a +/- 8 word local context window around the entity
        if not matching_clause:
            words = text.split()
            for idx, w in enumerate(words):
                if ent_lower in w.lower():
                    start_idx = max(0, idx - 8)
                    end_idx = min(len(words), idx + 9)
                    matching_clause = " ".join(words[start_idx:end_idx])
                    break
        
        target_context = matching_clause if matching_clause else text
        target_context = target_context[:256]  # Truncate context for fast CPU pass
        
        # 3. Evaluate sentiment with clause-level caching
        if target_context not in clause_cache:
            with torch.inference_mode():
                pred = sentiment_clf(target_context)[0]
                clause_cache[target_context] = pred['label'].upper()
        
        aspect_polarity = clause_cache[target_context]
        aspect_results.append(f"{entity} -> {aspect_polarity}")
        
    return aspect_results

@udf(returnType=nlp_schema)
def process_nlp(text):
    """
    PySpark UDF executing end-to-end NLP enrichment:
    1. Fast Domain Routing
    2. Dynamic Domain Entity Extraction
    3. Global Sentiment Analysis
    4. Aspect-Based Sentiment Tagging (ABSA)
    """
    if text is None or not isinstance(text, str) or not text.strip():
        return {
            "domain": "Unknown",
            "sentiment": "Neutral",
            "entities": [],
            "aspect_sentiments": []
        }
    
    try:
        clean_text = html.unescape(text).strip()
        lower_text = clean_text.lower()
        
        # 1. Domain Routing via Influencer Category Keyword Score Matching
        domain_scores = {
            "Tech_Creators": sum(1 for w in TECH_KEYWORDS if w in lower_text),
            "Beauty_Lifestyle": sum(1 for w in BEAUTY_KEYWORDS if w in lower_text),
            "Fitness_Health": sum(1 for w in FITNESS_KEYWORDS if w in lower_text),
            "Finance_Crypto": sum(1 for w in FINANCE_KEYWORDS if w in lower_text),
            "Gaming_Entertainment": sum(1 for w in GAMING_KEYWORDS if w in lower_text)
        }
        best_domain = max(domain_scores, key=domain_scores.get)
        if domain_scores[best_domain] > 0:
            predicted_domain = best_domain
        else:
            predicted_domain = "Tech_Creators"
        
        # 2. Domain-Conditioned Entity Extraction with GLiNER + Influencer & Brand Matching
        domain_clf, gliner, sentiment_clf = get_models()
        entity_labels = DOMAIN_CONFIG.get(predicted_domain, {}).get(
            "entity_labels", ["Influencer", "Product", "Brand", "Sponsor", "Verdict"]
        )
            
        with torch.inference_mode():
            entities_extracted = gliner.predict_entities(clean_text[:384], entity_labels, threshold=0.3)
        
        extracted_names = [
            e['text'].strip() for e in entities_extracted 
            if len(e['text'].strip()) >= 2 and not e['text'].strip().isnumeric()
        ]
        
        # Check known influencers and brands
        for inf in KNOWN_INFLUENCERS:
            if inf.lower() in lower_text and inf not in extracted_names:
                extracted_names.append(inf)
        for br in KNOWN_BRANDS:
            if br.lower() in lower_text and br not in extracted_names:
                extracted_names.append(br)
                
        entity_list = list(set(extracted_names))
        
        # 3. Overall Comment Sentiment Analysis
        with torch.inference_mode():
            sentiment_res = sentiment_clf(clean_text[:384])[0]
            sentiment = sentiment_res['label'].upper()
        
        # 4. Aspect-Based Sentiment Tagging (ABSA)
        aspect_sentiments = extract_aspect_sentiments(clean_text, entity_list, sentiment_clf)
        
        return {
            "domain": predicted_domain,
            "sentiment": sentiment,
            "entities": entity_list,
            "aspect_sentiments": aspect_sentiments
        }
    except Exception as e:
        print(f"[!] NLP UDF Processing Warning: {e}")
        return {
            "domain": "Unknown",
            "sentiment": "Neutral",
            "entities": [],
            "aspect_sentiments": []
        }

# --- POWER BI CONTINUOUS EXPORT ROUTINE ---
EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "powerbi_export"))
os.makedirs(EXPORT_DIR, exist_ok=True)
MASTER_DATA_PATH = os.path.join(EXPORT_DIR, "master_stream_history.parquet")

def atomic_export_df(df_to_save, base_name):
    """Atomically write CSV and Parquet files for lock-free Power BI ingestion."""
    csv_path = os.path.join(EXPORT_DIR, f"{base_name}.csv")
    parquet_path = os.path.join(EXPORT_DIR, f"{base_name}.parquet")
    
    # Save CSV atomically
    temp_csv = csv_path + ".tmp"
    df_to_save.to_csv(temp_csv, index=False, encoding='utf-8')
    os.replace(temp_csv, csv_path)
    
    # Save Parquet atomically
    try:
        temp_parquet = parquet_path + ".tmp"
        df_to_save.to_parquet(temp_parquet, index=False)
        os.replace(temp_parquet, parquet_path)
    except Exception as pe:
        pass

def export_powerbi_tables(batch_pandas_df):
    """
    Consolidates streaming batches and exports summary tables for Power BI:
    1. aspect_analytics (Aspect, Sentiment, Mentions, Positive%, Negative%)
    2. sentiment_summary (Domain & Overall Sentiment aggregations)
    3. live_feed_summary (Flattened live stream with aspect tags)
    4. kpi_summary (Single-row scorecard metrics)
    """
    if batch_pandas_df.empty:
        return
    
    # Update master history table
    if os.path.exists(MASTER_DATA_PATH):
        try:
            existing_df = pd.read_parquet(MASTER_DATA_PATH)
            combined_df = pd.concat([existing_df, batch_pandas_df], ignore_index=True)
            # Deduplicate by video_id, timestamp, and text
            combined_df = combined_df.drop_duplicates(subset=['video_id', 'timestamp', 'text'])
        except Exception:
            combined_df = batch_pandas_df
    else:
        combined_df = batch_pandas_df
    
    # Keep master history bounded (e.g. last 10,000 records for performance)
    if len(combined_df) > 10000:
        combined_df = combined_df.tail(10000)
    
    combined_df.to_parquet(MASTER_DATA_PATH, index=False)
    
    # 1. LIVE FEED SUMMARY TABLE
    live_feed = combined_df.copy()
    live_feed['aspect_tags'] = live_feed['aspect_sentiments'].apply(
        lambda tags: " | ".join(tags) if isinstance(tags, (list, tuple)) and len(tags) > 0 else "None"
    )
    live_feed['entities_list'] = live_feed['entities'].apply(
        lambda ents: ", ".join(ents) if isinstance(ents, (list, tuple)) and len(ents) > 0 else "None"
    )
    live_feed_export = live_feed[['timestamp', 'platform', 'video_id', 'domain', 'sentiment', 'aspect_tags', 'entities_list', 'text']]
    atomic_export_df(live_feed_export, "live_feed_summary")
    
    # 2. ASPECT ANALYTICS SUMMARY TABLE (ABSA Aggregations)
    aspect_records = []
    for _, row in combined_df.iterrows():
        domain = row.get('domain', 'Unknown')
        timestamp = row.get('timestamp', '')
        tags = row.get('aspect_sentiments', [])
        if isinstance(tags, (list, tuple)):
            for tag in tags:
                if " -> " in tag:
                    parts = tag.split(" -> ")
                    aspect_records.append({
                        "aspect": parts[0].strip(),
                        "aspect_sentiment": parts[1].strip(),
                        "domain": domain,
                        "timestamp": timestamp
                    })
    
    if aspect_records:
        aspect_df = pd.DataFrame(aspect_records)
        
        # Group by Aspect, Domain, and Sentiment
        aspect_grouped = aspect_df.groupby(['aspect', 'domain']).agg(
            total_mentions=('aspect_sentiment', 'count'),
            positive_mentions=('aspect_sentiment', lambda s: (s == 'POSITIVE').sum()),
            negative_mentions=('aspect_sentiment', lambda s: (s == 'NEGATIVE').sum()),
            latest_timestamp=('timestamp', 'max')
        ).reset_index()
        
        aspect_grouped['positive_rate_pct'] = (
            (aspect_grouped['positive_mentions'] / aspect_grouped['total_mentions']) * 100
        ).round(1)
        aspect_grouped['negative_rate_pct'] = (
            (aspect_grouped['negative_mentions'] / aspect_grouped['total_mentions']) * 100
        ).round(1)
        aspect_grouped['net_sentiment_score'] = (
            aspect_grouped['positive_rate_pct'] - aspect_grouped['negative_rate_pct']
        ).round(1)
        
        aspect_grouped = aspect_grouped.sort_values(by='total_mentions', ascending=False)
        atomic_export_df(aspect_grouped, "aspect_analytics")
    
    # 3. DOMAIN SENTIMENT SUMMARY TABLE
    domain_summary = combined_df.groupby(['domain', 'sentiment']).agg(
        event_count=('text', 'count'),
        latest_event=('timestamp', 'max')
    ).reset_index()
    
    domain_totals = combined_df.groupby('domain')['text'].count().reset_index().rename(columns={'text': 'domain_total'})
    domain_summary = pd.merge(domain_summary, domain_totals, on='domain')
    domain_summary['percentage_share'] = ((domain_summary['event_count'] / domain_summary['domain_total']) * 100).round(1)
    atomic_export_df(domain_summary, "sentiment_summary")
    
    # 4. EXECUTIVE KPI SUMMARY TABLE (Single Row for Power BI Cards)
    total_comments = len(combined_df)
    pos_count = (combined_df['sentiment'] == 'POSITIVE').sum()
    pos_rate = round((pos_count / total_comments * 100), 1) if total_comments > 0 else 0.0
    top_domain = combined_df['domain'].value_counts().index[0] if not combined_df.empty else "N/A"
    
    top_pos_aspect = "N/A"
    top_neg_aspect = "N/A"
    if aspect_records:
        pos_aspects = [r['aspect'] for r in aspect_records if r['aspect_sentiment'] == 'POSITIVE']
        neg_aspects = [r['aspect'] for r in aspect_records if r['aspect_sentiment'] == 'NEGATIVE']
        if pos_aspects:
            top_pos_aspect = pd.Series(pos_aspects).value_counts().index[0]
        if neg_aspects:
            top_neg_aspect = pd.Series(neg_aspects).value_counts().index[0]
            
    kpi_df = pd.DataFrame([{
        "total_comments": total_comments,
        "positive_sentiment_rate_pct": pos_rate,
        "active_domain": top_domain,
        "top_positive_aspect": top_pos_aspect,
        "top_negative_aspect": top_neg_aspect,
        "last_refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }])
    atomic_export_df(kpi_df, "kpi_summary")
    
    # 5. INFLUENCER LEADERBOARD TABLE (Category-wise Rankings)
    influencer_records = []
    for _, row in combined_df.iterrows():
        domain_val = row.get('domain', 'Unknown')
        sent_val = row.get('sentiment', 'Neutral')
        ents = row.get('entities', [])
        if not isinstance(ents, list):
            ents = []
        for ent in ents:
            ent_str = str(ent).strip()
            for inf in KNOWN_INFLUENCERS:
                if inf.lower() in ent_str.lower():
                    influencer_records.append({
                        "influencer": inf,
                        "category": domain_val,
                        "sentiment": sent_val
                    })
                    break
    if influencer_records:
        inf_df = pd.DataFrame(influencer_records)
        inf_grouped = inf_df.groupby(['influencer', 'category']).agg(
            total_reviews=('sentiment', 'count'),
            good_promotions=('sentiment', lambda s: (s == 'POSITIVE').sum()),
            wrong_promotions=('sentiment', lambda s: (s == 'NEGATIVE').sum())
        ).reset_index()
        inf_grouped['good_rate_pct'] = ((inf_grouped['good_promotions'] / inf_grouped['total_reviews']) * 100).round(1)
        inf_grouped['wrong_rate_pct'] = ((inf_grouped['wrong_promotions'] / inf_grouped['total_reviews']) * 100).round(1)
        inf_grouped['net_trust_score'] = (inf_grouped['good_rate_pct'] - inf_grouped['wrong_rate_pct']).round(1)
        inf_grouped['verdict'] = inf_grouped['net_trust_score'].apply(
            lambda s: "🟢 High Trust" if s >= 20 else ("🟡 Mixed / Biased" if s >= -20 else "🔴 High Sellout / Scam Risk")
        )
        inf_grouped = inf_grouped.sort_values(by=['category', 'total_reviews'], ascending=[True, False])
        atomic_export_df(inf_grouped, "influencer_leaderboard")
    
    print(f"[Power BI Export] Refreshed Power BI tables ({total_comments} cumulative events) -> {EXPORT_DIR}")

# --- SPARK STREAMING MICRO-BATCH PROCESSOR ---
def process_micro_batch(batch_df, batch_id):
    """
    Spark micro-batch execution:
    1. Writes raw batch to HDFS (with local data lake fallback)
    2. Executes continuous Power BI summary export
    """
    if batch_df.isEmpty():
        return
    
    record_count = batch_df.count()
    print(f"\n[Spark Batch {batch_id}] Processing {record_count} incoming social events...")
    
    # 1. Persist to HDFS Datalake (Preserving HDFS configuration)
    hdfs_path = "hdfs://localhost:8020/user/bda/datalake/"
    try:
        batch_df.write \
            .mode("append") \
            .format("parquet") \
            .save(hdfs_path)
        print(f"[HDFS] Wrote batch {batch_id} to {hdfs_path}")
    except Exception as hdfs_err:
        print(f"[HDFS Warning] HDFS cluster unavailable ({hdfs_err}). Saving to local datalake backup...")
        local_datalake = os.path.abspath(os.path.join(os.path.dirname(__file__), "datalake", "social_events.parquet"))
        os.makedirs(os.path.dirname(local_datalake), exist_ok=True)
        batch_df.write \
            .mode("append") \
            .format("parquet") \
            .save(local_datalake)
    
    # 2. Continuous Power BI Consolidated Export
    try:
        pandas_batch = batch_df.toPandas()
        export_powerbi_tables(pandas_batch)
    except Exception as pbi_err:
        print(f"[Power BI Export Warning] Error exporting Power BI summary: {pbi_err}")

# --- SPARK STREAMING ENGINE SETUP ---
if __name__ == "__main__":
    print("=" * 60)
    print(" Starting Spark Streaming AI & Aspect Sentiment Engine")
    print(" Target Kafka: localhost:9092 | Topic: raw-social")
    print(" Target HDFS : hdfs://localhost:8020/user/bda/datalake/")
    print(f" Power BI Out: {EXPORT_DIR}")
    print("=" * 60)
    
    spark = SparkSession.builder \
        .appName("BDA_Hadoop_Spark_ABSA_Pipeline") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1") \
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true") \
        .config("spark.ui.enabled", "false") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    
    kafka_schema = StructType([
        StructField("platform", StringType(), True),
        StructField("video_id", StringType(), True),
        StructField("timestamp", StringType(), True),
        StructField("text", StringType(), True)
    ])
    
    # Read from Kafka topic 'raw-social'
    df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("subscribe", "raw-social") \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()
    
    # Parse Kafka JSON payload
    parsed_df = df.select(
        from_json(col("value").cast("string"), kafka_schema).alias("data")
    ).select("data.*")
    
    # Filter out null or blank comments at the Spark DataFrame layer
    valid_comments_df = parsed_df.filter(
        col("text").isNotNull() & (col("text") != "")
    )
    
    # Apply Aspect-Based Sentiment & Domain Enrichment UDF
    enriched_df = valid_comments_df.withColumn("nlp_results", process_nlp(col("text")))
    
    final_df = enriched_df.select(
        col("timestamp"),
        col("platform"),
        col("video_id"),
        col("text"),
        col("nlp_results.domain").alias("domain"),
        col("nlp_results.sentiment").alias("sentiment"),
        col("nlp_results.entities").alias("entities"),
        col("nlp_results.aspect_sentiments").alias("aspect_sentiments")
    )
    
    checkpoint_dir = "/tmp/spark_checkpoints_influencer"
    if os.path.exists(checkpoint_dir):
        import shutil
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    # Structured streaming query using foreachBatch for dual HDFS + Power BI output
    query = final_df.writeStream \
        .foreachBatch(process_micro_batch) \
        .option("checkpointLocation", checkpoint_dir) \
        .start()
    
    try:
        query.awaitTermination()
    except KeyboardInterrupt:
        print("\n[!] Spark Streaming pipeline gracefully stopped by user.")