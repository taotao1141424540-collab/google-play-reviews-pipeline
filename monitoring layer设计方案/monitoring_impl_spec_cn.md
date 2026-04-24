# 监控层技术实现方案（Implementation Spec · 中文版）

> 配套文档：`monitoring_design_mentor.md`（设计方案）
> 本文件定位：**从设计到代码的落地规格**，面向开发自己（也可给 code reviewer 读）。
> 版本：v1（MVP · 只观察、不拦截） · 作者：Chuantao

---

## 0. 关系速览

| 文档 | 解决什么问题 |
|------|-------------|
| `monitoring_design_mentor.md` | **为什么要监控、监控什么、阈值含义**（设计 / 约定） |
| **本文件**（Impl Spec） | **代码放在哪、函数怎么写、输入输出怎么对齐、怎么验证** |

本文件不再重复设计中的业务论证，重点回答 5 件事：
1. 新增哪些目录 / 文件；
2. 两个脚本的**数据契约**（读谁、写谁、列是什么）；
3. 关键函数签名与错误处理；
4. `monitoring.yml` 的字段语义；
5. 怎么本地验收、CI 怎么接。

---

## 1. 仓库落地（File Layout）

在 `google play/` 下 **不改动** 01–06 业务脚本；版本控制里跟踪的监控相关**源码**包括：

- **`config/monitoring.yml`** — 阈值与漂移参数（可改）。
- **`scripts/07_monitor/`** 下 **5 个** `.py`：`__init__.py`、`_runlog.py`、`collect_run_metrics.py`、`check_drift_and_alerts.py`、`smoke_runlog.py`（本地自检 JSONL，可选运行）。
- **`requirements.txt`** 增加 **`pyyaml>=6.0`**（与仓库其余依赖一并维护）。

首次运行监控脚本后由程序创建：**`logs/`**（`pipeline_runs.jsonl`）、**`reports/monitoring/`**（history / alerts / report）。本仓库根 **`.gitignore`** 默认忽略 `google play/logs/` 与 `google play/reports/monitoring/` 的运行产物，克隆后需自行跑脚本生成。

```
google play/
├── config/
│   └── monitoring.yml                          # 【新增】阈值、漂移参数、豁免
├── logs/                                       # 【运行时目录】
│   └── pipeline_runs.jsonl                     # collect / check 每次 main 经 run_logger 追加一行
├── reports/
│   └── monitoring/                             # 【运行时目录】
│       ├── data_quality_history.csv            # append
│       ├── distribution_history.csv            # append
│       ├── alerts.csv                          # append
│       └── monitoring_report.md                # 每次覆盖
└── scripts/
    └── 07_monitor/
        ├── __init__.py
        ├── _runlog.py                          # run_logger 上下文 → JSONL
        ├── collect_run_metrics.py              # 聚合 → history CSV；main 包 run_logger
        ├── check_drift_and_alerts.py           # 比对 → alerts + report；main 包 run_logger
        └── smoke_runlog.py                     # 可选：验证 _runlog 写入
```

**设计原则（落地体现）**：
- 监控模块**只读不写**业务产物（`reports/quality_report.csv` 等只读取）。
- 所有监控产物都落在 `logs/` 或 `reports/monitoring/`，和业务产物严格隔离。
- 无任何第三方 daemon / 服务；纯文件 I/O + 标准库 + `pyyaml`（若你希望无依赖，也可以用 JSON 替代 YAML，见 §6）。

---

## 2. 数据契约（Data Contracts）

### 2.1 读入（上游，已存在）

| 产物（相对 `google play/`） | 读取方 | 必需列 / 字段 | 缺失时行为 |
|-----|--------|---------------|------------|
| `reports/raw_collection_metrics.csv` | `collect_run_metrics.py` | `raw_rows, apps_count` | 该行字段写 NaN，继续 |
| `reports/quality_report.csv` | `collect_run_metrics.py` | P0 / P1 / P2 指标（见 §2.2） | 该行字段写 NaN，继续 |
| `reports/eda_section_a/A1_rating_distribution.csv` | 同上（分布） | `score, count` | 字段留空 |
| `reports/eda_section_a/A3_length_summary.csv` | 同上 | `mean, p50, p90` | 字段留空 |
| `reports/eda_section_b/B3_daily_volume.csv` | 同上 | `date, reviews` | 字段留空 |
| `reports/eda_section_c/C2_english_subset_summary.csv` | 同上 | `english_share` 或等价字段 | 字段留空 |

