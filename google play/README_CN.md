# Google Play 评论工程 — README（与当前磁盘结构一致）

**English version:** [`README.md`](README.md)

本文档依据 **`google play/`** 项目根目录的实际结构整理：脚本分层、真实路径与推荐运行顺序。

---

## 1. 仓库根目录里有什么

```
google play/
├── README_CN.md                 # 本文件
├── .mplconfig/                  # Matplotlib 缓存（EDA 画图时可设 MPLCONFIGDIR）
├── config/
│   ├── README.md                # app_list 列说明
│   └── app_list.xlsx            # 采集用应用列表（必填 app_id）
├── data/
│   ├── raw/
│   │   └── google_play_reviews_raw.csv    # 采集输出（默认）
│   ├── processed/
│   │   ├── clean_all_languages.csv        # 清洗：全语言
│   │   ├── clean_en_only.csv              # 清洗：仅英文
│   │   ├── clean_en_time_window.csv       # 可选：time-window 采样产出
│   │   └── time_window_sampling_manifest.json  # 可选：采样参数记录
│   └── warehouse/
│       ├── play_reviews.db                # SQLite：默认全量入库结果
│       └── play_reviews_en.db             # SQLite：--english-only 入库结果
├── docs/
│   ├── export_spike_days_readme.md        # 尖峰表说明
│   ├── spike_dates_top10.csv              # 尖峰日 Top-N（export_spike_days 生成）
│   ├── sqlite_verification_results.txt    # 全量库校验报告
│   └── sqlite_verification_results_en.txt # 英文库校验报告
├── reports/
│   ├── collection_summary.md              # 采集汇总
│   ├── raw_collection_metrics.csv
│   ├── quality_report.csv                 # 清洗分层指标（p0/p1/p2）
│   ├── eda_sections_workbook.xlsx       # EDA 总表（merge 脚本）
│   ├── eda_section_a_workbook.xlsx … e   # 各节单独工作簿
│   ├── EDA_Conclusion_Bilingual.pptx / .pdf   # 结论 slides（04_export）
│   └── eda_section_{a,b,c,d,e}/         # 各节 CSV、PNG、小节 README
├── scripts/
│   ├── 01_collect/collect_reviews.py
│   ├── 02_clean/clean_and_eda.py
│   ├── 03_eda/run_eda_section_{a,b,c,d,e}.py
│   ├── 03_eda/merge_eda_csv_to_workbook.py
│   ├── 04_export/build_eda_conclusion_deck.py
│   ├── 05_warehouse/
│   │   ├── load_to_sqlite.py
│   │   └── run_sqlite_verification.py
│   └── 06_insights/
│       ├── export_spike_days.py
│       └── apply_time_window_sampling.py
└── sql/
    ├── schema.sql               # SQLite 表结构（由 load_to_sqlite 自动执行）
    └── verify.sql               # 命令行抽查用 SQL（见下文）
```

说明：

- **`run_sqlite_verification.py`** 不在上表单独一行，路径见 §5。
- 根目录下**没有** `templates/`、`scripts/README.md`、`docs/time_window_sampling_note.md`（若你需要「时间窗策略」长文说明，可自行放入 `docs/`；尖峰与采样脚本仍可独立使用）。
- **`scripts/01_collect/.idea/`** 为 IDE 配置，可忽略。

---

## 2. 分层含义（清洗脚本 `clean_and_eda.py`）

清洗在逻辑上对应 **`reports/quality_report.csv`** 里的 `section` 字段：

| 层级 | 含义（简述） |
|------|----------------|
| **P0** | 去重（`review_id`）、剔除空/过短文本、可解析时间与分数等基础规则 |
| **P1** | 语言检测（`langdetect`）、噪声标记等 |
| **P2** | 缺失关键字段、星级与情感关键词不一致、小时桶异常、疑似刷屏等扩展标记 |

产出两张主表：**`clean_all_languages.csv`**（通过 P0 的全语言）、**`clean_en_only.csv`**（其中 `is_en` 为真的子集）。

---

## 3. 脚本分层与职责（按文件夹编号）

