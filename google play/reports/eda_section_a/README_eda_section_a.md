# EDA Section A — Summary

## Data sources
- clean_en_only: `data/processed/clean_en_only.csv` (10,169 rows)
- clean_all_languages: `data/processed/clean_all_languages.csv` (13,806 rows)
- raw: `data/raw/google_play_reviews_raw.csv` (15,405 rows)

## A5 Scale chain

                 stage                                   file  rows
                   raw   data/raw/google_play_reviews_raw.csv 15405
after_P0_all_languages data/processed/clean_all_languages.csv 13806
 after_P0_english_only       data/processed/clean_en_only.csv 10169

## A6 / A7
- noise_rate (is_noise): 0.0000
- has_dev_reply_rate: 0.1481

## Generated files

- `A1_rating_distribution.png`, `A1_rating_distribution.csv`
- `A2_rating_counts_by_app.csv`, `A2_mean_score_by_app.csv`, `A2_rating_heatmap_by_app.png`
- `A3_review_length_hist.png`, `A3_length_summary.csv`
- `A4_length_by_rating_boxplot.png`, `A4_length_stats_by_rating.csv`
- `A5_data_scale_chain.csv`
- `A6_A7_quality_flags.csv`, `A7_score_by_has_dev_reply.csv`
