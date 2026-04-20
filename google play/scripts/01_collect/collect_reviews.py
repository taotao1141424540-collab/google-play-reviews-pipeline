#!/usr/bin/env python3
"""
Collect Google Play reviews into a single raw CSV file.

Before running:
1) pip install google-play-scraper pandas openpyxl
2) Put the app list under config/ (see find_app_list()).
"""

from __future__ import annotations

import hashlib
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews


ROOT = Path(__file__).resolve().parents[2]
RAW_OUT = ROOT / "data" / "raw" / "google_play_reviews_raw.csv"
SUMMARY_OUT = ROOT / "reports" / "collection_summary.md"
RAW_METRICS_OUT = ROOT / "reports" / "raw_collection_metrics.csv"


def find_app_list() -> Path:
    """Single source: config/app_list.xlsx (columns: app_id, app_name, target_reviews, …)."""
    p = ROOT / "config" / "app_list.xlsx"
    if p.is_file():
        return p
    raise FileNotFoundError(
        "No app list found. Add: config/app_list.xlsx\n"
        "(Required columns include app_id; app_name and target_reviews are optional.)"
    )


def read_app_list(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path, encoding="utf-8-sig")


def stable_text_hash(text: str) -> str:
    if not text:
        return ""
    return hashlib.md5(text.encode("utf-8")).hexdigest()  # nosec B324


def enrich_raw_like_1400(df: pd.DataFrame) -> pd.DataFrame:
    """Align row schema with data/raw/google_play_reviews_raw_1400.csv."""
    if df.empty:
        return df
    out = df.copy()
    out["content"] = out["content"].fillna("").astype(str).str.strip()
    out["content_len"] = out["content"].str.len()
    out["is_short_text"] = out["content_len"] < 5
    out["has_dev_reply"] = (
        out["reply_content"].fillna("").astype(str).str.strip().ne("")
    )
    out["at_parsed"] = pd.to_datetime(out["at"], errors="coerce")
    out["text_hash"] = out["content"].apply(stable_text_hash)
    return out


def collect_one_app(app_id: str, app_name: str, target_reviews: int) -> tuple[pd.DataFrame, str]:
    rows = []
    token = None
    fetched = 0

    while fetched < target_reviews:
        batch_count = min(200, target_reviews - fetched)
        result, token = reviews(
            app_id,
            lang="en",
            country="us",
            sort=Sort.NEWEST,
            count=batch_count,
            continuation_token=token,
        )
        if not result:
            break

        for item in result:
            rows.append(
                {
                    "app_id": app_id,
                    "app_name": app_name,
                    "review_id": item.get("reviewId"),
                    "score": item.get("score"),
                    "content": item.get("content"),
                    "at": item.get("at"),
                    "thumbs_up_count": item.get("thumbsUpCount"),
                    "reply_content": item.get("replyContent"),
                    "replied_at": item.get("repliedAt"),
                }
            )
        fetched += len(result)
        if token is None:
            break

    df = pd.DataFrame(rows)
    return df, f"{app_id}: fetched={len(df)}"


def compute_raw_quality_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Metric set aligned with profiling google_play_reviews_raw_1400.csv (Figure 1 + score)."""
    if df.empty:
        return pd.DataFrame([{"metric": "total_rows", "value": 0}])

    work = enrich_raw_like_1400(df)
    total_rows = len(work)
    empty_text_ratio = (work["content_len"] == 0).mean()
    short_text_ratio = work["is_short_text"].mean()
    parseable_time_ratio = work["at_parsed"].notna().mean()
    score_num = pd.to_numeric(work["score"], errors="coerce")
    parseable_score_ratio = score_num.notna().mean()
    missing_review_id_ratio = work["review_id"].isna().mean()
    duplicate_review_id_rows = int(work.duplicated(subset=["review_id"]).sum())
    dedup_df = work.drop_duplicates(subset=["review_id"], keep="first")
    dedup_keep_ratio = len(dedup_df) / total_rows if total_rows else 0.0
    clean_rows = int((dedup_df["content_len"] >= 5).sum())
    has_dev_reply_ratio = float(work["has_dev_reply"].mean())
    replied_at_parsed = pd.to_datetime(work["replied_at"], errors="coerce")
    parseable_replied_at_when_reply_ratio = float(
        replied_at_parsed[work["has_dev_reply"]].notna().mean()
    ) if bool(work["has_dev_reply"].any()) else 0.0
    duplicate_text_hash_rows = int(work.duplicated(subset=["text_hash"]).sum())
    apps_count = int(work["app_id"].nunique())

    rows = [
        {"metric": "total_rows", "value": total_rows},
        {"metric": "unique_review_id_rows", "value": int(dedup_df.shape[0])},
        {"metric": "clean_rows", "value": clean_rows},
        {"metric": "dedup_keep_ratio", "value": round(dedup_keep_ratio, 4)},
        {"metric": "empty_text_ratio", "value": round(float(empty_text_ratio), 4)},
        {"metric": "short_text_ratio_lt5", "value": round(float(short_text_ratio), 4)},
        {"metric": "parseable_time_ratio", "value": round(float(parseable_time_ratio), 4)},
        {"metric": "parseable_score_ratio", "value": round(float(parseable_score_ratio), 4)},
        {"metric": "missing_review_id_ratio", "value": round(float(missing_review_id_ratio), 4)},
        {"metric": "duplicate_review_id_rows", "value": duplicate_review_id_rows},
        {"metric": "duplicate_text_hash_rows", "value": duplicate_text_hash_rows},
        {"metric": "has_dev_reply_ratio", "value": round(float(has_dev_reply_ratio), 4)},
        {
            "metric": "parseable_replied_at_when_reply_ratio",
            "value": round(parseable_replied_at_when_reply_ratio, 4),
        },
        {"metric": "apps_count", "value": apps_count},
    ]
    return pd.DataFrame(rows)


def main() -> None:
    app_list_path = find_app_list()
    app_df = read_app_list(app_list_path)
    all_frames = []
    logs = []

    for _, row in app_df.iterrows():
        app_id = str(row["app_id"]).strip()
        app_name = str(row.get("app_name", app_id)).strip()
        target_reviews = int(row.get("target_reviews", 500))
        if not app_id:
            continue
        try:
            df, log_line = collect_one_app(app_id, app_name, target_reviews)
            all_frames.append(df)
            logs.append(log_line)
        except Exception as exc:  # noqa: BLE001
            logs.append(f"{app_id}: failed={exc}")
            logs.append(traceback.format_exc())

    out_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    out_df = enrich_raw_like_1400(out_df)
    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(RAW_OUT, index=False, encoding="utf-8-sig")

    metrics_df = compute_raw_quality_metrics(out_df)
    RAW_METRICS_OUT.parent.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(RAW_METRICS_OUT, index=False, encoding="utf-8-sig")

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        app_list_rel = str(app_list_path.relative_to(ROOT))
    except ValueError:
        app_list_rel = str(app_list_path)
    summary = [
        "# Collection Summary",
        "",
        f"- run_time: {now}",
        f"- app_list_file: {app_list_rel}",
        f"- apps_count: {len(app_df)}",
        f"- total_rows: {len(out_df)}",
        f"- raw_metrics_csv: {RAW_METRICS_OUT.name}",
        "",
        "## Per App Logs",
        "",
    ] + [f"- {line}" for line in logs]
    SUMMARY_OUT.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"Saved raw data to: {RAW_OUT}")
    print(f"Saved raw metrics (Figure-1 style) to: {RAW_METRICS_OUT}")
    print(f"Saved summary to: {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