| 目录 | 脚本 | 作用 |
|------|------|------|
| **`scripts/01_collect/`** | `collect_reviews.py` | 读 `config/app_list.xlsx`，抓取评论 → `data/raw/google_play_reviews_raw.csv`，并写采集汇总与原始指标 |
| **`scripts/02_clean/`** | `clean_and_eda.py` | 读原始 CSV → 分层清洗 → `processed/` 两张表 + `reports/quality_report.csv` |
| **`scripts/03_eda/`** | `run_eda_section_a.py` … `run_eda_section_e.py` | 分模块图表与 CSV → `reports/eda_section_*/` |
| **`scripts/03_eda/`** | `merge_eda_csv_to_workbook.py` | 合并各节 CSV → `reports/eda_sections_workbook.xlsx` + **各节** `eda_section_{a-e}_workbook.xlsx` |
| **`scripts/04_export/`** | `build_eda_conclusion_deck.py` | 双语结论 **PPT/PDF** → `reports/EDA_Conclusion_Bilingual.*` |
| **`scripts/05_warehouse/`** | `load_to_sqlite.py` | 执行 `sql/schema.sql` 后入库；支持全量默认路径或 **`--english-only`** → `play_reviews_en.db` |
| **`scripts/05_warehouse/`** | `run_sqlite_verification.py` | 查询库并写 **`docs/sqlite_verification_results*.txt`**；**`--both`** 同时校验两个 db |
| **`scripts/06_insights/`** | `export_spike_days.py` | 读 **`reports/eda_section_b/B3_daily_volume.csv`** → **`docs/spike_dates_top10.csv`** |
| **`scripts/06_insights/`** | `apply_time_window_sampling.py` | 基于 `clean_en_only` + 可选尖峰表，做去尖峰 / 按日封顶 / 时间切分 |

---

## 4. 推荐执行顺序（与依赖关系）

在 **`google play/`** 下激活虚拟环境后依次执行。

