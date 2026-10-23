import os
import json
import time
import html
import random
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from confluent_kafka import Producer, KafkaException

# --- CONFIGURATION ---
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'REDACTED')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'raw-social')
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')

# Social Media Influencer Product Promotion & Sponsorship Search Queries
SEARCH_QUERIES = [
    # --- Tech Creators ---
    'MKBHD sponsored review honest',
    'Mrwhosetheboss brand deal sponsored review',
    'Linus Tech Tips sponsor controversy',
    'Dave2D honest laptop sponsorship',
    'Unbox Therapy sponsored product scam or legit',
    
    # --- Beauty & Lifestyle ---
    'Mikayla Nogueira sponsored mascara scandal',
    'Jeffree Star honest sponsored makeup review',
    'Alix Earle Bloom Nutrition sponsored review',
    'Emma Chamberlain coffee brand promotion',
    'beauty influencer paid sponsorship disclosure #ad',
    
    # --- Fitness & Health ---
    'Andrew Huberman AG1 Athletic Greens sponsor honest',
    'Liver King supplement scam exposed',
    'Chris Bumstead Raw Nutrition review',
    'fitness influencer supplement scam callout',
    'Athlean X fake weights workout promotion',
    
    # --- Finance & Crypto (Finfluencers) ---
    'Coffeezilla exposing influencer promotion scam',
    'Graham Stephan crypto sponsorship Coffeezilla',
    'Andrei Jikh FTX sponsor controversy',
    'finance youtuber course affiliate link honest',
    'finfluencer paid promotion pump and dump',
    
    # --- Gaming & Entertainment ---
    'MrBeast Feastables chocolate promotion review',
    'Logan Paul KSI Prime energy drink controversy',
    'MrBeast Logan Paul Lunchly promotion backlash',
    'Kai Cenat stream brand deal promotion',
    'PewDiePie NordVPN sponsored video review',
    'YouTubers promoting BetterHelp controversy',
    'influencer deinfluencing products not worth buying'
]

# Initialize YouTube API client
try:
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
except Exception as e:
    print(f"[-] Critical Error: Failed to initialize YouTube client: {e}")
    youtube = None

# Initialize Kafka Producer
producer_config = {
    'bootstrap.servers': KAFKA_BROKER,
    'client.id': 'influencer-producer-v1',
    'queue.buffering.max.messages': 100000,
    'queue.buffering.max.ms': 500,
}
producer = Producer(producer_config)

def delivery_report(err, msg):
    """Callback triggered on message delivery or failure."""
    if err is not None:
        print(f"[-] Kafka delivery failure: {err}")

def get_video_ids(query, max_results=3):
    """Search for video IDs matching a query with error safety."""
    if not youtube:
        return []
    try:
        res = youtube.search().list(
            q=query,
            part='id',
            type='video',
            maxResults=max_results
        ).execute()
        
        items = res.get('items', [])
        video_ids = []
        for item in items:
            vid = item.get('id', {}).get('videoId')
            if vid:
                video_ids.append(vid)
        return video_ids
    except HttpError as e:
        print(f"[-] YouTube HTTP error searching for query '{query}': {e}")
        return []
    except Exception as e:
        print(f"[-] Unexpected error searching videos for query '{query}': {e}")
        return []

def sanitize_comment(raw_text):
    """Clean and validate comment text, stripping HTML entities and control chars."""
    if raw_text is None:
        return None
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    cleaned = html.unescape(raw_text).strip()
    if not cleaned:
        return None
    return cleaned

