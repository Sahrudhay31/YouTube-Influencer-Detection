# 🚀 Big Data Analytics: Real-Time Social Media Influencer Promotion & Sponsorship Intelligence Pipeline

An end-to-end Big Data Analytics and Natural Language Processing (NLP) streaming architecture that monitors and evaluates social media influencer product promotions, brand deals, and sponsorships across multiple categories (Tech Creators, Beauty & Lifestyle, Fitness & Health, Finance & Crypto, Gaming & Entertainment) in real time.

The system determines whether audience perception of influencer promotions is **Good (Authentic, Honest, Recommended)** or **Wrong (Deceptive, Sellout, Scam Risk)** using Aspect-Based Sentiment Analysis (ABSA) and named entity recognition.

---

## 🏗️ Architecture Overview

```
[ YouTube Data API v3 ]
          │
          ▼
[ Producer (youtube_producer.py) ]
          │  (JSON Streams)
          ▼
[ Apache Kafka (raw-social topic) ]
          │
          ▼
[ Apache Spark Structured Streaming (spark_processor.py) ]
    ├─ Domain-Adaptive Classification (5 Influencer Categories)
    ├─ GLiNER Zero-Shot & Dictionary Named Entity Extraction
    ├─ DistilBERT Sentiment Classification
    └─ Clause-Level Aspect-Based Sentiment Analysis (ABSA)
          │
    ┌─────┴─────────────────────────────────┐
    ▼                                       ▼
[ Apache Hadoop HDFS ]            [ Power BI Live Exports ]
hdfs://localhost:8020/user/bda/datalake/    powerbi_export/*.csv & *.parquet
                                            │
                                            ▼
                               [ Streamlit Analytics Dashboard ]
                                    (http://localhost:8501)
```

---

## 📦 Tech Stack

- **Data Ingestion**: Python `google-api-python-client`, `kafka-python`
- **Message Broker**: Apache Kafka & Apache Zookeeper (Docker)
- **Stream Processing**: Apache Spark 3.5.1 (PySpark Structured Streaming)
- **Distributed Storage**: Apache Hadoop 3.2.1 HDFS (`hdfs://localhost:8020/user/bda/datalake/`)
- **AI & NLP**: HuggingFace Transformers (`distilbert-base-uncased-finetuned-sst-2-english`), `gliner`
- **Dashboard & UI**: Streamlit, Plotly Express
- **Reporting**: Automated continuous Power BI data sync (`powerbi_export/`)

---

## 📊 Influencer Taxonomy

| Category | Top Tracked Creators & Influencers | Promoted Brands & Topics |
| :--- | :--- | :--- |
| **Tech Creators** | MKBHD, Linus Tech Tips, Mrwhosetheboss, Dave2D, Unbox Therapy | dbrand, Casetify, Ridge Wallet, Apple, Samsung |
| **Beauty & Lifestyle** | Mikayla Nogueira, Jeffree Star, Alix Earle, Emma Chamberlain | L'Oreal, Bloom Nutrition, Sephora, Glow Recipe |
| **Fitness & Health** | Andrew Huberman, Liver King, Chris Bumstead, Athlean-X | AG1 (Athletic Greens), Gymshark, Raw Nutrition |
| **Finance & Crypto** | Coffeezilla, Graham Stephan, Andrei Jikh, Meet Kevin | FTX, BlockFi, Crypto schemes, Finfluencer courses |
| **Gaming & Entertainment** | MrBeast, Logan Paul, KSI, Kai Cenat, PewDiePie | Feastables, Lunchly, Prime Energy, BetterHelp |

---

## 🛠️ Setup & Running

### 1. Start Infrastructure (Hadoop & Kafka)
```bash
docker compose up -d
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Streaming Pipeline

In separate terminal sessions:

1. **Start the YouTube Producer**:
   ```bash
   python3 youtube_producer.py
   ```

2. **Start the Spark Streaming & AI ABSA Engine**:
   ```bash
   python3 spark_processor.py
   ```

3. **Launch the Real-Time Streamlit Dashboard**:
   ```bash
   streamlit run dashboard.py
   ```

---

## 📈 Power BI Integration
CSV and Parquet datasets are exported automatically on each micro-batch to `powerbi_export/`:
- `influencer_leaderboard.csv`: Category rankings, trust score, and promotional verdict
- `aspect_analytics.csv`: Granular aspect-level sentiment breakdown
- `sentiment_summary.csv`: Aggregated category distribution
- `live_feed_summary.csv`: Rolling feed of analyzed comments
- `kpi_summary.csv`: High-level metrics for Power BI KPI cards
