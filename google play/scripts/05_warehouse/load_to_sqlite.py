#!/usr/bin/env python3
"""
Load processed Google Play reviews into SQLite (normalized apps + reviews + meta).

Reads the same logical schema as clean_all_languages / clean_en_only xlsx or csv.

Usage:
  python scripts/05_warehouse/load_to_sqlite.py
  python scripts/05_warehouse/load_to_sqlite.py --english-only
  python scripts/05_warehouse/load_to_sqlite.py --input data/processed/clean_en_only.xlsx
  python scripts/05_warehouse/load_to_sqlite.py --source clean_all
  python scripts/05_warehouse/load_to_sqlite.py --source clean_en --db data/warehouse/play_reviews.db
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "warehouse" / "play_reviews.db"
DEFAULT_DB_EN = ROOT / "data" / "warehouse" / "play_reviews_en.db"
SCHEMA_SQL = ROOT / "sql" / "schema.sql"

SOURCE_PRESETS = {
    "clean_all": [
        ROOT / "data" / "processed" / "clean_all_languages.xlsx",
        ROOT / "data" / "processed" / "clean_all_languages.csv",
    ],
    "clean_en": [
        ROOT / "data" / "processed" / "clean_en_only.xlsx",
        ROOT / "data" / "processed" / "clean_en_only.csv",
    ],
}


def _resolve_input(path: Path | None, source: str | None) -> Path:
    if path and path.exists():
        return path.resolve()
    if source:
        key = source.strip().lower().replace("-", "_")
        if key not in SOURCE_PRESETS:
            raise ValueError(f"--source must be one of: {list(SOURCE_PRESETS)}")
        for c in SOURCE_PRESETS[key]:
            if c.exists():
                return c.resolve()
        raise FileNotFoundError(f"No file found for --source {source!r} (tried xlsx/csv).")
    candidates = SOURCE_PRESETS["clean_all"] + SOURCE_PRESETS["clean_en"]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError("No clean_all_languages / clean_en_only xlsx or csv found.")


def _read_table(p: Path) -> pd.DataFrame:
    if p.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(p)
    return pd.read_csv(p, encoding="utf-8-sig")


def _prepare_reviews(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "app_name" in out.columns:
        out = out.drop(columns=["app_name"])
    for col in out.select_dtypes(include=["bool"]).columns:
        out[col] = out[col].astype("int8")
    for col in out.select_dtypes(include=["datetimetz", "datetime64"]).columns:
        out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        out[col] = out[col].replace("NaT", None)
    out["review_id"] = out["review_id"].astype(str)
    out["app_id"] = out["app_id"].astype(str)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build SQLite warehouse from cleaned reviews.")
    ap.add_argument("--input", type=Path, default=None, help="clean xlsx/csv path")
    ap.add_argument(
        "--english-only",
        "-e",
        action="store_true",
        help="Load only clean_en_only (English subset). Default DB: data/warehouse/play_reviews_en.db",
    )
    ap.add_argument(
        "--source",
        choices=("clean_all", "clean_en"),
        default=None,
        help="shorthand to pick clean_all_languages vs clean_en_only file",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"SQLite database file (default: {DEFAULT_DB.relative_to(ROOT)}; with --english-only: {DEFAULT_DB_EN.relative_to(ROOT)})",
    )
    args = ap.parse_args()

    if args.english_only and args.source == "clean_all":
        ap.error("--english-only cannot be used with --source clean_all")

    effective_source = "clean_en" if args.english_only else args.source
    db_path = args.db
    if db_path is None:
        db_path = DEFAULT_DB_EN if args.english_only else DEFAULT_DB

    src = _resolve_input(args.input, effective_source)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = _read_table(src)
    apps = df[["app_id", "app_name"]].drop_duplicates(subset=["app_id"]).copy()
    apps["app_id"] = apps["app_id"].astype(str)
    reviews = _prepare_reviews(df)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        schema = SCHEMA_SQL.read_text(encoding="utf-8")
        conn.executescript(schema)
        apps.to_sql("apps", conn, if_exists="append", index=False)
        reviews.to_sql("reviews", conn, if_exists="append", index=False)
        try:
            src_rel = str(src.relative_to(ROOT))
        except ValueError:
            src_rel = str(src)
        name_l = src.name.lower()
        if "clean_en_only" in name_l:
            subset_label = "clean_en_only"
        elif "clean_all" in name_l:
            subset_label = "clean_all_languages"
        else:
            subset_label = "custom"
        meta_rows = [
            ("source_file", src_rel),
            ("data_subset", subset_label),
            ("source_rows", str(len(reviews))),
            ("app_count", str(len(apps))),
            ("loaded_at_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        conn.executemany(
            "INSERT INTO ingestion_meta (key, value) VALUES (?, ?)",
            meta_rows,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Loaded {len(reviews)} reviews, {len(apps)} apps from {src}")
    print(f"Database: {db_path.resolve()}")
    print("Run: python scripts/05_warehouse/run_sqlite_verification.py")


if __name__ == "__main__":
    main()
