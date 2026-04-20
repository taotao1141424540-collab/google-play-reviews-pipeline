# `export_spike_days.py` 与 `spike_dates_top10.csv` 说明

## 作用

`scripts/06_insights/export_spike_days.py` 从 **B3 日度评论量** 结果中，按每天的 `reviews` 降序取出 **Top N 个“高流量日”**，并写出带 **排名、绝对量、占 B3 全量比例** 的 CSV。用于标定“尖峰日”，方便与按时间窗采样、异常日分析等文档（如 `time_window_sampling_note.md`）对照使用。

## 上游依赖

1. 已跑过 **Section B** 的 EDA，并生成日度表：  
   `reports/eda_section_b/B3_daily_volume.csv`（由 `scripts/03_eda/run_eda_section_b.py` 生成）。  
2. 若该文件不存在，脚本会退出并提示先跑 `run_eda_section_b.py`。

B3 的 `reviews` 按天汇总，其 **各天 `reviews` 之和** 即脚本里打印的 “Total reviews in B3”，也作为 `share_of_all_reviews_pct` 的分母（对应当前 B3 所基于的清洗/英文子集范围，以你工程里实际 B3 为准）。

## 如何运行

在项目根目录 `google play/` 下：

```bash
python3 scripts/06_insights/export_spike_days.py
```

### 命令行参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--b3` | `reports/eda_section_b/B3_daily_volume.csv` | 输入的 B3 日度 CSV 路径 |
| `--top` | `10` | 取前 N 个高流量日 |
| `--out` | `docs/spike_dates_top10.csv` | 输出 CSV 路径 |

示例：取前 20 天、指定输出名：

```bash
python3 scripts/06_insights/export_spike_days.py --top 20 --out docs/spike_dates_top20.csv
```

## 输出文件：`docs/spike_dates_top10.csv`（默认名）

UTF-8 with BOM（`utf-8-sig`），可用 Excel 直接打开。

| 列名 | 含义 |
|------|------|
| `rank` | 按当日评论量从高到低排序的名次（1 起） |
| `day` | 日历日（与 B3 中日期格式一致，一般为 `YYYY-MM-DD`） |
| `reviews` | 该日在 B3 中的评论条数 |
| `share_of_all_reviews_pct` | 该日评论量占 **B3 全表 `reviews` 合计** 的百分比（保留两位小数） |

## 如何解读

- **尖峰集中**：若前几名的 `share_of_all_reviews_pct` 很高，说明少数日期承载了大部分日度汇总量，适合做“尖峰日”抽样或单独核对数据采集窗口。  
- **与 Top N 的关系**：默认只保留 `top` 行；提高 `--top` 可覆盖更多尾部日期。  
- **数据刷新**：重新运行 Section B 后再执行本脚本，输出会随新的 `B3_daily_volume.csv` 更新。

## 相关路径（本仓库）

- 脚本：`scripts/06_insights/export_spike_days.py`  
- 默认输入：`reports/eda_section_b/B3_daily_volume.csv`  
- 默认输出：`docs/spike_dates_top10.csv`

## 下游：Time-window 采样（实现层）

在输出或更新 `spike_dates_top10.csv` 后，可用  
`scripts/06_insights/apply_time_window_sampling.py` 对 `clean_en_only` 做 **剔除尖峰日**、**按 (app, 日) 封顶**、**按 `at_parsed` 时间切分 train/val** 等（与 `time_window_sampling_note.md` 的 A / B / D 一致），并生成 `data/processed/time_window_sampling_manifest.json` 记录参数与行数。见该脚本顶部的 `python3 ... --help` 与示例。
