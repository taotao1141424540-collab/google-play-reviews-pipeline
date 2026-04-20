# Config — app list for scraping

**Required file:** **`app_list.xlsx`** in this folder.

Columns should include:

- **`app_id`** (required) — Google Play package name  
- **`app_name`** (optional; defaults to `app_id`)  
- **`target_reviews`** (optional; defaults to `500` per app)

Read by `scripts/01_collect/collect_reviews.py` → `find_app_list()`.