> **契约要点**：**`collect_run_metrics`** 在读不到上游文件时把对应列写成 **NaN/空**，**不**写 `alerts.csv`。**`check_drift_and_alerts`** 在 **history 缺失/为空** 时发 **WARN** 并早退；**ERROR** 仍只来自**指标值越界**或 **SQLite 行数不一致**等，不因「某张上游业务 CSV 没生成」直接 ERROR。

### 2.2 写出（下游，新产物）

#### `logs/pipeline_runs.jsonl`（每行一个 JSON）

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

- `run_id` 规则：`{iso8601}_{script_basename_without_ext}`。
- 失败时：先 append 一行 `status=failed, exception=<str>`，再 re-raise。
- `rows_in` / `rows_out` 允许 `null`（某些脚本不天然有这俩概念，例如 EDA）。

#### `reports/monitoring/data_quality_history.csv`（宽表，只追加）

列（顺序固定）：

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

#### `reports/monitoring/alerts.csv`（只追加）

```
run_ts, level, metric, current, baseline_or_threshold, rule, message
```

- `level ∈ {INFO, WARN, ERROR}`。
- `rule` 含阈值/漂移类：`threshold_max`、`threshold_min`、`psi_max`、`zscore_max`、`spike_ratio`、`eq`；另有降级与元数据类如 **`cold_start`**、**`missing`**、**`empty`**、**`parse_error`**、**`unknown_subset`**、`mismatch` 等（以实现代码为准，不必穷举）。

#### `reports/monitoring/monitoring_report.md`

每次**覆盖**（只留最近一次）。模板与字段与 `monitoring_design_mentor.md §4.4` 一致。

---

## 3. 模块 API（函数签名 + 语义）

> Python ≥ 3.10；依赖：标准库 + `pandas`（仓库已用）+ `pyyaml`（新依赖，或替换为 JSON）。

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
    上下文管理器。with 块内：
      - 记录 start_utc / end_utc / duration_sec
      - 捕获异常：status='failed', exception=str(e), 然后 re-raise
      - 正常退出：status='success'
    调用者可在 with 内通过 ctx.set_rows_out(n) / ctx.add_output(path) 追加信息。
    """
```

**使用示例**（Phase 2 才需要接进业务脚本；MVP 阶段可先不接）：

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
    如果 out_path 不存在：创建并写表头；存在：按列顺序 append。
    缺失列写 NaN，不重排。
    """

def main() -> int:
    """退出码：永远 0（本步骤只做聚合，不做判定）。"""
```

**CLI**：`python scripts/07_monitor/collect_run_metrics.py`

### 3.3 `check_drift_and_alerts.py`

```python
def load_config(path: str = "config/monitoring.yml") -> dict: ...

def check_hard_thresholds(latest: pd.Series, thresholds: dict) -> list[Alert]: ...
def check_drift(latest: pd.Series, history: pd.DataFrame, drift_cfg: dict) -> list[Alert]: ...

def write_alerts(alerts: list[Alert], out_path: str) -> None: ...     # append
def write_report(alerts: list[Alert], latest: pd.Series, out_path: str) -> None: ...  # overwrite

def main() -> int:
    """
    退出码（MVP）：
      - 任一 ERROR → 1
      - 其他（INFO/WARN/无告警） → 0
    """
