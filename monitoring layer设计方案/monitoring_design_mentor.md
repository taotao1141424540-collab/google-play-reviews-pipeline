# 监控层设计文档 · Google Play Reviews Pipeline

**版本**：v1（MVP）
**目标读者**：mentor
**作者**：Chuantao
**相关仓库**：`google play/`（现有 01_collect → 06_insights 流水线）

---

## 1. 背景与目标

### 1.1 背景

现有流水线已经完成 **采集 → 清洗 → EDA → 入库 → 洞察** 的端到端链路，并产出 ≥10k 英文评论的分析集。Mentor 建议在此之上加一层**轻量监控**，以便在数据量随时间增长、pipeline 反复运行的场景下：

- 知道流水线**是否跑对**；
- 知道每次拿回的数据**是否健康**；
- 知道各项分布**是否在悄悄漂移**。

### 1.2 本版的设计目标

| # | 目标 | 非目标 |
|---|------|--------|
| G1 | 每次 run 留下**结构化、机器可读**的运行记录 | 搭建 Prometheus/Grafana 等服务 |
| G2 | 把已有质量指标**时间序列化**，形成可比较的历史 | 重新实现清洗/EDA 的计算 |
| G3 | 对关键红线**给出硬阈值告警**，保证交付承诺 | 自动阻止业务脚本执行 |
| G4 | 对评分/长度/日量等分布做**漂移告警** | 线上实时推送（邮件/Slack） |
| G5 | 每次都产出**一份人读摘要**，让 mentor 30 秒判断这次能不能用 | 试图让监控自动“决定用不用” |

### 1.3 指导原则

- **非侵入**：不修改现有 01–06 业务脚本的计算逻辑；监控只读它们的产物。
- **轻量**：全部文件式输出（JSONL / CSV / Markdown），不引入服务组件。
- **人决策在前、自动化在后**：MVP 只产“体检单”，不做任何拦截动作。
- **阈值可配置**：红线和漂移参数集中在 `config/monitoring.yml`，方便调参。

---

## 2. 业务场景与需要监控的“红线”

### 2.1 业务承诺

- **规模**：交付 ≥10k 英文评论分析集。
- **可分析性**：时间字段可解析、评分字段可解析、关键字段不缺失。
- **可信度**：不含严重重复、不被限流抓空、不被非英文数据淹没。
- **可复跑**：同样的命令换一批 app 也能跑出结构相同的产物。

### 2.2 当任一承诺被违反时，**必定是“硬红线”**

这些情况**不用和历史比**就能定性，所以放进“硬阈值”：

| 业务承诺 | 可能的故障场景 | 对应硬阈值 |
|----------|----------------|------------|
| ≥10k 英文 | langdetect 崩、抓到大量非英文 | `clean_en_rows >= 8000` |
| 规模充足 | 限流/网络中断/app 列表出错 | `raw_rows >= 5000` |
| app 覆盖稳定 | 多个 app 同时失败 | `apps_count >= expected - 2` |
| 时间可分析 | at 字段格式变更 | `parseable_time_rate >= 0.99` |
| 评分可分析 | score 字段变更/丢失 | `parseable_score_rate >= 0.99` |
| 字段未错位 | content 映射错误 | `empty_text_rate <= 0.01` |
| 翻页无重复 | continuation token bug | `duplicate_rate <= 0.02` |
| 入库无丢行 | 写入失败或截断 | `reviews_rows == source_rows` |

### 2.3 漂移类（“和自己比才有意义”）

这些只在**和历史基线比较**时才有意义，放进漂移告警（WARN 为主）：

- 评分 1–5 星的占比分布（用 PSI）。
- 评论长度的 `mean / p50 / p90`（用 z-score）。
- 近 7 日日均评论量 vs 历史均值（倍数）。
- 英文占比 `en_share`（缓慢下降可能是 langdetect 行为变化）。
- 风险标记率：`is_spam_bot_suspect`、`is_time_anomaly`、`is_inconsistent_rating`。

---

## 3. 架构

### 3.1 数据流

