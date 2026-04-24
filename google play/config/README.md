# Config — app list for scraping

**Required file:** **`app_list.xlsx`** in this folder.

Columns should include:

- **`app_id`** (required) — Google Play package name  
- **`app_name`** (optional; defaults to `app_id`)  
- **`target_reviews`** (optional; defaults to `500` per app)

Read by `scripts/01_collect/collect_reviews.py` → `find_app_list()`.

---

## `monitoring.yml` (optional but recommended for `07_monitor`)

**File:** **`monitoring.yml`** in this folder.

Used by `scripts/07_monitor/check_drift_and_alerts.py`: hard thresholds, drift tuning, expected app count, and optional mute rules. If missing, the script falls back to built-in defaults and records a WARN in `alerts.csv` / `monitoring_report.md`.

See design specs under the repository root folder **`monitoring layer设计方案/`** — e.g. **`monitoring_impl_spec_en.md`** or **`monitoring_impl_spec_cn.md`** (paths are relative to the **repo root**, not to `google play/config/`).
