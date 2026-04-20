#!/usr/bin/env python3
"""
Clean Google Play reviews with layered quality checks.

Input: data/raw/google_play_reviews_raw.csv

Core outputs:
1) clean_all_languages.csv
2) clean_en_only.csv
3) quality_report.csv
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from langdetect import LangDetectException, detect


ROOT = Path(__file__).resolve().parents[2]
RAW_IN = ROOT / "data" / "raw" / "google_play_reviews_raw.csv"
CLEAN_ALL_OUT = ROOT / "data" / "processed" / "clean_all_languages.csv"
CLEAN_EN_OUT = ROOT / "data" / "processed" / "clean_en_only.csv"
QUALITY_REPORT_OUT = ROOT / "reports" / "quality_report.csv"

SHORT_TEXT_THRESHOLD = 5


def normalize_text(x: object) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def preprocess_text(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"https?://\S+|www\.\S+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def stable_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()  # nosec B324


def detect_lang_safe(text: str) -> str:
    if not text or len(text) < SHORT_TEXT_THRESHOLD:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def is_noise_text(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    letters = sum(ch.isalpha() for ch in t)
    if letters == 0:
        return True
    if len(set(t.lower())) <= 2 and len(t) >= 6:
        return True
    low_info = {"ok", "good", "nice", "bad", "wow", "lol", "ads"}
    if t.lower() in low_info and len(t) <= 4:
        return True
    return False


def sentiment_keyword_label(text: str) -> str:
    t = text.lower()
    positive = ["good", "great", "excellent", "love", "amazing", "perfect"]
    negative = ["bad", "terrible", "worst", "hate", "bug", "crash", "ads", "scam"]
    pos_hit = any(w in t for w in positive)
    neg_hit = any(w in t for w in negative)
    if pos_hit and not neg_hit:
        return "positive"
    if neg_hit and not pos_hit:
        return "negative"
    return "neutral"


def main() -> None:
    raw_in = RAW_IN
    if not raw_in.is_file():
        raise FileNotFoundError(f"Raw input not found: {raw_in}")

    df = pd.read_csv(raw_in)
    if df.empty:
        raise ValueError("Raw input is empty.")

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df["review_id"] = df["review_id"].astype(str)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["thumbs_up_count"] = pd.to_numeric(df["thumbs_up_count"], errors="coerce").fillna(0)
    df["content"] = df["content"].apply(normalize_text)
    df["content_len"] = df["content"].str.len()
    df["is_empty_text"] = df["content"].eq("")
    df["is_short_text"] = df["content_len"] < SHORT_TEXT_THRESHOLD
    df["at_parsed"] = pd.to_datetime(df["at"], errors="coerce")
    df["replied_at_parsed"] = pd.to_datetime(df["replied_at"], errors="coerce")
    df["content_clean"] = df["content"].apply(preprocess_text)
    df["text_hash"] = df["content_clean"].apply(stable_hash)

    # P1: language + noise flags.
    df["detected_lang"] = df["content_clean"].apply(detect_lang_safe)
    df["is_en"] = df["detected_lang"].eq("en")
    df["is_noise"] = df["content_clean"].apply(is_noise_text) | df["is_short_text"] | df["is_empty_text"]

    # P2: enhanced checks.
    df["is_missing_key_fields"] = (
        df["review_id"].isna() | df["score"].isna() | df["at_parsed"].isna() | df["content"].isna()
    )
    df["sentiment_keyword"] = df["content_clean"].apply(sentiment_keyword_label)
    df["is_inconsistent_rating"] = (
        ((df["score"] <= 2) & (df["sentiment_keyword"] == "positive"))
        | ((df["score"] >= 4) & (df["sentiment_keyword"] == "negative"))
    )

    hourly_counts = (
        df.assign(hour_bucket=df["at_parsed"].dt.floor("h"))
        .groupby("hour_bucket")
        .size()
        .rename("hourly_count")
    )
    spike_threshold = hourly_counts.quantile(0.95) if not hourly_counts.empty else 0
    df["hour_bucket"] = df["at_parsed"].dt.floor("h")
    df = df.merge(hourly_counts, on="hour_bucket", how="left")
    df["hourly_count"] = df["hourly_count"].fillna(0)
    df["is_time_anomaly"] = df["hourly_count"] >= spike_threshold

    dup_text_count = df.groupby("text_hash")["text_hash"].transform("count")
    df["is_spam_bot_suspect"] = (
        (dup_text_count >= 3)
        | ((df["content_len"] <= 6) & (df["thumbs_up_count"] == 0))
        | df["is_time_anomaly"]
    )

    # P0: dedup + base filtering.
    total_rows = len(df)
    duplicate_rows = int(df.duplicated(subset=["review_id"]).sum())
    dedup_df = df.drop_duplicates(subset=["review_id"], keep="first").copy()
    clean_all = dedup_df[~dedup_df["is_empty_text"] & ~dedup_df["is_short_text"]].copy()
    clean_en = clean_all[clean_all["is_en"]].copy()

    CLEAN_ALL_OUT.parent.mkdir(parents=True, exist_ok=True)
    clean_all.to_csv(CLEAN_ALL_OUT, index=False, encoding="utf-8-sig")
    clean_en.to_csv(CLEAN_EN_OUT, index=False, encoding="utf-8-sig")

    quality_rows = [
        {"section": "run", "metric": "run_time", "value": run_time},
        {"section": "run", "metric": "raw_input_file", "value": str(raw_in)},
        {"section": "p0", "metric": "raw_rows", "value": total_rows},
        {"section": "p0", "metric": "duplicate_rate", "value": round(duplicate_rows / total_rows, 4)},
        {"section": "p0", "metric": "empty_text_rate", "value": round(float(df["is_empty_text"].mean()), 4)},
        {"section": "p0", "metric": "short_text_rate_lt5", "value": round(float(df["is_short_text"].mean()), 4)},
        {"section": "p0", "metric": "parseable_time_rate", "value": round(float(df["at_parsed"].notna().mean()), 4)},
        {"section": "p0", "metric": "parseable_score_rate", "value": round(float(df["score"].notna().mean()), 4)},
        {"section": "p0", "metric": "clean_all_rows", "value": len(clean_all)},
        {
            "section": "p1",
            "metric": "english_rate_after_p0",
            "value": round(float(clean_all["is_en"].mean()), 4) if len(clean_all) else 0,
        },
        {
            "section": "p1",
            "metric": "noise_rate_after_p0",
            "value": round(float(clean_all["is_noise"].mean()), 4) if len(clean_all) else 0,
        },
        {
            "section": "p2",
            "metric": "missing_key_fields_rate",
            "value": round(float(df["is_missing_key_fields"].mean()), 4),
        },
        {
            "section": "p2",
            "metric": "spam_bot_suspect_rate",
            "value": round(float(clean_all["is_spam_bot_suspect"].mean()), 4) if len(clean_all) else 0,
        },
        {
            "section": "p2",
            "metric": "inconsistent_rating_rate",
            "value": round(float(clean_all["is_inconsistent_rating"].mean()), 4) if len(clean_all) else 0,
        },
        {
            "section": "p2",
            "metric": "time_anomaly_rate",
            "value": round(float(clean_all["is_time_anomaly"].mean()), 4) if len(clean_all) else 0,
        },
        {"section": "output", "metric": "clean_en_rows", "value": len(clean_en)},
    ]
    pd.DataFrame(quality_rows).to_csv(QUALITY_REPORT_OUT, index=False, encoding="utf-8-sig")

    print(f"Saved: {CLEAN_ALL_OUT}")
    print(f"Saved: {CLEAN_EN_OUT}")
    print(f"Saved: {QUALITY_REPORT_OUT}")


if __name__ == "__main__":
    main()