```
01_collect → 02_clean → 03_eda → 05_warehouse → 06_insights
    │            │           │           │            │
    │writes      │writes     │writes     │writes      │writes
    ▼            ▼           ▼           ▼            ▼
raw_collection_metrics.csv   quality_report.csv   eda_section_*/   play_reviews*.db   spike_dates_top10.csv
                         │                  │                    │                    │
                         └────────┬─────────┴────────────────────┴────────────────────┘
                                  ▼
                 07_monitor/collect_run_metrics.py
                                  │                 reads + aggregates (read-only)
        ┌─────────────────────────┼─────────────────────────────┐
        ▼                         ▼                             ▼
 logs/pipeline_runs.jsonl   reports/monitoring/                reports/monitoring/
  (run-level logs)          data_quality_history.csv           distribution_history.csv
                                  │
                                  ▼
                 07_monitor/check_drift_and_alerts.py
                                  │  reads history + config/monitoring.yml
                                  ▼
              reports/monitoring/alerts.csv
              reports/monitoring/monitoring_report.md
              exit code 0 / 1 (signal only in MVP)
```

### 3.2 新增目录与文件

```
google play/
├── config/
│   └── monitoring.yml                # 阈值、基线窗口、豁免清单
├── logs/
│   └── pipeline_runs.jsonl           # 每次 run 一行 JSONL
├── reports/
│   └── monitoring/
│       ├── data_quality_history.csv  # 质量指标时间序列
│       ├── distribution_history.csv  # 分布指标时间序列
│       ├── alerts.csv                # 历次告警明细
│       └── monitoring_report.md      # 本次 run 的人读摘要
├── scripts/
│   └── 07_monitor/
│       ├── __init__.py
│       ├── _runlog.py                # 上下文管理器：写 pipeline_runs.jsonl
│       ├── collect_run_metrics.py    # 聚合 → history CSV（main 外包 run_logger）
│       ├── check_drift_and_alerts.py # 对比 → alerts + markdown（main 外包 run_logger）
│       └── smoke_runlog.py           # 可选：本地验证 JSONL 写入
└── （设计 / 规格文档）仓库目录 `monitoring layer设计方案/`：`monitoring_design_mentor.md`、`monitoring_impl_spec_cn.md`、`monitoring_impl_spec_en.md` 等
```

### 3.3 对现有代码的改动边界

- **强制改动**：**无**（先落最小可用版）。
- **可选改动**（Phase 2 再做）：给 `01_collect` / `02_clean` / `05_warehouse` 的 `main()` 外层套一次 `with run_logger(...)`，把 `rows_in/rows_out` 塞进 JSONL；业务逻辑一行都不碰。

---

## 4. 四层监控详细设计

### 4.1 Run-level logging — “这次跑过没、跑对没”

**做什么**
在 `logs/pipeline_runs.jsonl` 里 append 一行，记录一次脚本运行的生命周期。

**字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | str | `{iso8601}_{script_short}` |
| `script` | str | 脚本相对路径 |
| `args` | str | CLI 参数原文 |
| `start_utc` / `end_utc` | ISO | 时间戳 |
| `duration_sec` | int | 结束 - 开始 |
| `status` | enum | `success` / `failed` |
| `exception` | str? | 失败时的异常 |
| `rows_in` / `rows_out` | int? | 脚本级输入/输出行数 |
| `output_files` | list[str] | 写入的文件相对路径 |
| `git_sha` | str? | 可选，`git rev-parse HEAD` |

**失败行为**
`_runlog.py` 的约定：脚本抛异常时先记 `failed`，再 re-raise。`rows_out=None` 也要写一行。

---

### 4.2 Data quality checks — “数据本身健不健康”

**做什么**
把已有的 `reports/quality_report.csv` 和 `reports/raw_collection_metrics.csv` **宽表化 → 追加到** `reports/monitoring/data_quality_history.csv`。

**表结构**

| 列 | 来源 |
|---|---|
| `run_ts` | collect_run_metrics 写入时间 |
| `raw_rows` | `raw_collection_metrics.csv` |
| `duplicate_rate` | `quality_report.csv` (`p0.duplicate_rate`) |
| `empty_text_rate` | 同上 |
| `short_text_rate_lt5` | 同上 |
| `parseable_time_rate` | 同上 |
| `parseable_score_rate` | 同上 |
| `english_rate_after_p0` | `quality_report.csv` (`p1`) |
| `noise_rate_after_p0` | 同上 |
| `missing_key_fields_rate` | `quality_report.csv` (`p2`) |
| `inconsistent_rating_rate` | 同上 |
| `time_anomaly_rate` | 同上 |
| `spam_bot_suspect_rate` | 同上 |
| `clean_all_rows` | `p0.clean_all_rows` |
| `clean_en_rows` | `output.clean_en_rows` |
| `apps_count` | `raw_collection_metrics.csv` |

