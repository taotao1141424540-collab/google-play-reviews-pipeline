# Monitoring Layer — Implementation Spec (EN)

> Companion to: `monitoring_design_mentor.md` (design doc)
> Scope of this doc: **how the design lands in code**. Audience: myself, code reviewer.
> Version: v1 (MVP · observe-only, non-blocking) · Author: Chuantao

---

## 0. Relationship

| Doc | What it answers |
|-----|-----------------|
| `monitoring_design_mentor.md` | **Why / what / thresholds** (design, contracts) |
| **This doc (Impl Spec)** | **Where the code lives, function signatures, data contracts, how to validate** |

This spec does **not** re-argue the business rationale. It answers 5 questions:
1. Which directories / files get added.
2. The **data contracts** of the two monitor scripts (inputs, outputs, column sets).
3. Key function signatures & error handling.
4. Field semantics for `monitoring.yml`.
5. How to validate locally and wire it into CI later.

---

## 1. File Layout

**No changes** to business scripts 01–06. **Tracked source** for monitoring includes:

- **`config/monitoring.yml`**
- **Five** `.py` files under **`scripts/07_monitor/`**: `__init__.py`, `_runlog.py`, `collect_run_metrics.py`, `check_drift_and_alerts.py`, `smoke_runlog.py` (optional local smoke test for JSONL).
- **`requirements.txt`** gains **`pyyaml>=6.0`** (alongside existing deps).

**`logs/`** and **`reports/monitoring/`** are created at runtime. This repo’s root **`.gitignore`** ignores `google play/logs/` and `google play/reports/monitoring/` by default — clones will not contain history/alerts until you run the scripts.

```
google play/
├── config/
│   └── monitoring.yml                          # NEW  thresholds, drift params, mutes
├── logs/                                       # RUNTIME dir
│   └── pipeline_runs.jsonl                     # one JSON line per monitored `main` (run_logger)
├── reports/
│   └── monitoring/                             # RUNTIME dir
│       ├── data_quality_history.csv            # RUNTIME append
│       ├── distribution_history.csv            # RUNTIME append
│       ├── alerts.csv                          # RUNTIME append
│       └── monitoring_report.md                # RUNTIME overwrite
└── scripts/
    └── 07_monitor/
        ├── __init__.py
        ├── _runlog.py                          # run_logger → JSONL
        ├── collect_run_metrics.py              # aggregate → history; main wrapped with run_logger
        ├── check_drift_and_alerts.py           # compare → alerts + report; main wrapped with run_logger
        └── smoke_runlog.py                     # optional smoke for _runlog
```

**Design principles (as enforced by the layout):**
- Monitor code is **read-only** against business artifacts.
- All monitor outputs live under `logs/` or `reports/monitoring/`, strictly separated from business outputs.
- No third-party daemon / service; pure file I/O + stdlib + `pandas` + `pyyaml` (see §6 for a JSON fallback).

---

## 2. Data Contracts

### 2.1 Upstream inputs (already produced by 01–06)

| Artifact (relative to `google play/`) | Reader | Required columns / keys | If missing |
|---|---|---|---|
| `reports/raw_collection_metrics.csv` | `collect_run_metrics.py` | `raw_rows, apps_count` | Write NaN, continue |
| `reports/quality_report.csv` | `collect_run_metrics.py` | P0 / P1 / P2 metrics | Write NaN, continue |
| `reports/eda_section_a/A1_rating_distribution.csv` | same | `score, count` | Leave empty |
| `reports/eda_section_a/A3_length_summary.csv` | same | `mean, p50, p90` | Leave empty |
| `reports/eda_section_b/B3_daily_volume.csv` | same | `date, reviews` | Leave empty |
| `reports/eda_section_c/C2_english_subset_summary.csv` | same | `english_share` (or equiv.) | Leave empty |

> **Key contract**: **`collect_run_metrics`** writes **NaN / empty** when upstream files are missing — it does **not** append to `alerts.csv`. **`check_drift_and_alerts`** **WARN**s and exits early if **DQ history** is missing/empty. **ERROR** still means **threshold violations** or **SQLite row mismatch**, not “some upstream business CSV was absent”.

### 2.2 Outputs (produced by the monitor)

#### `logs/pipeline_runs.jsonl` (one JSON per line)

```json
{
  "run_id": "2026-04-22T10:33:12Z_collect",
  "script": "scripts/01_collect/collect_reviews.py",
  "args": "--config config/app_list.xlsx",
  "start_utc": "2026-04-22T10:33:12Z",
  "end_utc": "2026-04-22T10:41:05Z",
  "duration_sec": 473,
  "status": "success",
  "exception": null,
  "rows_in": null,
  "rows_out": 12043,
  "output_files": ["data/raw/google_play_reviews_raw.csv"],
  "git_sha": "a9c3f01"
}
```