```

**PSI 实现（评分分布）**：

```python
def psi(p: np.ndarray, q: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(p, eps, None); q = np.clip(q, eps, None)
    return float(np.sum((p - q) * np.log(p / q)))
```

**冷启动处理**：

```python
if len(history) < drift_cfg["baseline_window"]:
    return []   # 只跑 hard thresholds
```

### 3.4 Alert 数据结构

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

## 4. 告警规则矩阵（代码级）

### 4.1 硬阈值 → ERROR

| 指标 | 规则 | 阈值键（yml） |
|------|------|---------------|
| `raw_rows` | `< raw_rows_min` | `thresholds.raw_rows_min` |
| `apps_count` | `< expected.apps_count - thresholds.apps_count_min_delta` | 同上 |
| `duplicate_rate` | `> duplicate_rate_max` | 同上 |
| `empty_text_rate` | `> empty_text_rate_max` | 同上 |
| `parseable_time_rate` | `< parseable_time_rate_min` | 同上 |
| `parseable_score_rate` | `< parseable_score_rate_min` | 同上 |
| `english_rate_after_p0` | `< english_rate_min` | 同上 |
| `clean_en_rows` | `< clean_en_rows_min` | 同上 |
| `missing_key_fields_rate` | `> missing_key_fields_rate_max` | 同上 |

### 4.2 漂移 → WARN

| 指标 | 规则 | 阈值键 |
|------|------|--------|
| 评分分布 | `PSI(score_pct_vec, mean(history[-N:])) > psi_rating_max` | `drift.psi_rating_max` |
| 长度均值 | `|z(len_mean)| > zscore_len_mean_max` | `drift.zscore_len_mean_max` |
| 日量 | `last7d_daily_mean / history_daily_mean > daily_volume_spike_ratio` | `drift.daily_volume_spike_ratio` |
| 英文占比下降 | `baseline_mean(en_share) - current > en_share_drop_max` | `drift.en_share_drop_max` |

### 4.3 非核心硬阈值 → WARN

原设计中「非交付红线」的硬阈值（如 `short_text_rate_lt5` 过高）使用相同比较规则，但 `level = WARN`。

---

## 5. `monitoring.yml` 字段语义

完整模板见设计文档 §6。此处只说明字段的**加载契约**：

```python
# 逻辑上等价：将 YAML 中存在的顶层段合并进内置 DEFAULTS（未写的键保留默认）
# 仅当文件缺失或 PyYAML 解析失败时整文件回退 DEFAULTS，并产生 config_file WARN

# 内置默认（当 monitoring.yml 缺失或解析失败时启用）
DEFAULTS = {
    "thresholds": {...},  # 同设计文档 §6
    "drift":      {...},
    "expected":   {"apps_count": 14},  # 与仓库 monitoring.yml 对齐；仅作 yml 缺失时的回退
    "mute":       [],
}
```

**mute 豁免语义**：

```yaml
mute:
  - metric: last7d_daily_mean
    until: 2026-05-01      # ISO 日期；到期自动失效
    reason: "campaign launch"
```

被 mute 的指标：**依旧计算并写入 history**，但不产生 alert（也不影响 exit code）。

---

## 6. 依赖与环境

| 组件 | 选择 | 理由 |
|------|------|------|
| Python | ≥ 3.10 | 匹配现有业务脚本 |
| pandas | 已有 | 读写 CSV |
| numpy | 已有 | PSI / z-score |
| pyyaml | **新增**（可选） | 载入 `monitoring.yml` |

> **若不想引入 pyyaml**：把 `monitoring.yml` 改写为 `monitoring.json`，代码端直接 `json.load`；字段完全一致。建议：若仓库已用 yaml 则保留 yaml，否则用 json，减少一条依赖。

`requirements.txt` 增加一行：

```
pyyaml>=6.0
```

---

## 7. 错误处理与降级

| 情况 | 代码行为 |
|------|---------|
| 上游 CSV 缺失（`collect_run_metrics` 读入） | 对应 history 列写 **NaN**；**不向** `alerts.csv` 追加「某文件缺失」行（collect 不写 alerts） |
| `data_quality_history.csv` 缺失或空文件 | `check_drift_and_alerts`：**WARN**（`metric=data_quality_history`，rule=`missing` / `empty`），**提前返回** exit `0`，不执行硬阈值 / SQLite / 漂移 |
| `distribution_history.csv` 缺失或空 | **WARN**（`metric=distribution_history`，rule=`missing`），跳过整段漂移；硬阈值仍执行 |
| `distribution_history` 行数 `< baseline_window + 1`（默认 `< 6`） | 跳过 PSI / z-score / 尖峰 / en_share 漂移；**INFO**（`metric=drift`，rule=`cold_start`） |
| `monitoring.yml` 缺失或无法解析 | 使用内置 **DEFAULTS**；**WARN**（`metric=config_file`，rule=`missing` 或 `parse_error`） |
| PSI 分子/分母含 0 | `eps=1e-6` 避免 log(0)；不抛异常 |
| 写 `jsonl` 失败（磁盘满等） | 抛异常；监控脚本随 `run_logger` 传播（Phase 2 业务脚本外包时同理） |

**要点**：ERROR 仅来自硬阈值违规、SQLite 行数不一致等；缺失 history 时宁可早退 WARN，也不伪造硬阈值结果。

---

## 8. 退出码契约

| 步骤 | MVP exit code | Phase 2 exit code |
|------|---------------|-------------------|
| `collect_run_metrics.py` | 永远 0 | 永远 0 |
| `check_drift_and_alerts.py` | ERROR → 1，其他 → 0 | **同 MVP**，但在 CI 里用 `&&` 把入库放在监控之后，ERROR 会自然阻断入库 |

**不改业务脚本的退出码语义**；阻断由调度顺序实现，不由脚本内跨模块依赖实现。

---

## 9. 验收测试（本地可跑）

### 9.1 冒烟测试

```bash
cd "google play"
# 先确保有一次完整业务 run 产生了 quality_report.csv / eda_section_* 等
python scripts/07_monitor/collect_run_metrics.py
python scripts/07_monitor/check_drift_and_alerts.py
ls reports/monitoring/
```

**期望**：两张 history CSV 各 append 1 行；`alerts.csv` 可为 0 行或 N 行；`monitoring_report.md` 可读。

### 9.2 人为制造 ERROR

- 编辑 `monitoring.yml`，把 `clean_en_rows_min` 调到当前值 +1；
- 再跑 `check_drift_and_alerts.py`；
- **期望**：`alerts.csv` 新增一行 level=ERROR，退出码 1，`monitoring_report.md` 顶部显示 ERROR。

### 9.3 人为制造漂移

- 在 `data_quality_history.csv` 手动 append 几行极端值（模拟历史）；
- 再跑 drift；
- **期望**：相应 WARN 行出现。

### 9.4 冷启动（漂移）

- 保留非空的 `data_quality_history.csv`（至少一行，否则 check 会 WARN 早退），使 **`distribution_history.csv` 行数少于 `baseline_window + 1`**（默认少于 6 行）；
- **期望**：`check_drift_and_alerts` 仍跑硬阈值与 SQLite 逻辑；漂移段跳过，`monitoring_report.md` 的 INFO 列表中出现 **`drift`** / rule **`cold_start`**（文案为「历史行数不足」类说明）。

> 注意：若 **`data_quality_history.csv` 本身缺失或为空**，当前实现**不会**执行硬阈值，而是 WARN 后退出（须先跑 `collect_run_metrics.py`）。

---

## 10. 运行顺序

### 10.1 MVP

```bash
# 01_collect → 02_clean → 03_eda (a..e) → merge → 05_warehouse (load + verify)
python scripts/07_monitor/collect_run_metrics.py
python scripts/07_monitor/check_drift_and_alerts.py
echo "exit=$?"
```

### 10.2 Phase 2（把监控变守门员）

```bash
... eda ... \
  && python scripts/07_monitor/collect_run_metrics.py \
  && python scripts/07_monitor/check_drift_and_alerts.py \
  && python scripts/05_warehouse/load_to_sqlite.py
```

---

## 11. 里程碑 / 工作拆分（给自己看的任务板）

| # | 任务 | 产出 | 预计 |
|---|------|------|------|
| M1 | 新建目录 + 空文件 + requirements | 骨架 | 0.5d |
| M2 | `_runlog.py` + 单测（手写 3 个用例） | JSONL 正确写入 | 0.5d |
| M3 | `collect_run_metrics.py` | 两张 history CSV 可 append | 1d |
| M4 | `check_drift_and_alerts.py`（只硬阈值） | `alerts.csv` + exit code | 1d |
| M5 | 接入 PSI / z-score / spike | 漂移 WARN 能触发 | 1d |
| M6 | `monitoring_report.md` 模板 + 冷启动 / 缺失容错 | 产出可读摘要 | 0.5d |
| M7 | 文档更新：README 增加「监控层」一节 | 对外可交付 | 0.5d |

**总预算**：≈ 5 人天。

---

## 12. 非目标（明确不做）

- 不做实时/近实时告警（无邮件/Slack/飞书 push）。
- 不引入 Prometheus / Grafana / Airflow。
- 不修改业务脚本的**任何**计算逻辑（Phase 2 只包一层 `with run_logger`）。
- 不自动决定 "用/不用"——**监控只产报告，mentor/自己看完再决定**。

---

## 附录 A：目录树一次性创建脚本（可选）

```bash
cd "google play"
mkdir -p config logs reports/monitoring scripts/07_monitor
touch config/monitoring.yml
touch scripts/07_monitor/{__init__.py,_runlog.py,collect_run_metrics.py,check_drift_and_alerts.py,smoke_runlog.py}
```

## 附录 B：和设计文档的一一映射

| 设计文档章节 | 本文件对应章节 |
|--------------|----------------|
| §1 背景 / 目标 / 原则 | §0、§1 |
| §2 红线 / 漂移分类 | §4 |
| §3 架构 / 目录 | §1、§2.2 |
| §4 四层监控 | §3（函数）+ §4（规则） |
| §5 漂移算法 | §3.3（PSI / z-score） |
| §6 `monitoring.yml` | §5 |
| §7 运行顺序 | §10 |
| §8 产物一览 | §2.2 |
| §9 失败模式 | §7 |
