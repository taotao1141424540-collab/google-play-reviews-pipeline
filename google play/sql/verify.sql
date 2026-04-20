-- Manual verification (CLI). Automated report (optional both DBs):
--   python scripts/05_warehouse/run_sqlite_verification.py --both
-- Same SQL applies to full warehouse or English subset; choose the DB file:
--   sqlite3 data/warehouse/play_reviews.db < sql/verify.sql
--   sqlite3 data/warehouse/play_reviews_en.db < sql/verify.sql

.headers on
.mode column

SELECT key, value FROM ingestion_meta ORDER BY key;

SELECT 'apps' AS tbl, COUNT(*) AS n FROM apps
UNION ALL
SELECT 'reviews', COUNT(*) FROM reviews;

SELECT app_id, COUNT(*) AS reviews
FROM reviews
GROUP BY app_id
ORDER BY reviews DESC
LIMIT 5;

SELECT score, COUNT(*) AS n
FROM reviews
GROUP BY score
ORDER BY score;
