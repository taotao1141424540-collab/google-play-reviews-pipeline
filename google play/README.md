# Google Play Reviews Pipeline — README (aligned with this repo)

**Chinese version:** [`README_CN.md`](README_CN.md)

This document mirrors the layout of **`google play/`** as it exists on disk: script layers, paths, and the recommended run order.

---

## 1. Repository layout (root)

```
google play/
├── README.md                    # This file
├── README_CN.md                 # Chinese README
├── .mplconfig/                  # Matplotlib cache (set MPLCONFIGDIR when plotting in EDA)
├── config/
│   ├── README.md                # Column descriptions for app_list
│   ├── app_list.xlsx            # Apps to scrape (required: app_id)
│   └── monitoring.yml           # Monitoring thresholds & drift params (`07_monitor`)
├── logs/                        # Runtime: `pipeline_runs.jsonl` (written by `07_monitor` scripts)
├── data/
│   ├── raw/
│   │   └── google_play_reviews_raw.csv    # Scraper output (default)
│   ├── processed/
│   │   ├── clean_all_languages.csv        # Clean: all languages
│   │   ├── clean_en_only.csv              # Clean: English only
│   │   ├── clean_en_time_window.csv       # Optional: time-window sampling output
│   │   └── time_window_sampling_manifest.json  # Optional: sampling run metadata
│   └── warehouse/
│       ├── play_reviews.db                # SQLite: default (full-dataset load)
│       └── play_reviews_en.db             # SQLite: --english-only load
├── docs/
│   ├── export_spike_days_readme.md        # Spike table documentation
│   ├── spike_dates_top10.csv              # Top-N spike days (from export_spike_days)
│   ├── sqlite_verification_results.txt    # Verification report (full DB)
│   └── sqlite_verification_results_en.txt # Verification report (English DB)
├── reports/
│   ├── collection_summary.md
│   ├── raw_collection_metrics.csv
│   ├── quality_report.csv                 # Layered quality metrics (p0/p1/p2)
│   ├── monitoring/                      # Runtime: metric history, alerts, report (`07_monitor`)
│   ├── eda_sections_workbook.xlsx         # All EDA sheets (merge script)
│   ├── eda_section_a_workbook.xlsx … e   # Per-section workbooks
│   ├── EDA_Conclusion_Bilingual.pptx / .pdf   # Deck (04_export)
│   └── eda_section_{a,b,c,d,e}/         # Per-section CSVs, PNGs, mini READMEs
├── scripts/
│   ├── 01_collect/collect_reviews.py
│   ├── 02_clean/clean_and_eda.py
│   ├── 03_eda/run_eda_section_{a,b,c,d,e}.py
│   ├── 03_eda/merge_eda_csv_to_workbook.py
│   ├── 04_export/build_eda_conclusion_deck.py
│   ├── 05_warehouse/
│   │   ├── load_to_sqlite.py
│   │   └── run_sqlite_verification.py
│   ├── 06_insights/
│   │   ├── export_spike_days.py
│   │   └── apply_time_window_sampling.py
│   └── 07_monitor/
│       ├── collect_run_metrics.py
│       ├── check_drift_and_alerts.py
│       ├── _runlog.py
│       └── smoke_runlog.py
└── sql/
    ├── schema.sql               # DDL (executed inside load_to_sqlite)
    └── verify.sql               # Ad-hoc CLI checks (see below)
```

Notes:

- **`run_sqlite_verification.py`** lives under `scripts/05_warehouse/` (see §6).
- **`logs/`** and **`reports/monitoring/`** are created when you run **`scripts/07_monitor/`** (see §4.3); they may be absent in a fresh clone until then.
- There is **no** `templates/`, **no** `scripts/README.md`, **no** `docs/time_window_sampling_note.md` in this tree by default (you can add a long-form time-window strategy note under `docs/` if needed; spike + sampling scripts still work standalone).
- **`scripts/01_collect/.idea/`** is IDE metadata and can be ignored.

---

## 2. Cleaning layers (`clean_and_eda.py`)

Layers align with the **`section`** field in **`reports/quality_report.csv`**:

| Layer | Meaning (short) |
|--------|------------------|
| **P0** | Dedupe on `review_id`, drop empty / too-short text, parseable time and score, etc. |
| **P1** | Language detection (`langdetect`), noise flags |
| **P2** | Missing key fields, star vs keyword sentiment mismatch, hourly-bucket anomalies, suspected spam patterns |

Main outputs: **`clean_all_languages.csv`** (post-P0, all languages) and **`clean_en_only.csv`** (rows with `is_en` true).

---

## 3. Scripts by folder

