#!/usr/bin/env python3
"""
EDA Section D — light text (word frequency).

Input:
  data/processed/clean_en_only.xlsx (or .csv)

Output:
  reports/eda_section_d/
"""

from __future__ import annotations

import os
import re
from collections import Counter
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
OUT_DIR = ROOT / "reports" / "eda_section_d"

# Minimal English stopword list (no NLTK dependency).
_STOP = frozenset(
    "a an the and or but if in on at to for of as by with from is are was were be been being "
    "it its this that these those i you he she we they what which who whom my your his her "
    "our their me him us them do does did doing have has had having will would could should "
    "may might must not no yes so than then too very can just about into through over after "
    "before between under again further once here there when where why how all both each few "
    "more most other some such only own same so than too very s just don doesn did wasn werent "
    "im ive id ill lets get got go going gone app apps one two also like just even much way "
    "use used using make made out up down off back well really still ever every never ever "
    "because since while though although unless until although".split()
)


def load_clean_en() -> pd.DataFrame:
    if CLEAN_EN_XLSX.exists():
        return pd.read_excel(CLEAN_EN_XLSX)
    if CLEAN_EN_CSV.exists():
        return pd.read_csv(CLEAN_EN_CSV)
    raise FileNotFoundError(f"Missing {CLEAN_EN_XLSX} and {CLEAN_EN_CSV}")


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z]{2,}", str(text).lower()) if w not in _STOP]


def top_words(series: pd.Series, top_k: int = 30) -> pd.Series:
    c: Counter[str] = Counter()
    for t in series.dropna():
        c.update(tokenize(t))
    return pd.Series(dict(c.most_common(top_k)), name="count")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_clean_en()
    col = "content_clean" if "content_clean" in df.columns else "content"

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # --- D1: top 30 words (English subset) ---
    top30 = top_words(df[col], 30)
    top30.rename_axis("token").to_csv(OUT_DIR / "D1_top30_words_overall.csv")

    fig, ax = plt.subplots(figsize=(10, 8))
    top30.sort_values().plot(kind="barh", ax=ax, color="#8C564B")
    ax.set_xlabel("Count")
    ax.set_title("D1: Top 30 tokens (clean_en, stopwords removed, len>=2)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "D1_top30_words_overall.png", dpi=150)
    plt.close(fig)

    # --- D2: 1–2 stars vs 5 stars ---
    low = df[df["score"].isin([1, 2])][col]
    high = df[df["score"] == 5][col]
    top_low = top_words(low, 25) if len(low) else pd.Series(dtype=int)
    top_high = top_words(high, 25) if len(high) else pd.Series(dtype=int)
    comp = pd.DataFrame({"low_star_1_2": top_low, "high_star_5": top_high})
    comp.to_csv(OUT_DIR / "D2_top_words_low_vs_high_star.csv")

    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    if len(top_low):
        top_low.sort_values().plot(kind="barh", ax=axes[0], color="#C44E52")
    axes[0].set_title(f"D2: Top tokens — scores 1–2 (n={len(low):,})")
    if len(top_high):
        top_high.sort_values().plot(kind="barh", ax=axes[1], color="#55A868")
    axes[1].set_title(f"D2: Top tokens — score 5 (n={len(high):,})")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "D2_top_words_low_vs_high_star.png", dpi=150)
    plt.close(fig)

    readme = """# EDA Section D

## Outputs
- `D1_top30_words_overall.csv`, `D1_top30_words_overall.png`
- `D2_top_words_low_vs_high_star.csv`, `D2_top_words_low_vs_high_star.png`

## Re-run
```bash
python3 "google play/scripts/03_eda/run_eda_section_d.py"
```
"""
    (OUT_DIR / "README_eda_section_d.md").write_text(readme, encoding="utf-8")
    print(f"Done. Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
