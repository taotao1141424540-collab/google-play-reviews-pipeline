#!/usr/bin/env python3
"""
Merge EDA section CSV outputs into Excel workbook(s), one sheet per subsection
(e.g. A1–A7 for section A), with multiple CSVs stacked on the same sheet when
a subsection has more than one table (e.g. A2 counts + mean by app).

Prerequisite: run `run_eda_section_*.py` first so CSVs exist under reports/.

Usage (from project root `google play/`):
  python3 scripts/03_eda/merge_eda_csv_to_workbook.py
  python3 scripts/03_eda/merge_eda_csv_to_workbook.py -o reports/custom.xlsx

Writes the combined workbook plus one file per section:
  reports/eda_section_a_workbook.xlsx … reports/eda_section_e_workbook.xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DIR_A = REPORTS / "eda_section_a"
DIR_B = REPORTS / "eda_section_b"
DIR_C = REPORTS / "eda_section_c"
DIR_D = REPORTS / "eda_section_d"
DIR_E = REPORTS / "eda_section_e"

DEFAULT_COMBINED = REPORTS / "eda_sections_workbook.xlsx"


def _safe_sheet(name: str) -> str:
    for c in r"[]:*?/\\":
        name = name.replace(c, "_")
    name = name.strip() or "Sheet"
    return name[:31]


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError):
        return None


def _write_multiblock(writer: pd.ExcelWriter, sheet_name: str, paths: list[Path]) -> bool:
    """Stack CSV tables vertically on one sheet. Returns True if at least one table written."""
    row = 0
    wrote = False
    safe = _safe_sheet(sheet_name)
    for p in paths:
        df = _read_csv(p)
        if df is None:
            continue
        df.to_excel(writer, sheet_name=safe, startrow=row, index=True)
        wrote = True
        row += 1 + len(df) + 2
    return wrote


def _existing(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.is_file()]


def _b3_paths(d: Path) -> list[Path]:
    if (d / "B3_daily_volume.csv").is_file():
        return [d / "B3_daily_volume.csv"]
    if (d / "B3_daily_volume_skip.csv").is_file():
        return [d / "B3_daily_volume_skip.csv"]
    return []


def _b4_paths(d: Path) -> list[Path]:
    out: list[Path] = []
    for name in ("B4_inconsistent_rating_rate.csv", "B4_inconsistent_rating_sample.csv"):
        p = d / name
        if p.is_file():
            out.append(p)
    if not out and (d / "B4_skip.csv").is_file():
        out.append(d / "B4_skip.csv")
    return out


def _c1_paths(d: Path) -> list[Path]:
    if (d / "C1_language_counts.csv").is_file():
        return [d / "C1_language_counts.csv"]
    if (d / "C1_skip.csv").is_file():
        return [d / "C1_skip.csv"]
    return []


def _e1_paths(d: Path) -> list[Path]:
    if (d / "E1_time_anomaly_rate.csv").is_file():
        return [d / "E1_time_anomaly_rate.csv"]
    if (d / "E1_skip.csv").is_file():
        return [d / "E1_skip.csv"]
    return []


def _e2_paths(d: Path) -> list[Path]:
    out: list[Path] = []
    for name in ("E2_spam_bot_suspect_rate.csv", "E2_spam_bot_suspect_sample.csv"):
        p = d / name
        if p.is_file():
            out.append(p)
    if not out and (d / "E2_skip.csv").is_file():
        out.append(d / "E2_skip.csv")
    return out


def _section_a_defs() -> list[tuple[str, list[Path]]]:
    d = DIR_A
    return [
        ("A1", _existing([d / "A1_rating_distribution.csv"])),
        (
            "A2",
            _existing([d / "A2_rating_counts_by_app.csv", d / "A2_mean_score_by_app.csv"]),
        ),
        ("A3", _existing([d / "A3_length_summary.csv"])),
        ("A4", _existing([d / "A4_length_stats_by_rating.csv"])),
        (
            "A5",
            _existing(
                [
                    d / "A5_data_scale_chain.csv",
                    d / "A5_raw_collection_metrics_from_package.csv",
                ]
            ),
        ),
        ("A6", _existing([d / "A6_A7_quality_flags.csv"])),
        ("A7", _existing([d / "A7_score_by_has_dev_reply.csv"])),
    ]


def _section_b_defs() -> list[tuple[str, list[Path]]]:
    d = DIR_B
    return [
        ("B1", _existing([d / "B1_per_app_stats.csv"])),
        ("B2", _existing([d / "B2_score_skew_by_app.csv"])),
        ("B3", _b3_paths(d)),
        ("B4", _b4_paths(d)),
        ("B5", _existing([d / "B5_top_duplicate_text_hashes.csv"])),
    ]


def _section_c_defs() -> list[tuple[str, list[Path]]]:
    d = DIR_C
    return [
        ("C1", _c1_paths(d)),
        ("C2", _existing([d / "C2_english_subset_summary.csv"])),
    ]


def _section_d_defs() -> list[tuple[str, list[Path]]]:
    d = DIR_D
    return [
        ("D1", _existing([d / "D1_top30_words_overall.csv"])),
        ("D2", _existing([d / "D2_top_words_low_vs_high_star.csv"])),
    ]


def _section_e_defs() -> list[tuple[str, list[Path]]]:
    d = DIR_E
    rows: list[tuple[str, list[Path]]] = [
        ("E1", _e1_paths(d)),
        ("E2", _e2_paths(d)),
    ]
    if (d / "E_summary_rates.csv").is_file():
        rows.append(("E_summary", [d / "E_summary_rates.csv"]))
    return rows


def _write_workbook(out_path: Path, sheet_defs: list[tuple[str, list[Path]]]) -> int:
    to_write = [(name, paths) for name, paths in sheet_defs if paths]
    if not to_write:
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_sheets = 0
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, paths in to_write:
            if _write_multiblock(writer, sheet_name, paths):
                wrote_sheets += 1
    if wrote_sheets == 0 and out_path.is_file():
        out_path.unlink()
    return wrote_sheets


def main() -> None:
    p = argparse.ArgumentParser(description="Merge EDA CSV outputs into Excel sheet(s).")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_COMBINED,
        help=f"Combined workbook path (default: {DEFAULT_COMBINED.relative_to(ROOT)})",
    )
    args = p.parse_args()

    combined_defs: list[tuple[str, list[Path]]] = (
        _section_a_defs() + _section_b_defs() + _section_c_defs() + _section_d_defs() + _section_e_defs()
    )

    n = _write_workbook(args.output.resolve(), combined_defs)
    if n:
        print(f"Wrote {n} sheet(s) -> {args.output.resolve()}")
    else:
        print("No EDA CSVs found; run run_eda_section_*.py first. No file written.")

    sections: list[tuple[Path, list[tuple[str, list[Path]]]]] = [
        (REPORTS / "eda_section_a_workbook.xlsx", _section_a_defs()),
        (REPORTS / "eda_section_b_workbook.xlsx", _section_b_defs()),
        (REPORTS / "eda_section_c_workbook.xlsx", _section_c_defs()),
        (REPORTS / "eda_section_d_workbook.xlsx", _section_d_defs()),
        (REPORTS / "eda_section_e_workbook.xlsx", _section_e_defs()),
    ]
    for path, defs in sections:
        m = _write_workbook(path, defs)
        if m:
            print(f"Wrote {m} sheet(s) -> {path.resolve()}")


if __name__ == "__main__":
    main()
