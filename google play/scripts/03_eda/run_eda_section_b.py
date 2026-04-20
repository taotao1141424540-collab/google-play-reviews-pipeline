#!/usr/bin/env python3
"""
EDA Section B (模式与对比) — patterns and cross-sections.

Input:
  data/processed/clean_en_only.xlsx  (or .csv if xlsx missing)

Output:
  reports/eda_section_b/
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MPL = _ROOT / ".mplconfig"
_MPL.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = _ROOT
CLEAN_EN_XLSX = ROOT / "data" / "processed" / "clean_en_only.xlsx"
CLEAN_EN_CSV = ROOT / "data" / "processed" / "clean_en_only.csv"
OUT_DIR = ROOT / "reports" / "eda_section_b"


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

    if "at_parsed" in df.columns:
        df["at_parsed"] = pd.to_datetime(df["at_parsed"], errors="coerce")

    # --- B1: per-app volume, mean score, mean length ---
    g = (
        df.groupby(["app_id", "app_name"], observed=False)
        .agg(rows=("review_id", "count"), mean_score=("score", "mean"), mean_len=("content_len", "mean"))
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    g.to_csv(OUT_DIR / "B1_per_app_stats.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    names = g["app_name"].str[:18]
    axes[0].barh(names, g["mean_score"], color="#4C72B0")
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Mean star rating")
    axes[0].set_title("B1: Mean score by app")
    axes[1].barh(names, g["mean_len"], color="#55A868")
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Mean review length (chars)")
    axes[1].set_title("B1: Mean length by app")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "B1_per_app_bars.png", dpi=150)
    plt.close(fig)

    # --- B2: rating skewness by app (偏态) ---
    def _skew(s: pd.Series) -> float:
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < 3:
            return float("nan")
        return float(s.skew())

    skew_df = (
        df.groupby(["app_id", "app_name"], observed=False)["score"]
        .apply(_skew)
        .reset_index(name="score_skew")
        .sort_values("score_skew")
    )
    skew_df.to_csv(OUT_DIR / "B2_score_skew_by_app.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(skew_df))))
    ax.barh(skew_df["app_name"].str[:22], skew_df["score_skew"], color="#C44E52")
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Skewness of star ratings (higher = more high-star tail)")
    ax.set_title("B2: Rating skewness by app")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "B2_score_skew_by_app.png", dpi=150)
    plt.close(fig)

    # Boxplot: score distribution per app (wide)
    apps_order = g.sort_values("rows", ascending=False)["app_name"].tolist()
    data_box = [df.loc[df["app_name"] == app, "score"].dropna() for app in apps_order]
    fig, ax = plt.subplots(figsize=(max(14, len(apps_order) * 0.8), 5))
    ax.boxplot(data_box, tick_labels=[n[:12] for n in apps_order], showfliers=False)
    ax.set_xticklabels([n[:12] for n in apps_order], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Star rating")
    ax.set_title("B2: Rating distribution by app (boxplot, no outliers)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "B2_rating_boxplot_by_app.png", dpi=150)
    plt.close(fig)

    # --- B3: daily review volume ---
    if df["at_parsed"].notna().any():
        daily = df.dropna(subset=["at_parsed"]).copy()
        daily["day"] = daily["at_parsed"].dt.floor("D")
        ts = daily.groupby("day", observed=False).size().rename("reviews")
        ts.to_csv(OUT_DIR / "B3_daily_volume.csv")
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(ts.index, ts.values, color="#8172B3", linewidth=1.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()
        ax.set_ylabel("Reviews per day")
        ax.set_title("B3: Daily review volume (all apps, clean_en_only)")
        fig.tight_layout()
        fig.savefig(OUT_DIR / "B3_daily_volume.png", dpi=150)
        plt.close(fig)
    else:
        pd.DataFrame({"note": ["at_parsed missing or all NaN — skip B3 time plot"]}).to_csv(
            OUT_DIR / "B3_daily_volume_skip.csv", index=False
        )

    # --- B4: inconsistent rating flag ---
    if "is_inconsistent_rating" in df.columns:
        rate = float(df["is_inconsistent_rating"].fillna(False).mean())
        pd.DataFrame([{"metric": "inconsistent_rating_rate", "value": rate}]).to_csv(
            OUT_DIR / "B4_inconsistent_rating_rate.csv", index=False
        )
        cols = [c for c in ["app_name", "score", "content", "sentiment_keyword", "is_inconsistent_rating"] if c in df.columns]
        samp = df.loc[df["is_inconsistent_rating"].fillna(False), cols].head(15)
        samp.to_csv(OUT_DIR / "B4_inconsistent_rating_sample.csv", index=False)
    else:
        pd.DataFrame([{"note": "is_inconsistent_rating column missing"}]).to_csv(
            OUT_DIR / "B4_skip.csv", index=False
        )

    # --- B5: duplicate text_hash top 20 ---
    vc = df.groupby("text_hash", observed=False).size().sort_values(ascending=False).head(20)
    ex = df.drop_duplicates(subset=["text_hash"])[["text_hash", "content"]].set_index("text_hash")
    top = (
        vc.rename("duplicate_count")
        .reset_index()
        .merge(ex, on="text_hash", how="left")
    )
    top.to_csv(OUT_DIR / "B5_top_duplicate_text_hashes.csv", index=False)

    lines = [
        "# EDA Section B — Summary",
        "",
        "## Input",
        f"- `{CLEAN_EN_XLSX.relative_to(ROOT)}` or `clean_en_only.csv`",
        f"- Rows: {len(df):,}",
        "",
        "## Outputs",
        "",
        "- `B1_per_app_stats.csv`, `B1_per_app_bars.png`",
        "- `B2_score_skew_by_app.csv`, `B2_score_skew_by_app.png`, `B2_rating_boxplot_by_app.png`",
        "- `B3_daily_volume.csv` + `B3_daily_volume.png` (or skip csv)",
        "- `B4_inconsistent_rating_rate.csv`, `B4_inconsistent_rating_sample.csv`",
        "- `B5_top_duplicate_text_hashes.csv`",
        "",
    ]
    (OUT_DIR / "README_eda_section_b.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Done. Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