| Folder | Script | Role |
|--------|--------|------|
| **`scripts/01_collect/`** | `collect_reviews.py` | Read `config/app_list.xlsx`, scrape → `data/raw/google_play_reviews_raw.csv`, plus collection summary + raw metrics |
| **`scripts/02_clean/`** | `clean_and_eda.py` | Read raw CSV → layered cleaning → `processed/` tables + `reports/quality_report.csv` |
| **`scripts/03_eda/`** | `run_eda_section_a.py` … `run_eda_section_e.py` | Modular plots + CSVs → `reports/eda_section_*/` |
| **`scripts/03_eda/`** | `merge_eda_csv_to_workbook.py` | Merge section CSVs → `reports/eda_sections_workbook.xlsx` + **`eda_section_{a–e}_workbook.xlsx`** |
| **`scripts/04_export/`** | `build_eda_conclusion_deck.py` | Bilingual **PPT/PDF** → `reports/EDA_Conclusion_Bilingual.*` |
| **`scripts/05_warehouse/`** | `load_to_sqlite.py` | Run `sql/schema.sql` then load rows; supports default full load or **`--english-only`** → `play_reviews_en.db` |
| **`scripts/05_warehouse/`** | `run_sqlite_verification.py` | Query DB → **`docs/sqlite_verification_results*.txt`**; use **`--both`** to verify both databases |
| **`scripts/06_insights/`** | `export_spike_days.py` | Read **`reports/eda_section_b/B3_daily_volume.csv`** → **`docs/spike_dates_top10.csv`** |
| **`scripts/06_insights/`** | `apply_time_window_sampling.py` | Optional: spike-day removal / per-day cap / time split on `clean_en_only` |
| **`scripts/07_monitor/`** | `collect_run_metrics.py` | After upstream reports exist: append **`reports/monitoring/data_quality_history.csv`** + **`distribution_history.csv`** |
| **`scripts/07_monitor/`** | `check_drift_and_alerts.py` | Read config + histories + SQLite: **`reports/monitoring/alerts.csv`**, **`monitoring_report.md`**; exit **`1`** if any ERROR |
| **`scripts/07_monitor/`** | `_runlog.py`, `smoke_runlog.py` | Run-level JSONL logging + small self-test for the log writer |

---

## 4. Recommended run order and dependencies

Run from the **`google play/`** root with your venv activated.