- `run_id` = `{iso8601}_{script_basename_without_ext}`.
- On failure: append one row with `status=failed, exception=<str>`, then **re-raise**.
- `rows_in` / `rows_out` may be `null` (e.g. EDA scripts).

#### `reports/monitoring/data_quality_history.csv` (wide table, append-only)

Column order fixed:

```
run_ts, raw_rows, apps_count,
duplicate_rate, empty_text_rate, short_text_rate_lt5,
parseable_time_rate, parseable_score_rate,
english_rate_after_p0, noise_rate_after_p0,
missing_key_fields_rate, inconsistent_rating_rate,
time_anomaly_rate, spam_bot_suspect_rate,
clean_all_rows, clean_en_rows
```

#### `reports/monitoring/distribution_history.csv`

```
run_ts,
score_1_pct, score_2_pct, score_3_pct, score_4_pct, score_5_pct,
len_mean, len_p50, len_p90,
en_share,
last7d_reviews_sum, last7d_daily_mean
```

#### `reports/monitoring/alerts.csv` (append-only)

```
run_ts, level, metric, current, baseline_or_threshold, rule, message
```

- `level ∈ {INFO, WARN, ERROR}`
- `rule` includes threshold/drift: `threshold_max`, `threshold_min`, `psi_max`, `zscore_max`, `spike_ratio`, `eq`; plus degradation/metadata such as **`cold_start`**, **`missing`**, **`empty`**, **`parse_error`**, **`unknown_subset`**, `mismatch`, etc. (see code — not an exhaustive closed set).

#### `reports/monitoring/monitoring_report.md`

**Overwritten** each run — only the latest run is kept here. Template aligned with `monitoring_design_mentor.md §4.4`.

---

## 3. Module API

> Python ≥ 3.10; deps: stdlib + `pandas` (already used) + `pyyaml` (new; can be swapped for JSON).

### 3.1 `_runlog.py`

```python
from contextlib import contextmanager

@contextmanager
def run_logger(
    script: str,
    args: str = "",
    rows_in: int | None = None,
    output_files: list[str] | None = None,
    log_path: str = "logs/pipeline_runs.jsonl",
) -> "RunContext":
    """
    Context manager. Inside the with block:
      - Records start_utc / end_utc / duration_sec
      - On exception: status='failed', exception=str(e), then re-raise
      - On success:   status='success'
    Callers can enrich via ctx.set_rows_out(n) / ctx.add_output(path).
    """
```

**Usage** (Phase 2 only; MVP does not require touching business scripts):

```python
from scripts._runlog import run_logger

with run_logger(script=__file__, args=" ".join(sys.argv[1:])) as ctx:
    df = collect(...)
    ctx.set_rows_out(len(df))
    ctx.add_output("data/raw/google_play_reviews_raw.csv")
```

### 3.2 `collect_run_metrics.py`

```python
def load_quality_report(path: str = "reports/quality_report.csv") -> dict[str, float]: ...
def load_raw_metrics(path: str = "reports/raw_collection_metrics.csv") -> dict[str, float]: ...
def load_distribution_metrics(base: str = "reports") -> dict[str, float]: ...

def append_history(row: dict, out_path: str) -> None:
    """
    If out_path doesn't exist → create with header; else append, preserving column order.
    Missing fields are written as NaN; never reorder.
    """

def main() -> int:
    """Exit code: always 0 (aggregation only; no judgments here)."""
```

**CLI**: `python scripts/07_monitor/collect_run_metrics.py`

### 3.3 `check_drift_and_alerts.py`

```python
def load_config(path: str = "config/monitoring.yml") -> dict: ...

def check_hard_thresholds(latest: pd.Series, thresholds: dict) -> list[Alert]: ...
def check_drift(latest: pd.Series, history: pd.DataFrame, drift_cfg: dict) -> list[Alert]: ...

def write_alerts(alerts: list[Alert], out_path: str) -> None: ...     # append
def write_report(alerts: list[Alert], latest: pd.Series, out_path: str) -> None: ...  # overwrite

def main() -> int:
    """
    Exit code (MVP):
      - any ERROR  → 1
      - otherwise  → 0
    """
```

**PSI (rating distribution)**:

```python
def psi(p: np.ndarray, q: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(p, eps, None); q = np.clip(q, eps, None)
    return float(np.sum((p - q) * np.log(p / q)))
```

**Cold start**:

