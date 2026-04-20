#!/usr/bin/env python3
"""
Apply time-window sampling strategies from docs/time_window_sampling_note.md:

  A) Exclude spike calendar days (using docs/spike_dates_top10.csv by default)
  B) Per-(app_id, day) row cap with fixed random_state
  D) Train / validation split by at_parsed cutoff (no shuffle leakage)

Reads English-clean table (same columns as clean_en_only). Writes CSV + JSON manifest.

Examples:
  python scripts/06_insights/apply_time_window_sampling.py --exclude-spikes
  python scripts/06_insights/apply_time_window_sampling.py --exclude-spikes --per-day-cap 50 --random-state 42
  python scripts/06_insights/apply_time_window_sampling.py --split-cutoff 2026-04-01 \\
      --out-train data/processed/clean_en_train.csv --out-val data/processed/clean_en_val.csv
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN_XLSX = ROOT / "data" / "processed" / "clean_en_only.xlsx"
DEFAULT_IN_CSV = ROOT / "data" / "processed" / "clean_en_only.csv"
DEFAULT_SPIKE_CSV = ROOT / "docs" / "spike_dates_top10.csv"
DEFAULT_OUT = ROOT / "data" / "processed" / "clean_en_time_window.csv"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "time_window_sampling_manifest.json"


def _resolve_input(path: Path | None) -> Path:
    if path and path.is_file():
        return path.resolve()
    if DEFAULT_IN_XLSX.is_file():
        return DEFAULT_IN_XLSX.resolve()
    if DEFAULT_IN_CSV.is_file():
        return DEFAULT_IN_CSV.resolve()
    raise FileNotFoundError(f"No input found. Pass --input or add {DEFAULT_IN_XLSX} / {DEFAULT_IN_CSV}")


def _read_table(p: Path) -> pd.DataFrame:
    if p.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(p)
    return pd.read_csv(p, encoding="utf-8-sig")


def _path_for_manifest(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p.resolve())


def _parse_time(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["at_parsed"], errors="coerce")
    if ts.isna().all():
        ts = pd.to_datetime(out.get("at"), errors="coerce")
    out["_ts"] = ts
    out["_date"] = ts.dt.normalize()
    return out


def _load_spike_days(spike_csv: Path) -> set[pd.Timestamp]:
    if not spike_csv.is_file():
        raise FileNotFoundError(f"Missing {spike_csv}. Run scripts/06_insights/export_spike_days.py first.")
    sp = pd.read_csv(spike_csv, encoding="utf-8-sig")
    if "day" not in sp.columns:
        raise ValueError(f"{spike_csv} must contain a 'day' column.")
    days = pd.to_datetime(sp["day"], errors="coerce").dropna().dt.normalize().unique()
    return set(days)


def apply_pipeline(
    df: pd.DataFrame,
    *,
    exclude_spikes: bool,
    spike_csv: Path,
    per_day_cap: int | None,
    random_state: int,
    split_cutoff: str | None,
    drop_missing_time: bool,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, dict]:
    """Returns (single_or_train_df, val_df_or_none, stats_dict). If split_cutoff set, first is train."""
    work = _parse_time(df)
    stats: dict = {"input_rows": len(work)}

    if drop_missing_time:
        before = len(work)
        work = work[work["_ts"].notna()].copy()
        stats["dropped_missing_time"] = before - len(work)
    else:
        bad = work["_ts"].isna().sum()
        if bad:
            raise ValueError(f"{bad} rows have unparseable at_parsed/at; use --drop-missing-time or fix data.")

    meta_steps: list[str] = []

    if exclude_spikes:
        spike_days = _load_spike_days(spike_csv)
        before = len(work)
        work = work[~work["_date"].isin(spike_days)].copy()
        stats["excluded_spike_days"] = sorted({d.strftime("%Y-%m-%d") for d in spike_days})
        stats["rows_after_exclude_spikes"] = len(work)
        stats["dropped_for_spike_days"] = before - len(work)
        meta_steps.append("exclude_spikes")

    if per_day_cap is not None and per_day_cap > 0:
        before = len(work)
        # max per (app_id, calendar day); groups smaller than cap keep all rows
        work = (
            work.groupby(["app_id", "_date"], group_keys=False)
            .sample(n=per_day_cap, random_state=random_state)
            .sort_values("_ts")
            .reset_index(drop=True)
        )
        stats["per_day_cap"] = per_day_cap
        stats["random_state"] = random_state
        stats["rows_after_per_day_cap"] = len(work)
        stats["dropped_for_cap"] = before - len(work)
        meta_steps.append("per_day_cap")

    # drop helper columns for output unless split (we drop before write in main)
    out_cols_drop = ["_ts", "_date"]

    if split_cutoff:
        cutoff = pd.Timestamp(split_cutoff)
        train = work[work["_ts"] < cutoff].copy()
        val = work[work["_ts"] >= cutoff].copy()
        stats["split_cutoff"] = split_cutoff
        stats["train_rows"] = len(train)
        stats["val_rows"] = len(val)
        meta_steps.append("time_split")
        for d in (train, val):
            d.drop(columns=[c for c in out_cols_drop if c in d.columns], inplace=True)
        return train, val, {"steps": meta_steps, **stats}

    single = work.drop(columns=[c for c in out_cols_drop if c in work.columns])
    return single, None, {"steps": meta_steps, **stats}


def main() -> None:
    ap = argparse.ArgumentParser(description="Time-window sampling for clean_en_only-style tables.")
    ap.add_argument("--input", type=Path, default=None, help="clean_en xlsx/csv (default: processed clean_en_only)")
    ap.add_argument(
        "--exclude-spikes",
        action="store_true",
        help="Drop rows whose calendar day appears in spike CSV (default: docs/spike_dates_top10.csv)",
    )
    ap.add_argument("--spike-list", type=Path, default=DEFAULT_SPIKE_CSV, help="CSV with column 'day'")
    ap.add_argument("--per-day-cap", type=int, default=None, metavar="N", help="Max rows per (app_id, day)")
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument(
        "--split-cutoff",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="If set, write train (at < cutoff) and val (at >= cutoff); use with --out-train / --out-val",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Single output CSV (no time split)")
    ap.add_argument("--out-train", type=Path, default=ROOT / "data" / "processed" / "clean_en_train.csv")
    ap.add_argument("--out-val", type=Path, default=ROOT / "data" / "processed" / "clean_en_val.csv")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--drop-missing-time", action="store_true", help="Drop rows with bad at_parsed/at")
    args = ap.parse_args()

    src = _resolve_input(args.input)
    df = _read_table(src)

    if not args.exclude_spikes and args.per_day_cap is None and args.split_cutoff is None:
        raise SystemExit("Nothing to do. Pass --exclude-spikes and/or --per-day-cap N and/or --split-cutoff DATE.")

    train_df, val_df, stats = apply_pipeline(
        df,
        exclude_spikes=args.exclude_spikes,
        spike_csv=args.spike_list,
        per_day_cap=args.per_day_cap,
        random_state=args.random_state,
        split_cutoff=args.split_cutoff,
        drop_missing_time=args.drop_missing_time,
    )

    manifest = {
        "source_file": _path_for_manifest(src),
        "source_rows": len(df),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **stats,
    }

    if args.split_cutoff:
        assert train_df is not None and val_df is not None
        args.out_train.parent.mkdir(parents=True, exist_ok=True)
        train_df.to_csv(args.out_train, index=False, encoding="utf-8-sig")
        val_df.to_csv(args.out_val, index=False, encoding="utf-8-sig")
        manifest["outputs"] = {
            "train": _path_for_manifest(args.out_train),
            "val": _path_for_manifest(args.out_val),
        }
        print(f"Train: {len(train_df)} -> {args.out_train.resolve()}")
        print(f"Val:   {len(val_df)} -> {args.out_val.resolve()}")
    else:
        assert train_df is not None and val_df is None
        args.out.parent.mkdir(parents=True, exist_ok=True)
        train_df.to_csv(args.out, index=False, encoding="utf-8-sig")
        manifest["outputs"] = {"single": _path_for_manifest(args.out)}
        print(f"Wrote {len(train_df)} rows -> {args.out.resolve()}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest -> {args.manifest.resolve()}")


if __name__ == "__main__":
    main()