### 4.1 Environment (example)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pandas openpyxl google-play-scraper langdetect matplotlib python-pptx reportlab pyyaml
export MPLCONFIGDIR="$(pwd)/.mplconfig" && mkdir -p .mplconfig
```

### 4.2 Main pipeline

| Step | Command | Requires |
|------|---------|----------|
| 1 | `python3 scripts/01_collect/collect_reviews.py` | `config/app_list.xlsx` |
| 2 | `python3 scripts/02_clean/clean_and_eda.py` | `data/raw/google_play_reviews_raw.csv` |
| 3 | `python3 scripts/03_eda/run_eda_section_a.py` | Clean `data/processed/` (scripts may prefer `.xlsx` if present, else `.csv`) |
|  | `python3 scripts/03_eda/run_eda_section_b.py` | Same |
|  | … `c`, `d`, `e` | Same |
| 4 | `python3 scripts/03_eda/merge_eda_csv_to_workbook.py` | Section CSVs under `reports/eda_section_*` |
| 5 | `python3 scripts/04_export/build_eda_conclusion_deck.py` | Optional; paths inside script |
| 6 | `python3 scripts/06_insights/export_spike_days.py` | **After Section B**: needs `B3_daily_volume.csv` |
| 7 | `python3 scripts/05_warehouse/load_to_sqlite.py` | `processed/` csv/xlsx |
| 8 | `python3 scripts/05_warehouse/load_to_sqlite.py --english-only` | Same (writes separate English DB) |
| 9 | `sqlite3 data/warehouse/play_reviews.db < sql/verify.sql` | Optional manual check |
|  | `sqlite3 data/warehouse/play_reviews_en.db < sql/verify.sql` | Same for English DB |
| 10 | `python3 scripts/05_warehouse/run_sqlite_verification.py --both` | Both `.db` files exist |
| 11 | `python3 scripts/06_insights/apply_time_window_sampling.py …` | Optional; see `--help` |
| 12 | `python3 scripts/07_monitor/collect_run_metrics.py` | After §4.2 steps 1–4 (or full run): appends `reports/monitoring/*_history.csv` |
| 13 | `python3 scripts/07_monitor/check_drift_and_alerts.py` | After step 12: writes `alerts.csv`, `monitoring_report.md`; exit `1` if any ERROR |

**Do not run `sql/schema.sql` alone for normal workflow:** `load_to_sqlite.py` applies it via `executescript(schema.sql)` after connecting.

### 4.3 Monitoring (`scripts/07_monitor/`)

Read-only over pipeline outputs. Thresholds in `config/monitoring.yml`. Typical order after a successful run:

```bash
python3 scripts/07_monitor/collect_run_metrics.py
python3 scripts/07_monitor/check_drift_and_alerts.py
echo "exit=$?"
```

See `monitoring layer设计方案/monitoring_impl_spec_en.md` for full behavior.

---

## 5. EDA outputs (typical files in this repo)

Each `eda_section_*` folder also has **`README_eda_section_*.md`**.

| Folder | Examples |
|--------|-----------|
| `eda_section_a/` | Rating distributions, per-app scores, lengths, `A5_data_scale_chain.csv`, quality flags — CSV + PNG |
| `eda_section_b/` | App stats, skew, **`B3_daily_volume.csv/png`** (needed for spike export), inconsistent-rating samples |
| `eda_section_c/` | Language counts, English subset summary |
| `eda_section_d/` | Word-frequency CSV + PNG |
| `eda_section_e/` | Time-anomaly rate, suspected spam rate, etc. |

Workbooks: **`eda_sections_workbook.xlsx`** (all sections) and **`eda_section_*_workbook.xlsx`** (one section per file).

---

## 6. Docs and verification artifacts (`docs/`)

| File | Produced by |
|------|-------------|
| `export_spike_days_readme.md` | Maintained manually; describes spike CSV + script |
| `spike_dates_top10.csv` | `export_spike_days.py` (default Top 10; `--top N`) |
| `sqlite_verification_results.txt` | `run_sqlite_verification.py` (default full DB) |
| `sqlite_verification_results_en.txt` | Same with `--both` or `--en-db` |

---

## 7. Copy-paste: full skeleton

```bash
source .venv/bin/activate
python3 scripts/01_collect/collect_reviews.py
python3 scripts/02_clean/clean_and_eda.py
for s in a b c d e; do python3 "scripts/03_eda/run_eda_section_${s}.py"; done
python3 scripts/03_eda/merge_eda_csv_to_workbook.py
python3 scripts/04_export/build_eda_conclusion_deck.py
python3 scripts/06_insights/export_spike_days.py
python3 scripts/05_warehouse/load_to_sqlite.py
python3 scripts/05_warehouse/load_to_sqlite.py --english-only
python3 scripts/05_warehouse/run_sqlite_verification.py --both
python3 scripts/07_monitor/collect_run_metrics.py
python3 scripts/07_monitor/check_drift_and_alerts.py
```

Run **`apply_time_window_sampling.py`** when needed (see in-script examples).

---

## 8. Deliverables quick reference

| Kind | Paths |
|------|--------|
| Raw / clean | `data/raw/*.csv`, `data/processed/*.csv`, `reports/quality_report.csv` |
| Collection | `reports/collection_summary.md`, `reports/raw_collection_metrics.csv` |
| EDA | `reports/eda_section_*`, `reports/eda_*workbook*.xlsx` |
| Deck | `reports/EDA_Conclusion_Bilingual.pptx`, `reports/EDA_Conclusion_Bilingual.pdf` |
| Spikes | `docs/spike_dates_top10.csv`, `docs/export_spike_days_readme.md` |
| Warehouse | `data/warehouse/play_reviews.db`, `play_reviews_en.db` |
| Verification text | `docs/sqlite_verification_results*.txt` |
| Monitoring | `reports/monitoring/*_history.csv`, `alerts.csv`, `monitoring_report.md`, `logs/pipeline_runs.jsonl` |
| Modeling subset (if run) | `data/processed/clean_en_time_window.csv`, `time_window_sampling_manifest.json` |

---

## 9. Reproducibility (fresh clone → full outputs)

### Data access

**Full datasets are not distributed with this repository.** Generated paths under **`data/raw/`**, **`data/processed/`**, and **`data/warehouse/`** are excluded by **`.gitignore`** so the repo stays small. **After you clone:** fill **`config/app_list.xlsx`**, then **run scraping first** — `python3 scripts/01_collect/collect_reviews.py` — and continue in pipeline order (**`02_clean` → `03_eda` → …**, see **§7**) to recreate all CSV/SQLite outputs.

Anyone cloning this repo can rebuild the pipeline end-to-end if they follow the same steps:

1. **Clone** the repository.
2. **Python environment:** use Python **3.10+** (3.9+ usually works). Create a venv and install packages listed in **§4.1** (`pandas`, `openpyxl`, `google-play-scraper`, `langdetect`, `matplotlib`, `python-pptx`, `reportlab`).
3. **`config/app_list.xlsx`:** prepare the app list per **`config/README.md`** (required column `app_id`). Scraping needs **network** access; runtime scales with `target_reviews`.
4. **Same as Data access:** confirm **`data/`** appears empty or missing large files until you run **`01_collect`** onward (**§7** skeleton).
5. **Random seeds:** CLI flags such as **`--random-state`** (e.g. `apply_time_window_sampling.py`) keep downsampling reproducible; raw row counts still depend on **when** you scrape and on third-party APIs.
6. **Frozen snapshots (optional):** For mentor review without re-scraping, zip a dated `data/` snapshot or attach it to **GitHub Releases** / cloud storage and paste the download URL here (same **Data access** topic as §10).

---

## 10. Git and large files

Prefer **`.gitignore`** for large **`data/`** CSVs, **`data/warehouse/*.db`**, bulky xlsx; ship samples in-repo and host full dumps via cloud / Releases with a documented link (see **§9**).

---

## 11. Limitations and compliance

- **`google-play-scraper`** is unofficial; upstream changes may break scraping or fields.  
- **`langdetect`** is heuristic; short text may be unstable.  
- Section **E** flags are rule-based, not ground truth.  
- Daily **spikes** may mix real traffic and crawl timing—interpret with B3 + `spike_dates_top10.csv`.  
- Comply with **Google Play Terms of Service**, course rules, and mentor policies.
