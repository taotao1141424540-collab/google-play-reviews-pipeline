#!/usr/bin/env python3
"""
EDA Section E — risk flags (exploratory; not ground truth).

Input:
  data/processed/clean_en_only.xlsx (or .csv)

Output:
  reports/eda_section_e/
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MPL = _ROOT / ".mplconfig"
_MPL.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL))

import matplotlib.pyplot as plt
import pandas as pd

ROOT = _ROOT
CLEAN_EN_XLSX = ROOT / "data" / "processed" / "clean_en_only.xlsx"
CLEAN_EN_CSV = ROOT / "data" / "processed" / "clean_en_only.csv"
OUT_DIR = ROOT / "reports" / "eda_section_e"


def load_clean_en() -> pd.DataFrame:
    if CLEAN_EN_XLSX.exists():
        return pd.read_excel(CLEAN_EN_XLSX)
    if CLEAN_EN_CSV.exists():
        return pd.read_csv(CLEAN_EN_CSV)
    raise FileNotFoundError(f"Missing {CLEAN_EN_XLSX} and {CLEAN_EN_CSV}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_clean_en()

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    rows: list[dict[str, object]] = []

    # --- E1: time anomaly ---
    if "is_time_anomaly" in df.columns:
        rate = float(df["is_time_anomaly"].fillna(False).mean())
        rows.append({"metric": "time_anomaly_rate", "value": rate, "note": "heuristic spike-hour flag"})
        pd.DataFrame([{"is_time_anomaly": rate, "interpretation": "share of rows in top-volume hours"}]).to_csv(
            OUT_DIR / "E1_time_anomaly_rate.csv", index=False
        )
        if "hourly_count" in df.columns:
            hc = pd.to_numeric(df["hourly_count"], errors="coerce").dropna()
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.hist(hc.clip(upper=hc.quantile(0.99)), bins=40, color="#8172B3", edgecolor="white")
            ax.set_xlabel("hourly_count (capped at 99th pct for display)")
            ax.set_ylabel("Rows")
            ax.set_title("E1: Distribution of hourly bucket volume (exploratory)")
            fig.tight_layout()
            fig.savefig(OUT_DIR / "E1_hourly_count_distribution.png", dpi=150)
            plt.close(fig)
    else:
        pd.DataFrame([{"note": "is_time_anomaly missing — skip E1"}]).to_csv(OUT_DIR / "E1_skip.csv", index=False)

    # --- E2: spam/bot suspect ---
    if "is_spam_bot_suspect" in df.columns:
        rate = float(df["is_spam_bot_suspect"].fillna(False).mean())
        rows.append({"metric": "spam_bot_suspect_rate", "value": rate, "note": "heuristic composite flag"})
        pd.DataFrame([{"is_spam_bot_suspect_rate": rate}]).to_csv(OUT_DIR / "E2_spam_bot_suspect_rate.csv", index=False)

        cols = [c for c in ["app_name", "score", "content_len", "content", "is_spam_bot_suspect", "text_hash"] if c in df.columns]
        samp = df.loc[df["is_spam_bot_suspect"].fillna(False), cols].head(20)
        samp.to_csv(OUT_DIR / "E2_spam_bot_suspect_sample.csv", index=False)

        vc = df["is_spam_bot_suspect"].fillna(False).astype(bool).value_counts()
        n_false = int(vc.get(False, 0))
        n_true = int(vc.get(True, 0))
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.bar(["False", "True"], [n_false, n_true], color=["#7F7F7F", "#E377C2"])
        ax.set_ylabel("Rows")
        ax.set_title("E2: spam_bot_suspect flag counts")
        fig.tight_layout()
        fig.savefig(OUT_DIR / "E2_spam_bot_flag_counts.png", dpi=150)
        plt.close(fig)
    else:
        pd.DataFrame([{"note": "is_spam_bot_suspect missing — skip E2"}]).to_csv(OUT_DIR / "E2_skip.csv", index=False)

    if rows:
        pd.DataFrame(rows).to_csv(OUT_DIR / "E_summary_rates.csv", index=False)

    readme = """# EDA Section E

Risk metrics are **heuristic** — use for limitations / follow-up sampling, not as definitive labels.

## Outputs
- `E1_time_anomaly_rate.csv`, `E1_hourly_count_distribution.png` (if columns exist)
- `E2_spam_bot_suspect_rate.csv`, `E2_spam_bot_flag_counts.png`, `E2_spam_bot_suspect_sample.csv`
- `E_summary_rates.csv`

## Re-run
```bash
python3 "google play/scripts/03_eda/run_eda_section_e.py"
```
"""
    (OUT_DIR / "README_eda_section_e.md").write_text(readme, encoding="utf-8")
    print(f"Done. Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