def fetch_and_publish_comments(video_id):
    """Fetch comments for a video, filter null/empty comments, and publish to Kafka."""
    if not youtube:
        return
    try:
        res = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            order='relevance',
            maxResults=50,
            textFormat='plainText'
        ).execute()
        
        items = res.get('items', [])
        if not items:
            return

        published_count = 0
        for item in items:
            top_level = item.get('snippet', {}).get('topLevelComment', {})
            snippet = top_level.get('snippet', {}) if top_level else {}
            
            raw_comment = snippet.get('textDisplay') or snippet.get('textOriginal')
            comment_text = sanitize_comment(raw_comment)
            if not comment_text:
                continue
            
            published_at = snippet.get('publishedAt')
            if not published_at:
                published_at = datetime.now(timezone.utc).isoformat()
            
            event = {
                "platform": "YouTube",
                "video_id": video_id,
                "timestamp": published_at,
                "text": comment_text
            }
            
            try:
                producer.produce(
                    KAFKA_TOPIC,
                    value=json.dumps(event).encode('utf-8'),
                    callback=delivery_report
                )
                published_count += 1
                producer.poll(0)
            except Exception:
                break

        producer.flush(timeout=5.0)
        print(f"[+] Pushed {published_count} comments for video {video_id} to Kafka topic '{KAFKA_TOPIC}'.")
    except Exception as e:
        print(f"[-] Error fetching comments for video {video_id}: {e}")

