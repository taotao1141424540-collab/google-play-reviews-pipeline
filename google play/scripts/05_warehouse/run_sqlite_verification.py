#!/usr/bin/env python3
"""
Run verification queries against play_reviews.db and write a text report for mentors / CI.

Usage:
  python scripts/05_warehouse/run_sqlite_verification.py
  python scripts/05_warehouse/run_sqlite_verification.py --db data/warehouse/play_reviews.db
  python scripts/05_warehouse/run_sqlite_verification.py --out docs/sqlite_verification_results.txt
  python scripts/05_warehouse/run_sqlite_verification.py --both
  python scripts/05_warehouse/run_sqlite_verification.py --both --en-db data/warehouse/play_reviews_en.db --out-en docs/sqlite_verification_results_en.txt
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "warehouse" / "play_reviews.db"
DEFAULT_DB_EN = ROOT / "data" / "warehouse" / "play_reviews_en.db"
DEFAULT_OUT = ROOT / "docs" / "sqlite_verification_results.txt"
DEFAULT_OUT_EN = ROOT / "docs" / "sqlite_verification_results_en.txt"

CHECKS: list[tuple[str, str]] = [
    ("ingestion_meta", "SELECT key, value FROM ingestion_meta ORDER BY key"),
    ("row_counts", "SELECT 'apps' AS tbl, COUNT(*) FROM apps UNION ALL SELECT 'reviews', COUNT(*) FROM reviews"),
    ("reviews_by_app_top5", "SELECT app_id, COUNT(*) AS n FROM reviews GROUP BY app_id ORDER BY n DESC LIMIT 5"),
    ("reviews_by_score", "SELECT score, COUNT(*) AS n FROM reviews GROUP BY score ORDER BY score"),
    ("null_keys", "SELECT SUM(CASE WHEN review_id IS NULL OR review_id = '' THEN 1 ELSE 0 END) AS bad_review_id FROM reviews"),
    ("english_flag_dist", "SELECT is_en, COUNT(*) FROM reviews GROUP BY is_en"),
    ("avg_content_len", "SELECT ROUND(AVG(content_len), 2) AS mean_len, COUNT(*) AS n FROM reviews"),
]


def build_report(db_path: Path) -> str:
    lines: list[str] = [
        "# SQLite verification report",
        f"# database: {db_path.resolve()}",
        "",
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        for title, sql in CHECKS:
            lines.append(f"## {title}")
            lines.append(dedent(sql).strip())
            rows = conn.execute(sql).fetchall()
            if not rows:
                lines.append("(no rows)")
            else:
                cols = rows[0].keys()
                lines.append(" | ".join(cols))
                lines.append("-" * (sum(len(c) for c in cols) + 3 * len(cols)))
                for r in rows:
                    lines.append(" | ".join(str(r[c]) for c in cols))
            lines.append("")
    finally:
        conn.close()
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run SQLite warehouse verification queries.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Primary database (default: full warehouse)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Report path for primary --db")
    ap.add_argument(
        "--both",
        action="store_true",
        help=f"Also verify English subset DB ({DEFAULT_DB_EN.relative_to(ROOT)}) -> --out-en",
    )
    ap.add_argument(
        "--en-db",
        type=Path,
        default=DEFAULT_DB_EN,
        help="English subset database path (used with --both)",
    )
    ap.add_argument("--out-en", type=Path, default=DEFAULT_OUT_EN, help="Report path when using --both for --en-db")
    args = ap.parse_args()

    tasks: list[tuple[Path, Path]] = [(args.db.resolve(), args.out.resolve())]
    if args.both:
        tasks.append((args.en_db.resolve(), args.out_en.resolve()))

    primary = True
    for db_path, out_path in tasks:
        if not db_path.is_file():
            if primary:
                raise SystemExit(f"Database not found: {db_path}. Run scripts/05_warehouse/load_to_sqlite.py first.")
            print(f"Skip (database not found): {db_path}")
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = build_report(db_path)
        out_path.write_text(text, encoding="utf-8")
        if args.both:
            print(f"\n--- {db_path.name} ---\n")
        print(text)
        print(f"\nWrote: {out_path.resolve()}")
        primary = False


if __name__ == "__main__":
    main()
