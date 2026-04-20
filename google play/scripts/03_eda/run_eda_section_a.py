#!/usr/bin/env python3
"""
EDA Section A (必做).

Inputs (xlsx preferred, else csv — same as sections B–E):
  data/processed/clean_en_only.xlsx | clean_en_only.csv  (required)
  data/processed/clean_all_languages.xlsx | .csv  (optional)
  data/raw/google_play_reviews_raw.xlsx | google_play_reviews_raw.csv  (optional)

Outputs:
  reports/eda_section_a/
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MPL = _ROOT / ".mplconfig"
_MPL.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = _ROOT
RAW_XLSX = ROOT / "data" / "raw" / "google_play_reviews_raw.xlsx"
RAW_CSV = ROOT / "data" / "raw" / "google_play_reviews_raw.csv"
CLEAN_ALL_XLSX = ROOT / "data" / "processed" / "clean_all_languages.xlsx"
CLEAN_ALL_CSV = ROOT / "data" / "processed" / "clean_all_languages.csv"
CLEAN_EN_XLSX = ROOT / "data" / "processed" / "clean_en_only.xlsx"
CLEAN_EN_CSV = ROOT / "data" / "processed" / "clean_en_only.csv"
QUALITY_CSV = ROOT / "reports" / "quality_report.csv"
RAW_METRICS_CSV = ROOT / "reports" / "raw_collection_metrics.csv"
RAW_METRICS_PACKAGE_XLSX = ROOT / "reports" / "Raw Data_collection_metrics.xlsx"
OUT_DIR = ROOT / "reports" / "eda_section_a"


def _load_xlsx_or_csv(xlsx_path: Path, csv_path: Path) -> pd.DataFrame:
    """Prefer xlsx; fall back to utf-8-sig csv. Returns empty DataFrame if neither exists."""
    if xlsx_path.is_file():
        return pd.read_excel(xlsx_path)
    if csv_path.is_file():
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    return pd.DataFrame()


def _resolved_source_path(xlsx_path: Path, csv_path: Path) -> Path:
    """Path used for reporting (existing file, or xlsx as preferred label)."""
    if xlsx_path.is_file():
        return xlsx_path
    if csv_path.is_file():
        return csv_path
    return xlsx_path


def load_clean_en_required() -> pd.DataFrame:
    if CLEAN_EN_XLSX.is_file():
        return pd.read_excel(CLEAN_EN_XLSX)
    if CLEAN_EN_CSV.is_file():
        return pd.read_csv(CLEAN_EN_CSV, encoding="utf-8-sig")
    raise FileNotFoundError(f"Missing {CLEAN_EN_XLSX} and {CLEAN_EN_CSV}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []

    df_en = load_clean_en_required()
    df_raw = _load_xlsx_or_csv(RAW_XLSX, RAW_CSV)
    df_all = _load_xlsx_or_csv(CLEAN_ALL_XLSX, CLEAN_ALL_CSV)

    if not QUALITY_CSV.exists():
        missing.append(str(QUALITY_CSV.relative_to(ROOT)))
    if not RAW_METRICS_CSV.exists() and not RAW_METRICS_PACKAGE_XLSX.exists():
        missing.append(
            f"{RAW_METRICS_CSV.relative_to(ROOT)} (或整理包 `reports/Raw Data_collection_metrics.xlsx`)"
        )

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # --- A1: score distribution ---
    score_counts = df_en["score"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    score_counts.reindex(range(1, 6), fill_value=0).plot(kind="bar", ax=ax, color="#4C72B0")
    ax.set_xlabel("Star rating")
    ax.set_ylabel("Count")
    ax.set_title("A1: Rating distribution (clean_en_only)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "A1_rating_distribution.png", dpi=150)
    plt.close(fig)
    score_counts.to_csv(OUT_DIR / "A1_rating_distribution.csv", header=["count"])

    # --- A2: rating distribution by app (mean + count table + heatmap counts) ---
    by_app = (
        df_en.groupby(["app_id", "app_name", "score"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 6), fill_value=0)
    )
    by_app.to_csv(OUT_DIR / "A2_rating_counts_by_app.csv")
    mean_by_app = df_en.groupby(["app_id", "app_name"], observed=True)["score"].agg(["mean", "count"])
    mean_by_app.to_csv(OUT_DIR / "A2_mean_score_by_app.csv")

    y_labels = [f"{aid}\n{name}"[:40] for aid, name in by_app.index]
    fig, ax = plt.subplots(figsize=(12, max(4, 0.35 * len(by_app))))
    im = ax.imshow(by_app.values, aspect="auto", cmap="Blues")
    ax.set_yticks(range(len(by_app)))
    ax.set_yticklabels(y_labels, fontsize=7)
    ax.set_xticks(range(5))
    ax.set_xticklabels([str(i) for i in range(1, 6)])
    ax.set_xlabel("Star rating")
    ax.set_ylabel("App")
    ax.set_title("A2: Review counts by app and rating (heatmap)")
    fig.colorbar(im, ax=ax, label="Count")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "A2_rating_heatmap_by_app.png", dpi=150)
    plt.close(fig)

    # --- A3: review length ---
    lengths = df_en["content_len"].dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(lengths, bins=60, color="#55A868", edgecolor="white", alpha=0.9)
    ax.set_yscale("log")
    ax.set_xlabel("Review length (characters)")
    ax.set_ylabel("Count (log scale)")
    ax.set_title("A3: Review length distribution (clean_en_only)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "A3_review_length_hist.png", dpi=150)
    plt.close(fig)
    desc = lengths.describe(percentiles=[0.5, 0.9, 0.95])
    desc.to_csv(OUT_DIR / "A3_length_summary.csv", header=["value"])

    # --- A4: length vs rating ---
    fig, ax = plt.subplots(figsize=(8, 5))
    data_box = [df_en.loc[df_en["score"] == s, "content_len"].dropna() for s in range(1, 6)]
    ax.boxplot(data_box, tick_labels=[str(s) for s in range(1, 6)], showfliers=False)
    ax.set_xlabel("Star rating")
    ax.set_ylabel("Review length (characters)")
    ax.set_title("A4: Review length by rating (boxplot, no outliers)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "A4_length_by_rating_boxplot.png", dpi=150)
    plt.close(fig)
    grp = df_en.groupby("score")["content_len"].agg(["mean", "median", "count"])
    grp.to_csv(OUT_DIR / "A4_length_stats_by_rating.csv")

    # --- A5: scale chain ---
    raw_src = _resolved_source_path(RAW_XLSX, RAW_CSV)
    all_src = _resolved_source_path(CLEAN_ALL_XLSX, CLEAN_ALL_CSV)
    en_src = _resolved_source_path(CLEAN_EN_XLSX, CLEAN_EN_CSV)
    rows_a5 = [
        {
            "stage": "raw",
            "file": str(raw_src.relative_to(ROOT)),
            "rows": int(len(df_raw)) if len(df_raw) else None,
        },
        {
            "stage": "after_P0_all_languages",
            "file": str(all_src.relative_to(ROOT)),
            "rows": int(len(df_all)) if len(df_all) else None,
        },
        {
            "stage": "after_P0_english_only",
            "file": str(en_src.relative_to(ROOT)),
            "rows": int(len(df_en)),
        },
    ]
    pd.DataFrame(rows_a5).to_csv(OUT_DIR / "A5_data_scale_chain.csv", index=False)

    # --- A6 / A7: noise and dev reply ---
    noise_rate = float(df_en["is_noise"].mean()) if "is_noise" in df_en.columns else float("nan")
    dev_reply_rate = float(df_en["has_dev_reply"].mean()) if "has_dev_reply" in df_en.columns else float("nan")
    grp_dev = (
        df_en.groupby("has_dev_reply", observed=True)["score"]
        .agg(["mean", "count"])
        if "has_dev_reply" in df_en.columns
        else pd.DataFrame()
    )
    grp_dev.to_csv(OUT_DIR / "A7_score_by_has_dev_reply.csv")
    pd.DataFrame([{"metric": "noise_rate", "value": noise_rate}, {"metric": "has_dev_reply_rate", "value": dev_reply_rate}]).to_csv(
        OUT_DIR / "A6_A7_quality_flags.csv", index=False
    )

    companion: list[str] = []
    if RAW_METRICS_PACKAGE_XLSX.exists():
        for sheet_try in ("01_raw_collection_metrics", "raw_collection_metrics"):
            try:
                xm = pd.read_excel(RAW_METRICS_PACKAGE_XLSX, sheet_name=sheet_try)
                xm.to_csv(OUT_DIR / "A5_raw_collection_metrics_from_package.csv", index=False)
                companion.append(
                    f"- Raw 指标包：`{RAW_METRICS_PACKAGE_XLSX.relative_to(ROOT)}`（已把 sheet `{sheet_try}` 导出为 `eda_section_a/A5_raw_collection_metrics_from_package.csv`）"
                )
                break
            except (ValueError, KeyError, OSError):
                continue
        if not companion:
            companion.append(
                f"- Raw 指标包：`{RAW_METRICS_PACKAGE_XLSX.relative_to(ROOT)}`（请在 Excel 中查看各 sheet）"
            )
    proc_dict = ROOT / "reports" / "Processed Data dictionary.xlsx"
    if proc_dict.exists():
        companion.append(f"- 处理后字段/指标字典：`{proc_dict.relative_to(ROOT)}`")

    lines = [
        "# EDA Section A — Summary",
        "",
        "## Data sources",
        f"- clean_en_only: `{en_src.relative_to(ROOT)}` ({len(df_en):,} rows)",
        f"- clean_all_languages: `{all_src.relative_to(ROOT)}` ({len(df_all):,} rows)" if len(df_all) else "- clean_all_languages: (missing)",
        f"- raw: `{raw_src.relative_to(ROOT)}` ({len(df_raw):,} rows)" if len(df_raw) else "- raw: (missing)",
        "",
        "## A5 Scale chain",
        "",
        pd.DataFrame(rows_a5).to_string(index=False),
        "",
        "## A6 / A7",
        f"- noise_rate (is_noise): {noise_rate:.4f}",
        f"- has_dev_reply_rate: {dev_reply_rate:.4f}",
        "",
        "## Generated files",
        "",
        "- `A1_rating_distribution.png`, `A1_rating_distribution.csv`",
        "- `A2_rating_counts_by_app.csv`, `A2_mean_score_by_app.csv`, `A2_rating_heatmap_by_app.png`",
        "- `A3_review_length_hist.png`, `A3_length_summary.csv`",
        "- `A4_length_by_rating_boxplot.png`, `A4_length_stats_by_rating.csv`",
        "- `A5_data_scale_chain.csv`",
        "- `A6_A7_quality_flags.csv`, `A7_score_by_has_dev_reply.csv`",
        "",
    ]
    if companion:
        lines += ["## 已补上的整理文档（与 A5 指标链配套）", ""] + companion + [""]
    if missing:
        lines += [
            "## Optional companion files (not found — regenerate if you need exact historical metrics)",
            "",
        ]
        lines += [f"- `{m}`" for m in missing]
        lines.append("")

    (OUT_DIR / "README_eda_section_a.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Done. Output directory: {OUT_DIR}")
    if missing:
        print("Missing optional files:", ", ".join(missing))


if __name__ == "__main__":
    main()