### 4.1 环境与依赖（示例）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pandas openpyxl google-play-scraper langdetect matplotlib python-pptx reportlab pyyaml
export MPLCONFIGDIR="$(pwd)/.mplconfig" && mkdir -p .mplconfig
```

### 4.2 主流程

| 顺序 | 命令 | 依赖 |
|------|------|------|
| 1 | `python3 scripts/01_collect/collect_reviews.py` | `config/app_list.xlsx` |
| 2 | `python3 scripts/02_clean/clean_and_eda.py` | `data/raw/google_play_reviews_raw.csv` |
| 3 | `python3 scripts/03_eda/run_eda_section_a.py` | 清洗后的 `data/processed/`（脚本可能优先读 xlsx，无则 csv） |
|  | `python3 scripts/03_eda/run_eda_section_b.py` | 同上 |
|  | `python3 scripts/03_eda/run_eda_section_c.py` | 同上 |
|  | `python3 scripts/03_eda/run_eda_section_d.py` | 同上 |
|  | `python3 scripts/03_eda/run_eda_section_e.py` | 同上 |
| 4 | `python3 scripts/03_eda/merge_eda_csv_to_workbook.py` | 各 `reports/eda_section_*` 下 CSV 已生成 |
| 5 | `python3 scripts/04_export/build_eda_conclusion_deck.py` | 可选；依赖各节产出与脚本内引用路径 |
| 6 | `python3 scripts/06_insights/export_spike_days.py` | **建议**在 **Section B** 跑完后执行（需要 `B3_daily_volume.csv`） |
| 7 | `python3 scripts/05_warehouse/load_to_sqlite.py` | `processed/` 下 csv/xlsx |
| 8 | `python3 scripts/05_warehouse/load_to_sqlite.py --english-only` | 同上（写入独立英文库） |
| 9 | `sqlite3 data/warehouse/play_reviews.db < sql/verify.sql` | 可选手工抽查 |
|  | `sqlite3 data/warehouse/play_reviews_en.db < sql/verify.sql` | 英文库同上 |
| 10 | `python3 scripts/05_warehouse/run_sqlite_verification.py --both` | 两个 db 均存在时 |
| 11 | `python3 scripts/06_insights/apply_time_window_sampling.py ...` | 可选；见脚本 `--help` |
| 12 | `python3 scripts/07_monitor/collect_run_metrics.py` | 在 §4.2 步骤 1–4（或完整跑）之后：追加 `reports/monitoring/*_history.csv` |
| 13 | `python3 scripts/07_monitor/check_drift_and_alerts.py` | 在步骤 12 之后：写入 `alerts.csv`、`monitoring_report.md`；若有 ERROR 则退出码为 `1` |

**说明：** `sql/schema.sql` **不要单独跑**；`load_to_sqlite.py` 会在连接数据库后 `executescript(schema.sql)`。

### 4.3 监控层（`scripts/07_monitor/`）

对流水线产物只读不写业务数据；阈值在 `config/monitoring.yml`。典型用法（一次完整跑之后）：

```bash
python3 scripts/07_monitor/collect_run_metrics.py
python3 scripts/07_monitor/check_drift_and_alerts.py
echo "exit=$?"
```

完整行为见 `monitoring layer设计方案/monitoring_impl_spec_cn.md`。

---

## 5. EDA 各节产出（当前仓库中的典型形态）

各目录内另有 **`README_eda_section_*.md`** 小节说明。

| 目录 | 主要内容（示例） |
|------|------------------|
| `eda_section_a/` | 评分分布、按应用星级、长度图、`A5_data_scale_chain.csv`、质量标记等 CSV + PNG |
| `eda_section_b/` | 应用统计、偏度、`B3_daily_volume.csv/png`（**尖峰脚本依赖**）、不一致评分样本等 |
| `eda_section_c/` | 语言计数、英文子集摘要 |
| `eda_section_d/` | 词频相关 CSV + PNG |
| `eda_section_e/` | 时间异常率、疑似刷屏率等 |

合并工作簿：**`eda_sections_workbook.xlsx`**（全表）与各 **`eda_section_*_workbook.xlsx`**（仅该节 sheet）。

---

## 6. 文档与校验文件（`docs/`）

| 文件 | 来源 |
|------|------|
| `export_spike_days_readme.md` | 人工维护；说明尖峰 CSV 字段与 `export_spike_days.py` 用法 |
| `spike_dates_top10.csv` | `export_spike_days.py`（默认 Top 10，可调 `--top`） |
| `sqlite_verification_results.txt` | `run_sqlite_verification.py`（默认全量库） |
| `sqlite_verification_results_en.txt` | 同上 `--both` 或指定 `--en-db` |

---

## 7. 一键复制（全流程骨架）

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

按需再运行 **`apply_time_window_sampling.py`**（见脚本内示例）。

---

## 8. 交付物速查

| 类型 | 路径 |
|------|------|
| 原始 / 清洗 | `data/raw/*.csv`、`data/processed/*.csv`、`reports/quality_report.csv` |
| 采集汇总 | `reports/collection_summary.md`、`reports/raw_collection_metrics.csv` |
| EDA | `reports/eda_section_*`、`reports/eda_*workbook*.xlsx` |
| 结论演示 | `reports/EDA_Conclusion_Bilingual.pptx`、`reports/EDA_Conclusion_Bilingual.pdf` |
| 尖峰 | `docs/spike_dates_top10.csv`、`docs/export_spike_days_readme.md` |
| 数仓 | `data/warehouse/play_reviews.db`、`play_reviews_en.db` |
| 校验文本 | `docs/sqlite_verification_results*.txt` |
| 监控 | `reports/monitoring/*_history.csv`、`alerts.csv`、`monitoring_report.md`、`logs/pipeline_runs.jsonl` |
| 建模前采样（若已跑） | `data/processed/clean_en_time_window.csv`、`time_window_sampling_manifest.json` |

---

## 9. 可复现（克隆仓库后如何跑通）

### Data access（数据获取）

**完整评论数据不随本 Git 仓库分发。** 根目录 **`.gitignore`** 默认忽略 **`data/raw/`、`data/processed/`、`data/warehouse/`** 等生成结果，以控制体积。**克隆后：** 先配置 **`config/app_list.xlsx`**，再**首先运行采集**：`python3 scripts/01_collect/collect_reviews.py`，然后按流水线顺序继续执行 **`02_clean` → `03_eda` → …**（见 **§7**），即可在本地生成原始表、清洗表与 SQLite 等文件。

从空目录到产出完整报表/数据库，建议按同一套步骤复现：

1. **克隆** 本仓库到本地。
2. **Python 环境：** 建议使用 **Python 3.10+**（一般 3.9+ 也可）。创建虚拟环境并按 **§4.1** 安装依赖（`pandas`、`openpyxl`、`google-play-scraper`、`langdetect`、`matplotlib`、`python-pptx`、`reportlab` 等）。
3. **`config/app_list.xlsx`：** 按 **`config/README.md`** 填写（至少 **`app_id`**）。采集需要 **联网**；耗时与 `target_reviews` 等相关。
4. **与上文 Data access 一致：** 克隆后若 **`data/`** 下无大文件属正常；请从 **`scripts/01_collect/collect_reviews.py`** 起按 **§7** 依次执行以生成数据。
5. **随机性：** 涉及抽样的脚本提供固定种子参数（如 **`apply_time_window_sampling.py`** 的 **`--random-state`**）；同一次配置下抽样可重复。原始评论行数仍受**采集时刻**与上游接口影响。
6. **数据快照（可选）：** 若 mentor 要求「可打开即见」而不重新爬取，可将某次跑完后的 **`data/`** 打 Zip 上传至 **Releases / 网盘**，并在本 README 顶部或本节补充 **下载链接**（与上文 **Data access**、**§10 Git 与大文件** 一并说明）。

---

## 10. Git 与大文件

建议将 **`data/`** 大 CSV、**`data/warehouse/*.db`**、大型 xlsx 等加入 **`.gitignore`**，仓库内只保留小样本或说明；完整数据可用网盘 / Release 并在文档中注明下载方式（与 **§9 可复现** 配套）。

---

## 11. 已知限制与合规

- **`google-play-scraper`** 非官方接口，上游变更可能导致采集失败或字段变化。  
- **`langdetect`** 为启发式检测，短文本语言可能不稳定。  
- **E 节** 等规则为启发式标记，非 ground truth。  
- **日度尖峰** 可能混合真实活跃与采集窗口，解读需结合 B3 与 `spike_dates_top10.csv`。  
- 使用数据须遵守 **Google Play 服务条款**、课程与 mentor 要求。
