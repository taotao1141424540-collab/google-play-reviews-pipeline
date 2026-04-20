#!/usr/bin/env python3
"""
Export top-N high-volume days from B3_daily_volume.csv for spike / sampling documentation.

Output: docs/spike_dates_top10.csv (default N=10; override with --top N)

Source: reports/eda_section_b/B3_daily_volume.csv (from run_eda_section_b.py)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
B3 = ROOT / "reports" / "eda_section_b" / "B3_daily_volume.csv"
DEFAULT_OUT = ROOT / "docs" / "spike_dates_top10.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b3", type=Path, default=B3)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.b3.is_file():
        raise SystemExit(f"Missing {args.b3}. Run scripts/03_eda/run_eda_section_b.py first.")

    df = pd.read_csv(args.b3)
    df = df.sort_values("reviews", ascending=False).head(args.top).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    total_all = pd.read_csv(args.b3)["reviews"].sum()
    df["share_of_all_reviews_pct"] = (100 * df["reviews"] / total_all).round(2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"Wrote {args.out} ({len(df)} rows). Total reviews in B3: {total_all}")


if __name__ == "__main__":
    main()
