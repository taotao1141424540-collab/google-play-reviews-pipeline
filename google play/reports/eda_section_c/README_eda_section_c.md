# EDA Section C — Summary

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