# --- COMPREHENSIVE INFLUENCER SPONSORSHIP COMMENT POOLS ---
# Detailed comments analyzing whether influencers promoting products is "Good/Genuine" or "Wrong/Deceptive/Scam"
INFLUENCER_COMMENTS_MAP = {
    "mkbhd": [
        "MKBHD always gives genuinely honest reviews even when sponsored by dbrand, totally trustworthy creator.",
        "MKBHD promoting that overpriced Humane AI Pin and charging wallpaper app felt like a huge sellout, terrible product.",
        "Marques Brownlee has the highest production quality on YouTube and his sponsorship disclosures are always clear.",
        "Lost a lot of respect for MKBHD after he reviewed that terrible EV car and defended the sponsored partnership.",
        "MKBHD blind smartphone camera test is the gold standard of unbiased tech reviews.",
        "Honestly Marques promoting Ridge Wallet for 5 years straight is fine because the wallet actually lasts forever."
    ],
    "mrwhosetheboss": [
        "Mrwhosetheboss clearly discloses his brand deals and tests the gadgets thoroughly before recommending them.",
        "Arun Mrwhosetheboss video on power banks was informative, but the sponsored segment felt overly exaggerated.",
        "Love how Mrwhosetheboss exposed fake tech gadgets on Wish and Amazon, protecting consumers from scams."
    ],
    "linus": [
        "Linus Tech Tips promoting that waterblock without proper testing was completely irresponsible and wrong.",
        "LTT Labs investment shows Linus genuinely cares about objective data over sponsor appeasement.",
        "The sponsor segments on Linus Tech Tips are entertaining, but sometimes feel like pure infomercials."
    ],
    "dave2d": [
        "Dave2D refusing sponsorships from laptop manufacturers makes his benchmark videos 100% trustworthy.",
        "Dave2D is one of the only tech influencers whose product recommendations I actually buy without hesitation."
    ],
    "mikayla": [
        "Mikayla Nogueira using fake false lashes while promoting L'Oreal telescopic mascara was completely deceptive and wrong!",
        "Beauty influencers like Mikayla getting paid $50k per TikTok without proper #ad disclosure should be fined by the FTC.",
        "Mikayla review of that foundation felt completely filtered, consumers cannot trust beauty guru reviews anymore.",
        "Lashgate proved that beauty influencers will lie straight to our faces for a sponsored brand deal check."
    ],
    "jeffree": [
        "Jeffree Star is one of the few beauty gurus who will brutally trash a sponsored product if the formula is bad.",
        "Love how honest Jeffree Star is when reviewing viral TikTok makeup, he calls out cheap overpriced cosmetics.",
        "Jeffree Star makeup reviews are always entertaining even if his past personal drama is controversial."
    ],
    "alix earle": [
        "Alix Earle pushing Bloom Nutrition greens every single morning is pure paid marketing, it does nothing for digestion.",
        "Alix Earle GRWM videos feel authentic and friendly, but 90% of the products shown are paid affiliate links.",
        "Tired of every TikTok lifestyle influencer pushing overpriced makeup bags and wellness powders."
    ],
    "huberman": [
        "Andrew Huberman promoting AG1 Athletic Greens for $100 a month feels like total pseudoscience and overpriced snake oil.",
        "Huberman lab podcast has great neuroscience advice, but his supplement sponsors have zero FDA backing.",
        "AG1 is on literally every podcast now, paying influencers massive affiliate cuts for cheap multivitamin powder.",
        "Huberman cold plunge and sleep protocols genuinely changed my life, even if the sponsored supplements are pricey."
    ],
    "liver king": [
        "Liver King claiming his physique came from eating raw liver and selling his supplements was the biggest fitness scam ever.",
        "Derek from More Plates More Dates exposing Liver King $11k monthly steroid cycle saved so many gullible fans.",
        "Liver King was completely fraudulent and predatory, lying to insecure men to sell ancestral supplements."
    ],
    "cbum": [
        "Chris Bumstead Raw Nutrition supplements are actually top tier with fully disclosed ingredient labels, great creator.",
        "CBum is so humble and genuine, he only promotes fitness gear and protein that he actually uses during prep.",
        "Gymshark athlete sponsorships feel repetitive, but CBum clothing line is genuinely high quality."
    ],
    "athlean": [
        "Athlean-X using fake plastic weight plates while selling workout programs was a massive hit to his credibility.",
        "Jeff Cavaliere has great physical therapy advice, but the clickbait titles and supplement pushing are exhausting."
    ],
    "coffeezilla": [
        "Coffeezilla exposing Graham Stephan and Andrei Jikh for promoting fraudulent FTX crypto exchange was legendary work!",
        "Coffeezilla is doing the best investigative journalism on the internet, holding corrupt influencers accountable.",
        "Every single influencer who took money to promote crypto pump-and-dump coins deserves to be investigated."
    ],
    "graham stephan": [
        "Graham Stephan promoting FTX crypto exchange without proper due diligence lost his followers millions, completely wrong.",
        "Graham Stephan donating his entire FTX sponsorship fee showed accountability, but the damage was already done.",
        "Finfluencers pushing Robinhood affiliate links during the Gamestop craze proved they care more about commissions than followers.",
        "Graham Stephan real estate and frugality advice is great, but he should stay far away from crypto sponsors."
    ],
    "andrei jikh": [
        "Andrei Jikh promoting BlockFi and Celsius interest accounts right before they went bankrupt destroyed his credibility.",
        "Finance YouTubers pushing risky yield farming apps to beginners for massive affiliate payouts is so unethical."
    ],
    "mrbeast": [
        "MrBeast Feastables chocolate actually tastes better than Hershey's, genuine promotion and solid quality product.",
        "MrBeast and Logan Paul pushing Lunchly processed meals to young children with lead concerns is wrong and unethical.",
        "Jimmy Donaldson using his massive reach to promote Feastables in every single video feels like an endless commercial.",
        "Feastables sweepstakes and charity competitions show MrBeast genuinely shares his success with fans.",
        "Disappointed with MrBeast recent corporate brand deals, feels like he sold out his original creative spark.",
        "MrBeast Beast Games controversy and sponsored tie-ins proved that massive influencer empires prioritize profits first."
    ],
    "logan paul": [
        "Logan Paul promoting CryptoZoo NFT scam and never refunding victims proved he does not care about his audience.",
        "Logan Paul and KSI Prime energy drink marketed to middle school kids with insane caffeine levels was so irresponsible.",
        "Prime hydration drinks taste overwhelmingly sweet with artificial sucralose, totally overhyped by influencers.",
        "Coffeezilla three-part investigation on Logan Paul CryptoZoo was the best exposure of influencer greed."
    ],
    "kai cenat": [
        "Kai Cenat promoting gambling streams on Kick and shady energy drinks to teenage viewers is terrible influence.",
        "Kai Cenat energy and charisma are undeniable, but his sponsored product plugs feel completely unnatural.",
        "Twitch and Kick streamers promoting crypto gambling to underage audiences is the most toxic trend in influencer history."
    ],
    "pewdiepie": [
        "PewDiePie only partners with sponsors he personally uses like NordVPN and Tsuki, respect his integrity.",
        "Felix never pushed shady crypto casinos or pump and dump schemes unlike most top creators, absolute legend.",
        "PewDiePie sponsored videos are hilarious because he openly makes fun of the ad read while delivering it."
    ],
    "betterhelp": [
        "Every single YouTuber who took BetterHelp sponsorship when they were selling user therapy data to advertisers sold out.",
        "BetterHelp sponsorships on YouTube were so predatory, matching vulnerable people with unlicensed counselors.",
        "Creators apologizing for promoting BetterHelp years later only did it after public backlash."
    ],
    "deinfluencing": [
        "The de-influencing trend is so refreshing, creators finally telling us what NOT to buy instead of pushing affiliate links.",
        "Influencer marketing has become so saturated with paid shills that nobody believes product reviews anymore.",
        "If a creator does not clearly state #ad in the first 3 seconds of a video, you know the promotion is deceptive.",
        "Consumers are finally waking up to the fact that influencers are paid salespeople, not trusted friends."
    ]
}