```python
if len(history) < drift_cfg["baseline_window"]:
    return []   # run hard thresholds only
```

### 3.4 Alert dataclass

```python
@dataclass
class Alert:
    run_ts: str
    level: str                 # INFO / WARN / ERROR
    metric: str
    current: float | None
    baseline_or_threshold: float | None
    rule: str                  # threshold_max / psi_max / ...
    message: str
```

---

## 4. Alert Rule Matrix (code-level)

### 4.1 Hard thresholds → ERROR

| Metric | Rule | YAML key |
|--------|------|----------|
| `raw_rows` | `< raw_rows_min` | `thresholds.raw_rows_min` |
| `apps_count` | `< expected.apps_count - thresholds.apps_count_min_delta` | same |
| `duplicate_rate` | `> duplicate_rate_max` | same |
| `empty_text_rate` | `> empty_text_rate_max` | same |
| `parseable_time_rate` | `< parseable_time_rate_min` | same |
| `parseable_score_rate` | `< parseable_score_rate_min` | same |
| `english_rate_after_p0` | `< english_rate_min` | same |
| `clean_en_rows` | `< clean_en_rows_min` | same |
| `missing_key_fields_rate` | `> missing_key_fields_rate_max` | same |

### 4.2 Drift → WARN

| Metric | Rule | YAML key |
|--------|------|----------|
| Rating distribution | `PSI(score_pct_vec, mean(history[-N:])) > psi_rating_max` | `drift.psi_rating_max` |
| Length mean | `|z(len_mean)| > zscore_len_mean_max` | `drift.zscore_len_mean_max` |
| Daily volume | `last7d_daily_mean / hist_daily_mean > daily_volume_spike_ratio` | `drift.daily_volume_spike_ratio` |
| English share drop | `baseline_mean(en_share) - current > en_share_drop_max` | `drift.en_share_drop_max` |

### 4.3 Non-critical hard checks → WARN

Design-doc metrics that are not delivery red-lines (e.g. `short_text_rate_lt5`) use the same comparison logic but emit `level=WARN`.

---

## 5. `monitoring.yml` Semantics

Full template: see design doc §6. Here is the **loading contract**:

```python
# Merge: for each top-level key present in the YAML file, update the built-in DEFAULTS
# (omitted keys keep their defaults). If the file is missing or PyYAML fails, use DEFAULTS
# as-is and emit a config_file WARN.

DEFAULTS = {
    "thresholds": {...},  # mirror design doc §6
    "drift":      {...},
    "expected":   {"apps_count": 14},  # align with repo monitoring.yml; fallback if yml missing
    "mute":       [],
}
```

**Mute semantics**:

```yaml
mute:
  - metric: last7d_daily_mean
    until: 2026-05-01      # ISO date, auto-expires
    reason: "campaign launch"
```

Muted metrics are **still computed and written to history**; they just produce no alert and do not affect the exit code.

---

## 6. Dependencies

| Component | Choice | Why |
|-----------|--------|-----|
| Python | ≥ 3.10 | Matches existing scripts |
| pandas | existing | CSV I/O |
| numpy | existing | PSI / z-score |
| pyyaml | **new** (optional) | loads `monitoring.yml` |

> **JSON fallback**: rename the config to `monitoring.json` and `json.load` directly — identical schema, no new dep.

`requirements.txt` adds:

```
pyyaml>=6.0
```

---

## 7. Error Handling & Degradation

| Situation | Behavior |
|-----------|----------|
| Upstream CSV missing (`collect_run_metrics`) | Write **NaN** for affected columns; **no** `alerts.csv` row for “file missing” (collect does not write alerts) |
| `data_quality_history.csv` missing or empty | `check_drift_and_alerts`: **WARN** (`metric=data_quality_history`, rule=`missing` / `empty`), **early exit** code `0` — no hard thresholds / SQLite / drift |
| `distribution_history.csv` missing or empty | **WARN** (`metric=distribution_history`, rule=`missing`); skip drift block; hard thresholds still run |
| `distribution_history` row count `< baseline_window + 1` (default `< 6`) | Skip PSI / z-score / spike / en_share drift; **INFO** (`metric=drift`, rule=`cold_start`) |
| `monitoring.yml` missing or unreadable | Use built-in **DEFAULTS**; **WARN** (`metric=config_file`, rule=`missing` or `parse_error`) |
| PSI with 0 bins | `eps=1e-6`; never log(0) |
| `jsonl` write fails (disk full) | Raise; propagates through `run_logger` (same when business scripts wrap in Phase 2) |

