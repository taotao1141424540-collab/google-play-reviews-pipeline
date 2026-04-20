#!/usr/bin/env python3
"""
EDA Section C — language composition & English subset justification.

Inputs:
  data/processed/clean_all_languages.xlsx  (or .csv)
  reports/quality_report.csv  (optional, for C2 layered rate)

Output:
  reports/eda_section_c/
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
CLEAN_ALL_XLSX = ROOT / "data" / "processed" / "clean_all_languages.xlsx"
CLEAN_ALL_CSV = ROOT / "data" / "processed" / "clean_all_languages.csv"
QUALITY_CSV = ROOT / "reports" / "quality_report.csv"
OUT_DIR = ROOT / "reports" / "eda_section_c"

# ISO-style codes from langdetect → English display names (for plots & CSV).
LANG_NAME_EN: dict[str, str] = {
    "en": "English",
    "af": "Afrikaans",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian (Farsi)",
    "fi": "Finnish",
    "fr": "French",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "mr": "Marathi",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "so": "Somali",
    "sq": "Albanian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Tagalog",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "unknown": "Unknown (undetected or too short)",
}


def lang_code_to_english(code: str) -> str:
    c = str(code).strip().lower().replace("_", "-")
    return LANG_NAME_EN.get(c, f"Other language ({c})")


def load_clean_all() -> pd.DataFrame:
    if CLEAN_ALL_XLSX.exists():
        return pd.read_excel(CLEAN_ALL_XLSX)
    if CLEAN_ALL_CSV.exists():
        return pd.read_csv(CLEAN_ALL_CSV)
    raise FileNotFoundError(f"Missing {CLEAN_ALL_XLSX} and {CLEAN_ALL_CSV}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_clean_all()

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # --- C1: language composition ---
    if "detected_lang" not in df.columns:
        pd.DataFrame([{"error": "detected_lang column missing"}]).to_csv(OUT_DIR / "C1_skip.csv", index=False)
    else:
        lang_code = df["detected_lang"].fillna("unknown").astype(str).str.strip()
        vc_code = lang_code.value_counts()
        out_tbl = pd.DataFrame(
            {
                "detected_lang_code": vc_code.index.astype(str),
                "count": vc_code.values.astype(int),
            }
        )
        out_tbl["language_name_en"] = out_tbl["detected_lang_code"].map(lang_code_to_english)
        out_tbl = out_tbl[["language_name_en", "count", "detected_lang_code"]]
        out_tbl.to_csv(OUT_DIR / "C1_language_counts.csv", index=False)

        vc = out_tbl.groupby("language_name_en", as_index=True)["count"].sum().sort_values(ascending=False)
        top_n = 15
        tail = int(vc.iloc[top_n:].sum()) if len(vc) > top_n else 0
        plot_vc = vc.head(top_n).copy()
        if tail > 0:
            plot_vc = pd.concat([plot_vc, pd.Series({"Other (remaining languages)": tail})])

        fig, axes = plt.subplots(1, 2, figsize=(14, 7))
        labels = plot_vc.index.astype(str)
        axes[0].barh(labels[::-1], plot_vc.values[::-1], color="#64B5CD")
        axes[0].set_xlabel("Count")
        axes[0].set_title("C1: Top languages by review count (English names)")
        pie_labels = list(labels)
        axes[1].pie(
            plot_vc.values,
            labels=pie_labels,
            autopct="%1.1f%%",
            pctdistance=0.75,
            textprops={"fontsize": 7},
        )
        axes[1].set_title("C1: Share (top languages + Other)")
        fig.tight_layout()
        fig.savefig(OUT_DIR / "C1_language_distribution.png", dpi=150)
        plt.close(fig)

    # --- C2: English subset share ---
    rows_c2: list[dict[str, object]] = []
    if "is_en" in df.columns:
        en_rate_data = float(df["is_en"].fillna(False).mean())
        rows_c2.append(
            {
                "metric": "english_share_on_clean_all",
                "value": round(en_rate_data, 6),
                "source": "computed from clean_all_languages (mean of is_en)",
                "n_rows": len(df),
            }
        )
    if QUALITY_CSV.exists():
        q = pd.read_csv(QUALITY_CSV)
        for _, r in q.iterrows():
            if str(r.get("metric", "")).strip() in (
                "english_rate_after_p0",
                "clean_en_rows",
                "clean_all_rows",
                "raw_rows",
            ):
                rows_c2.append(
                    {
                        "metric": r.get("metric"),
                        "value": r.get("value"),
                        "source": "quality_report.csv",
                        "n_rows": "",
                    }
                )
    if not rows_c2:
        rows_c2.append({"metric": "note", "value": "No is_en column and no quality_report.csv", "source": "", "n_rows": ""})
    pd.DataFrame(rows_c2).to_csv(OUT_DIR / "C2_english_subset_summary.csv", index=False)

    readme = """# EDA Section C — Summary

## C 项说明（见对话或下方「各 C 项意义」）

## 输入
- `data/processed/clean_all_languages.xlsx`（或 `.csv`）
- 可选：`reports/quality_report.csv`

## 产出
- `C1_language_counts.csv` — `language_name_en`（英文全称）、`count`、`detected_lang_code`
- `C1_language_distribution.png` — 条形图 + 饼图（Top15 其余合并为 Other，标签为英文全称）
- `C2_english_subset_summary.csv` — 英文占比（数据内计算）+ 若有则附 `quality_report` 中的相关行

## 复跑
```bash
python3 "google play/scripts/03_eda/run_eda_section_c.py"
```
"""
    (OUT_DIR / "README_eda_section_c.md").write_text(readme, encoding="utf-8")
    print(f"Done. Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
