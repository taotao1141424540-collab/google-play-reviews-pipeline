"""Append one row to data_quality_history.csv and distribution_history.csv.

Reads existing pipeline outputs under ``google play/`` (read-only).
Run from ``google play/`` root::

    python3 scripts/07_monitor/collect_run_metrics.py

Exit code: always 0 (aggregation only).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

DATA_QUALITY_COLS = [
    "run_ts",
    "raw_rows",
    "apps_count",
    "duplicate_rate",
    "empty_text_rate",
    "short_text_rate_lt5",
    "parseable_time_rate",
    "parseable_score_rate",
    "english_rate_after_p0",
    "noise_rate_after_p0",
    "missing_key_fields_rate",
    "inconsistent_rating_rate",
    "time_anomaly_rate",
    "spam_bot_suspect_rate",
    "clean_all_rows",
    "clean_en_rows",
]

DISTRIBUTION_COLS = [
    "run_ts",
    "score_1_pct",
    "score_2_pct",
    "score_3_pct",
    "score_4_pct",
    "score_5_pct",
    "len_mean",
    "len_p50",
    "len_p90",
    "en_share",
    "last7d_reviews_sum",
    "last7d_daily_mean",
]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _f(x: Any) -> float:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return float("nan")
        return float(x)
    except Exception:
        return float("nan")


def load_quality_series(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    if df.empty or "section" not in df.columns or "metric" not in df.columns:
        return pd.Series(dtype=float)
    idx = df["section"].astype(str) + "." + df["metric"].astype(str)
    return pd.Series(df["value"].values, index=idx, dtype=object)


def q(series: pd.Series, section: str, metric: str) -> float:
    key = f"{section}.{metric}"
    if key not in series.index:
        return float("nan")
    return _f(series.loc[key])


def load_raw_metrics(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if df.empty or "metric" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        out[str(row["metric"])] = _f(row.get("value"))
    return out


def load_rating_pcts(path: Path) -> dict[str, float]:
    if not path.exists():
        return {f"score_{i}_pct": float("nan") for i in range(1, 6)}
    df = pd.read_csv(path)
    if "score" not in df.columns or "count" not in df.columns:
        return {f"score_{i}_pct": float("nan") for i in range(1, 6)}
    total = float(df["count"].sum()) or float("nan")
    pcts: dict[str, float] = {}
    for star in range(1, 6):
        sub = df[df["score"] == star]
        cnt = float(sub["count"].sum()) if len(sub) else 0.0
        pcts[f"score_{star}_pct"] = (cnt / total) if total and not np.isnan(total) else float("nan")
    return pcts


def load_length_stats(path: Path) -> tuple[float, float, float]:
    if not path.exists():
        return float("nan"), float("nan"), float("nan")
    df = pd.read_csv(path)
    if df.shape[1] < 2:
        return float("nan"), float("nan"), float("nan")
    df = df.rename(columns={df.columns[0]: "stat", df.columns[1]: "value"})
    df["stat"] = df["stat"].astype(str).str.strip()
    df = df[df["stat"].str.len() > 0]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    def pick(stat: str) -> float:
        m = df[df["stat"] == stat]
        return float(m["value"].iloc[0]) if len(m) else float("nan")

    return pick("mean"), pick("50%"), pick("90%")


def load_en_share_c2(path: Path) -> float:
    if not path.exists():
        return float("nan")
    df = pd.read_csv(path)
    if "metric" in df.columns and "value" in df.columns:
        m = df[df["metric"].astype(str) == "english_share_on_clean_all"]
        if len(m):
            return _f(m.iloc[0]["value"])
    return float("nan")


def last7d_from_b3(path: Path) -> tuple[float, float]:
    if not path.exists():
        return float("nan"), float("nan")
    df = pd.read_csv(path)
    if "day" not in df.columns or "reviews" not in df.columns:
        return float("nan"), float("nan")
    df = df.copy()
    df["day"] = pd.to_datetime(df["day"], errors="coerce")
    df = df.dropna(subset=["day"]).sort_values("day")
    if df.empty:
        return float("nan"), float("nan")
    tail = df.tail(7)
    s = float(tail["reviews"].sum())
    mean = s / 7.0
    return s, mean


def append_csv_row(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {k: row.get(k) for k in columns}
    new_df = pd.DataFrame([out], columns=columns)
    if path.exists():
        new_df.to_csv(path, mode="a", header=False, index=False, lineterminator="\n")
    else:
        new_df.to_csv(path, mode="w", header=True, index=False, lineterminator="\n")


def collect_data_quality_row(run_ts: Optional[str] = None) -> dict[str, Any]:
    qs = load_quality_series(ROOT / "reports/quality_report.csv")
    raw = load_raw_metrics(ROOT / "reports/raw_collection_metrics.csv")

    raw_rows = raw.get("total_rows")
    if raw_rows is None or (isinstance(raw_rows, float) and np.isnan(raw_rows)):
        raw_rows = q(qs, "p0", "raw_rows")
    apps = raw.get("apps_count", float("nan"))

    return {
        "run_ts": run_ts or _ts(),
        "raw_rows": raw_rows,
        "apps_count": apps,
        "duplicate_rate": q(qs, "p0", "duplicate_rate"),
        "empty_text_rate": q(qs, "p0", "empty_text_rate"),
        "short_text_rate_lt5": q(qs, "p0", "short_text_rate_lt5"),
        "parseable_time_rate": q(qs, "p0", "parseable_time_rate"),
        "parseable_score_rate": q(qs, "p0", "parseable_score_rate"),
        "english_rate_after_p0": q(qs, "p1", "english_rate_after_p0"),
        "noise_rate_after_p0": q(qs, "p1", "noise_rate_after_p0"),
        "missing_key_fields_rate": q(qs, "p2", "missing_key_fields_rate"),
        "inconsistent_rating_rate": q(qs, "p2", "inconsistent_rating_rate"),
        "time_anomaly_rate": q(qs, "p2", "time_anomaly_rate"),
        "spam_bot_suspect_rate": q(qs, "p2", "spam_bot_suspect_rate"),
        "clean_all_rows": q(qs, "p0", "clean_all_rows"),
        "clean_en_rows": q(qs, "output", "clean_en_rows"),
    }


def collect_distribution_row(run_ts: Optional[str] = None) -> dict[str, Any]:
    ts = run_ts or _ts()
    pcts = load_rating_pcts(ROOT / "reports/eda_section_a/A1_rating_distribution.csv")
    mean_v, p50, p90 = load_length_stats(ROOT / "reports/eda_section_a/A3_length_summary.csv")
    en = load_en_share_c2(ROOT / "reports/eda_section_c/C2_english_subset_summary.csv")
    s7, m7 = last7d_from_b3(ROOT / "reports/eda_section_b/B3_daily_volume.csv")
    row: dict[str, Any] = {
        "run_ts": ts,
        "len_mean": mean_v,
        "len_p50": p50,
        "len_p90": p90,
        "en_share": en,
        "last7d_reviews_sum": s7,
        "last7d_daily_mean": m7,
    }
    row.update(pcts)
    return row


def run_collect() -> int:
    dq_path = ROOT / "reports/monitoring/data_quality_history.csv"
    dist_path = ROOT / "reports/monitoring/distribution_history.csv"

    ts = _ts()
    dq_row = collect_data_quality_row(ts)
    dist_row = collect_distribution_row(ts)

    append_csv_row(dq_path, dq_row, DATA_QUALITY_COLS)
    append_csv_row(dist_path, dist_row, DISTRIBUTION_COLS)
    print(f"Appended rows to:\n  {dq_path}\n  {dist_path}")
    return 0


if __name__ == "__main__":
    _mon = Path(__file__).resolve().parent
    if str(_mon) not in sys.path:
        sys.path.insert(0, str(_mon))
    from _runlog import run_logger  # noqa: E402

    with run_logger(
        script="scripts/07_monitor/collect_run_metrics.py",
        args=" ".join(sys.argv[1:]),
        log_path=str(ROOT / "logs/pipeline_runs.jsonl"),
    ) as ctx:
        rc = run_collect()
        ctx.set_rows_out(2)
        ctx.add_output("reports/monitoring/data_quality_history.csv")
        ctx.add_output("reports/monitoring/distribution_history.csv")
    raise SystemExit(rc)