**Rule of thumb**: ERROR only from hard-threshold violations and SQLite row mismatch (etc.); missing DQ history → WARN early exit, not fabricated hard checks.

---

## 8. Exit-code Contract

| Step | MVP exit code | Phase 2 |
|------|---------------|---------|
| `collect_run_metrics.py` | always 0 | always 0 |
| `check_drift_and_alerts.py` | ERROR → 1, else → 0 | **same**; in CI use `&&` so that ERROR naturally blocks warehouse load |

**Business scripts' exit semantics are unchanged.** Blocking is achieved by orchestration order, not by cross-module calls.

---

## 9. Local Acceptance Tests

### 9.1 Smoke

```bash
cd "google play"
# Assumes one full business run already produced quality_report.csv / eda_section_*/
python scripts/07_monitor/collect_run_metrics.py
python scripts/07_monitor/check_drift_and_alerts.py
ls reports/monitoring/
```

Expected: both history CSVs gain one row; `alerts.csv` may be 0 or more rows; `monitoring_report.md` is readable.

### 9.2 Trigger an ERROR

- Edit `monitoring.yml`: set `clean_en_rows_min` to `current + 1`.
- Re-run `check_drift_and_alerts.py`.
- Expected: new ERROR in `alerts.csv`, exit code 1, ERROR shown at top of `monitoring_report.md`.

### 9.3 Trigger drift

- Manually append a few extreme rows to `data_quality_history.csv`.
- Re-run drift.
- Expected: relevant WARNs.

### 9.4 Cold start (drift)

- Keep **`data_quality_history.csv`** non-empty (otherwise check exits with WARN first). Make **`distribution_history.csv`** have **fewer than `baseline_window + 1`** rows (default fewer than 6).
- Expected: hard thresholds + SQLite checks still run; drift skipped; `monitoring_report.md` INFO lists **`drift`** with rule **`cold_start`**.

> If **`data_quality_history.csv`** is missing or empty, the implementation **does not** run hard thresholds — it WARNs and returns (run `collect_run_metrics.py` first).

---

## 10. Run Order

### 10.1 MVP

```bash
# 01_collect → 02_clean → 03_eda (a..e) → merge → 05_warehouse (load + verify)
python scripts/07_monitor/collect_run_metrics.py
python scripts/07_monitor/check_drift_and_alerts.py
echo "exit=$?"
```

### 10.2 Phase 2 (monitor as gate)

```bash
... eda ... \
  && python scripts/07_monitor/collect_run_metrics.py \
  && python scripts/07_monitor/check_drift_and_alerts.py \
  && python scripts/05_warehouse/load_to_sqlite.py
```

---

## 11. Milestones

| # | Task | Deliverable | ETA |
|---|------|-------------|-----|
| M1 | Create dirs + empty files + requirements | Skeleton | 0.5 d |
| M2 | `_runlog.py` + 3 hand-written tests | Correct JSONL writes | 0.5 d |
| M3 | `collect_run_metrics.py` | Both history CSVs appendable | 1 d |
| M4 | `check_drift_and_alerts.py` (hard thresholds only) | `alerts.csv` + exit code | 1 d |
| M5 | PSI / z-score / spike | Drift WARNs firing | 1 d |
| M6 | `monitoring_report.md` template + cold-start / missing-file fallback | Human-readable summary | 0.5 d |
| M7 | README: add a "Monitoring" section | Ship-ready | 0.5 d |

**Total**: ≈ 5 dev-days.

---

## 12. Non-goals (explicit)

- No real-time / near-real-time alerting (no email / Slack push).
- No Prometheus / Grafana / Airflow.
- No changes to the **logic** of any business script (Phase 2 only wraps them with `with run_logger`).
- No automatic "use / don't use" decisions — **the monitor produces reports; a human decides**.

---

## Appendix A — One-off scaffolding command

```bash
cd "google play"
mkdir -p config logs reports/monitoring scripts/07_monitor
touch config/monitoring.yml
touch scripts/07_monitor/{__init__.py,_runlog.py,collect_run_metrics.py,check_drift_and_alerts.py,smoke_runlog.py}
```

## Appendix B — Mapping to the design doc

| Design section | Impl-spec section |
|----------------|-------------------|
| §1 Background / goals / principles | §0, §1 |
| §2 Red lines / drift classification | §4 |
| §3 Architecture / dirs | §1, §2.2 |
| §4 Four-layer monitoring | §3 (APIs) + §4 (rules) |
| §5 Drift algorithms | §3.3 (PSI / z-score) |
| §6 `monitoring.yml` | §5 |
| §7 Run order | §10 |
| §8 Artifacts | §2.2 |
| §9 Failure modes | §7 |
