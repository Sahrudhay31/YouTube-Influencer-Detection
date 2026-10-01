CREATE DATABASE IF NOT EXISTS sih_analytics;

CREATE TABLE IF NOT EXISTS sih_analytics.social_events (
    event_id UUID,
    timestamp DateTime,
    platform String,
    domain String,
    text String,
    sentiment String,
    entities Array(String),
    aspect_sentiments Array(String),
    video_id String
) ENGINE = MergeTree()
ORDER BY (domain, timestamp);