**约定**
- 只 append，不重写历史。
- 某些指标缺失时写 `NaN`，不抛异常。

---

### 4.3 Distribution tracking — “分布有没有悄悄变样”

**做什么**
从 EDA 产物里读几个**小而稳定**的聚合值，追加到 `reports/monitoring/distribution_history.csv`。

**表结构**

| 列 | 来源 |
|---|---|
| `run_ts` | 写入时间 |
| `score_1_pct` … `score_5_pct` | `eda_section_a/A1_rating_distribution.csv` 归一化 |
| `len_mean`, `len_p50`, `len_p90` | `eda_section_a/A3_length_summary.csv` |
| `en_share` | `eda_section_c/C2_english_subset_summary.csv` 或 `quality_report.csv` |
| `last7d_reviews_sum`, `last7d_daily_mean` | `eda_section_b/B3_daily_volume.csv` 最近 7 行 |

**约束**
- 不存原始行、不存 PNG。
- 指标缺失时列留空，流程继续。

---

### 4.4 Alerts & deviation — “不对劲时要被看到”

**做什么**
读前两张 history 表 + `monitoring.yml`，产出 **两份告警产物** + **一个退出码**。

**告警级别定义**

| 级别 | 触发条件 | 退出码（MVP） | 含义 |
|------|---------|----------------|------|
| INFO | 有 baseline 记录 / 没有告警 | 0 | 本次健康 |
| **WARN** | 漂移指标越过阈值；非核心硬阈值越过 | 0 | 值得留意但可用 |
| **ERROR** | 核心硬阈值越过（见 §2.2） | 1 | 不建议作为交付 |

**告警清单结构（`alerts.csv`）**

| 列 | 说明 |
|---|---|
| `run_ts` | 本次 run |
| `level` | INFO / WARN / ERROR |
| `metric` | 如 `duplicate_rate` / `score_dist_psi` |
| `current` | 当前值 |
| `baseline_or_threshold` | 红线或基线值 |
| `rule` | `threshold_max` / `threshold_min` / `psi_max` / `zscore_max` / `spike_ratio` |
| `message` | 人话描述 |

**人读摘要（`monitoring_report.md` 模板）**

```markdown
# Monitoring Report — {run_ts}

## Run summary
- Scripts tracked this round: {list}
- Overall status: {OK / WARN / ERROR}

## Hard-threshold alerts (ERROR)
- [if none] —

## Drift alerts (WARN)
- [if none] —

## Healthy metrics (FYI)
- clean_en_rows: 10 072 (target ≥ 8 000)
- parseable_time_rate: 0.998
- en_share: 0.725

## Recommendation
{automatically generated:
 - ERROR 存在 → "Do NOT use this run as delivery; investigate and rerun."
 - 仅 WARN → "Usable, but spot-check the flagged metrics before claims."
 - 无告警 → "All checks passed."}
```

---

## 5. 漂移算法约定（最小实现）

- **评分分布 PSI**：

  \[
  \text{PSI} = \sum_{i=1}^{5} (p_i - q_i) \cdot \ln \frac{p_i}{q_i}
  \]

  - `p_i` = 本次分布；`q_i` = 最近 `baseline_window` 次的均值分布。
  - 阈值：`psi_rating_max: 0.20`。

- **长度均值 z-score**：
  `z = (len_mean_cur - mean(len_mean_hist)) / std(len_mean_hist)`；阈值 `zscore_len_mean_max: 3.0`。

- **日量 spike**：
  `last7d_daily_mean / historical_daily_mean > daily_volume_spike_ratio`（默认 2.0）。

- **冷启动**：历史样本 `< baseline_window` 时，仅跑硬阈值，跳过漂移计算。

---

## 6. `config/monitoring.yml` 设计