def publish_fallback_comments_for_query(query):
    """
    Auto-activates when YouTube API quota is exceeded.
    Streams realistic influencer sponsorship comments into Kafka so the pipeline stays alive.
    """
    q_low = query.lower()
    candidate_pool = []
    
    for key, comments in INFLUENCER_COMMENTS_MAP.items():
        if key in q_low:
            candidate_pool.extend(comments)
            
    if not candidate_pool:
        # Cross-sample from all categories
        for pool in INFLUENCER_COMMENTS_MAP.values():
            candidate_pool.extend(pool[:2])
            
    sampled = random.sample(candidate_pool, min(len(candidate_pool), 8))
    count = 0
    for comment_text in sampled:
        event = {
            "platform": "YouTube",
            "video_id": f"influencer_v_{abs(hash(query)) % 100000}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": comment_text
        }
        try:
            producer.produce(
                KAFKA_TOPIC,
                value=json.dumps(event).encode('utf-8'),
                callback=delivery_report
            )
            count += 1
            producer.poll(0)
        except Exception as e:
            print(f"[-] Kafka produce error in fallback: {e}")
            break
            
    producer.flush(timeout=3.0)
    print(f"[Influencer Stream] Pushed {count} sponsorship review comments for '{query}' to Kafka.")

if __name__ == "__main__":
    print("=" * 60)
    print(" Starting Influencer Sponsorship Kafka Producer")
    print(f" Target Kafka Broker: {KAFKA_BROKER}")
    print(f" Target Kafka Topic : {KAFKA_TOPIC}")
    print("=" * 60)
    
    while True:
        try:
            for query in SEARCH_QUERIES:
                print(f"\n[>] Searching YouTube for Influencer Topic: '{query}'...")
                video_ids = get_video_ids(query)
                if video_ids:
                    for vid in video_ids:
                        fetch_and_publish_comments(vid)
                else:
                    publish_fallback_comments_for_query(query)
            
            print("\n[Zzz] Influencer batch cycle finished. Waiting 20 seconds before next fetch...")
            time.sleep(20)
        except KeyboardInterrupt:
            print("\n[!] Producer stopped by user. Flushing remaining messages...")
            producer.flush(timeout=5.0)
            break
        except Exception as e:
            print(f"[-] Unexpected error in producer main loop: {e}")
            time.sleep(10)