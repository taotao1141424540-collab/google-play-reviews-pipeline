-- SQLite schema for Google Play reviews (Phase I storage layer).
-- Load order: apps -> reviews -> ingestion_meta (filled by loader).

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS ingestion_meta;
DROP TABLE IF EXISTS apps;

CREATE TABLE apps (
  app_id   TEXT PRIMARY KEY,
  app_name TEXT NOT NULL
);

CREATE TABLE reviews (
  app_id                   TEXT NOT NULL,
  review_id                TEXT NOT NULL,
  score                    REAL,
  content                  TEXT,
  at                       TEXT,
  thumbs_up_count          INTEGER,
  reply_content            TEXT,
  replied_at               TEXT,
  content_len              INTEGER,
  is_short_text            INTEGER NOT NULL DEFAULT 0,
  has_dev_reply            INTEGER NOT NULL DEFAULT 0,
  at_parsed                TEXT,
  text_hash                TEXT,
  is_empty_text            INTEGER NOT NULL DEFAULT 0,
  replied_at_parsed        TEXT,
  content_clean            TEXT,
  detected_lang            TEXT,
  is_en                    INTEGER NOT NULL DEFAULT 0,
  is_noise                 INTEGER NOT NULL DEFAULT 0,
  is_missing_key_fields    INTEGER NOT NULL DEFAULT 0,
  sentiment_keyword        TEXT,
  is_inconsistent_rating   INTEGER NOT NULL DEFAULT 0,
  hour_bucket              TEXT,
  hourly_count             REAL,
  is_time_anomaly          INTEGER NOT NULL DEFAULT 0,
  is_spam_bot_suspect      INTEGER NOT NULL DEFAULT 0,
  loaded_at                TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (app_id, review_id),
  FOREIGN KEY (app_id) REFERENCES apps (app_id)
);

CREATE INDEX idx_reviews_at_parsed ON reviews (at_parsed);
CREATE INDEX idx_reviews_score ON reviews (score);
CREATE INDEX idx_reviews_is_en ON reviews (is_en);
CREATE INDEX idx_reviews_text_hash ON reviews (text_hash);

-- One row per load: source path, counts, timestamp (loader replaces table content each run).
CREATE TABLE ingestion_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