```yaml
# 硬阈值（越过即 ERROR）
thresholds:
  raw_rows_min: 5000
  apps_count_min_delta: 2
  duplicate_rate_max: 0.02
  empty_text_rate_max: 0.01
  parseable_time_rate_min: 0.99
  parseable_score_rate_min: 0.99
  english_rate_min: 0.50
  clean_en_rows_min: 8000
  missing_key_fields_rate_max: 0.005

# 漂移（越过即 WARN）
drift:
  baseline_window: 5
  psi_rating_max: 0.20
  zscore_len_mean_max: 3.0
  daily_volume_spike_ratio: 2.0
  en_share_drop_max: 0.10

# 预期参数
expected:
  apps_count: 14   # 与当前仓库 app 数一致；请按你的 app_list 修改

# 豁免（偶发噪声/人为例外时临时使用）
mute:
  # - metric: last7d_daily_mean
  #   until: 2026-05-01
  #   reason: "campaign launch"
```

---

## 7. 运行顺序

### 7.1 MVP（当前阶段，只看不拦）

```bash
# 业务流水线
python scripts/01_collect/collect_reviews.py
python scripts/02_clean/clean_and_eda.py
python scripts/03_eda/run_eda_section_a.py
python scripts/03_eda/run_eda_section_b.py
python scripts/03_eda/run_eda_section_c.py
python scripts/03_eda/run_eda_section_d.py
python scripts/03_eda/run_eda_section_e.py
python scripts/03_eda/merge_eda_csv_to_workbook.py
python scripts/05_warehouse/load_to_sqlite.py
python scripts/05_warehouse/run_sqlite_verification.py

# 监控
python scripts/07_monitor/collect_run_metrics.py
python scripts/07_monitor/check_drift_and_alerts.py
```

### 7.2 Phase 2（把监控变“守门员”）

在 CI 里用 `&&` 把监控**前置到入库之前**：

```bash
... eda ... \
  && python scripts/07_monitor/collect_run_metrics.py \
  && python scripts/07_monitor/check_drift_and_alerts.py \
  && python scripts/05_warehouse/load_to_sqlite.py
```

- ERROR 发生 → 入库不会被执行；已采集/清洗/EDA 的产物仍保留在磁盘上。
- 不改任何业务脚本，只调顺序。

---

## 8. 产物一览

| 文件 | 作用 | 写入频率 |
|------|------|----------|
| `logs/pipeline_runs.jsonl` | 每次脚本运行的结构化 log | 每次 run，append |
| `reports/monitoring/data_quality_history.csv` | 质量指标历史 | 每次监控 append 1 行 |
| `reports/monitoring/distribution_history.csv` | 分布指标历史 | 每次监控 append 1 行 |
| `reports/monitoring/alerts.csv` | 历次告警明细 | 每次监控 append N 行 |
| `reports/monitoring/monitoring_report.md` | 人读摘要 | 每次覆盖 |

---

## 9. 失败模式与降级策略

| 情况 | 监控层行为 |
|------|-----------|
| 本次未跑 EDA，C/D 的 CSV 不存在 | 相关分布字段留空，不报 ERROR |
| `quality_report.csv` 缺失 | 输出一条 WARN：`quality_report_missing`；不计算硬阈值 |
| `monitoring.yml` 缺失 | 使用脚本内置的默认阈值，并在报告里提示 |
| 历史样本 < `baseline_window` | 跳过漂移，仅跑硬阈值 |
| `git_sha` 取不到 | 字段留空，不阻塞流程 |

---

## 附录 A：红线速查表

| 指标 | 红线（ERROR） | 业务含义 |
|------|---------------|----------|
| `raw_rows` | `< 5 000` | 采集量不足，后续无法产出 ≥10k 英文集 |
| `apps_count` | `< expected - 2` | 多个 app 同时抓失败，样本覆盖不可信 |
| `duplicate_rate` | `> 2%` | 翻页/去重异常，EDA 会被污染 |
| `empty_text_rate` | `> 1%` | `content` 字段错位或丢失 |
| `parseable_time_rate` | `< 99%` | 时间字段坏，B/E 节与 spike 分析全部失真 |
| `parseable_score_rate` | `< 99%` | 评分字段坏，A/B 节失真 |
| `english_rate_after_p0` | `< 50%` | langdetect 异常或采集跑偏 |
| `clean_en_rows` | `< 8 000` | 违反 ≥10k 英文交付承诺 |
| `missing_key_fields_rate` | `> 0.5%` | review_id / score / at / content 任一大面积缺失 |
| `sqlite.row_counts(reviews) vs source_rows` | 不等 | 入库丢行/截断 |
