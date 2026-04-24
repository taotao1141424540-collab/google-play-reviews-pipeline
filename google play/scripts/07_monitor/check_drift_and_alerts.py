"""Compare latest metrics vs thresholds + drift baselines; write alerts + report.

Run from ``google play/`` root::

    python3 scripts/07_monitor/collect_run_metrics.py
    python3 scripts/07_monitor/check_drift_and_alerts.py

Exit code: 1 if any ERROR alert; else 0.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "config" / "monitoring.yml"
DQ_PATH = ROOT / "reports" / "monitoring" / "data_quality_history.csv"
DIST_PATH = ROOT / "reports" / "monitoring" / "distribution_history.csv"
ALERTS_PATH = ROOT / "reports" / "monitoring" / "alerts.csv"
REPORT_PATH = ROOT / "reports" / "monitoring" / "monitoring_report.md"
DEFAULT_DB = ROOT / "data" / "warehouse" / "play_reviews.db"

ALERT_COLS = ["run_ts", "level", "metric", "current", "baseline_or_threshold", "rule", "message"]

DEFAULTS: dict[str, Any] = {
    "thresholds": {
        "raw_rows_min": 5000,
        "apps_count_min_delta": 2,
        "duplicate_rate_max": 0.02,
        "empty_text_rate_max": 0.01,
        "parseable_time_rate_min": 0.99,
        "parseable_score_rate_min": 0.99,
        "english_rate_min": 0.50,
        "clean_en_rows_min": 8000,
        "missing_key_fields_rate_max": 0.005,
        "short_text_rate_lt5_warn": 0.30,
    },
    "drift": {
        "baseline_window": 5,
        "psi_rating_max": 0.20,
        "zscore_len_mean_max": 3.0,
        "daily_volume_spike_ratio": 2.0,
        "en_share_drop_max": 0.10,
    },
    "expected": {"apps_count": 14},
    "mute": [],
}


@dataclass
class Alert:
    run_ts: str
    level: str
    metric: str
    current: Any
    baseline_or_threshold: Any
    rule: str
    message: str

    def row(self) -> dict[str, Any]:
        return {
            "run_ts": self.run_ts,
            "level": self.level,
            "metric": self.metric,
            "current": self.current,
            "baseline_or_threshold": self.baseline_or_threshold,
            "rule": self.rule,
            "message": self.message,
        }


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_config() -> tuple[dict[str, Any], list[Alert]]:
    alerts: list[Alert] = []
    cfg: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
    ts = _now_ts()
    if not CFG_PATH.exists():
        alerts.append(
            Alert(
                ts,
                "WARN",
                "config_file",
                None,
                None,
                "missing",
                f"monitoring.yml not found at {CFG_PATH}; using built-in defaults.",
            )
        )
        return cfg, alerts
    try:
        import yaml  # type: ignore

        with CFG_PATH.open("r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        alerts.append(
            Alert(
                ts,
                "WARN",
                "config_file",
                str(e),
                None,
                "parse_error",
                "Failed to parse monitoring.yml; using defaults.",
            )
        )
        return cfg, alerts

    for key in ("thresholds", "drift", "expected"):
        if key in user and isinstance(user[key], dict):
            cfg[key].update(user[key])
    if "mute" in user and isinstance(user["mute"], list):
        cfg["mute"] = user["mute"]
    return cfg, alerts


def is_muted(cfg: dict[str, Any], metric: str, today: date) -> bool:
    for m in cfg.get("mute") or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("metric")) != metric:
            continue
        until = m.get("until")
        if until:
            try:
                u = datetime.strptime(str(until), "%Y-%m-%d").date()
                if today <= u:
                    return True
            except ValueError:
                return True
    return False


def psi(p: np.ndarray, q: np.ndarray, eps: float = 1e-6) -> float:
    p = np.asarray(p, dtype=float).ravel()
    q = np.asarray(q, dtype=float).ravel()
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum((p - q) * np.log(p / q)))


def append_alerts(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=ALERT_COLS)
    if ALERTS_PATH.exists():
        df.to_csv(ALERTS_PATH, mode="a", header=False, index=False, lineterminator="\n")
    else:
        df.to_csv(ALERTS_PATH, mode="w", header=True, index=False, lineterminator="\n")


def _sqlite_meta(db_path: Path) -> tuple[Optional[int], Optional[str], Optional[int]]:
    if not db_path.exists():
        return None, None, None
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.execute("SELECT COUNT(*) FROM reviews")
        n = int(cur.fetchone()[0])
        subset = None
        src_rows = None
        try:
            cur2 = con.execute("SELECT key, value FROM ingestion_meta")
            meta = dict(cur2.fetchall())
            subset = meta.get("data_subset")
            if "source_rows" in meta:
                src_rows = int(meta["source_rows"])
        except Exception:
            pass
        con.close()
        return n, subset, src_rows
    except Exception:
        return None, None, None


def check_hard_thresholds(
    cfg: dict[str, Any],
    latest: pd.Series,
    run_ts: str,
    today: date,
) -> list[Alert]:
    out: list[Alert] = []
    th = cfg["thresholds"]
    exp = int(cfg["expected"].get("apps_count", 0) or 0)
    delta = int(th.get("apps_count_min_delta", 2))

    def num(col: str) -> Optional[float]:
        if col not in latest.index:
            return None
        v = latest[col]
        if pd.isna(v):
            return None
        return float(v)

    def add_error(metric: str, cur: Any, thr: Any, rule: str, msg: str) -> None:
        if is_muted(cfg, metric, today):
            return
        out.append(Alert(run_ts, "ERROR", metric, cur, thr, rule, msg))

    def add_warn(metric: str, cur: Any, thr: Any, rule: str, msg: str) -> None:
        if is_muted(cfg, metric, today):
            return
        out.append(Alert(run_ts, "WARN", metric, cur, thr, rule, msg))

    for col in (
        "raw_rows",
        "clean_en_rows",
        "duplicate_rate",
        "parseable_time_rate",
        "parseable_score_rate",
    ):
        if num(col) is None:
            add_warn(col, None, None, "missing_value", f"{col} is NaN/missing; hard check skipped.")

    v_raw = num("raw_rows")
    if v_raw is not None and v_raw < float(th["raw_rows_min"]):
        add_error("raw_rows", v_raw, th["raw_rows_min"], "threshold_min", "raw_rows below minimum.")

    v_apps = num("apps_count")
    if v_apps is not None and exp > 0 and v_apps < float(exp - delta):
        add_error("apps_count", v_apps, exp - delta, "threshold_min", "apps_count below expected minus delta.")

    v_dup = num("duplicate_rate")
    if v_dup is not None and v_dup > float(th["duplicate_rate_max"]):
        add_error("duplicate_rate", v_dup, th["duplicate_rate_max"], "threshold_max", "duplicate_rate too high.")

    v_empty = num("empty_text_rate")
    if v_empty is not None and v_empty > float(th["empty_text_rate_max"]):
        add_error("empty_text_rate", v_empty, th["empty_text_rate_max"], "threshold_max", "empty_text_rate too high.")

    v_pt = num("parseable_time_rate")
    if v_pt is not None and v_pt < float(th["parseable_time_rate_min"]):
        add_error("parseable_time_rate", v_pt, th["parseable_time_rate_min"], "threshold_min", "parseable_time_rate too low.")

    v_ps = num("parseable_score_rate")
    if v_ps is not None and v_ps < float(th["parseable_score_rate_min"]):
        add_error("parseable_score_rate", v_ps, th["parseable_score_rate_min"], "threshold_min", "parseable_score_rate too low.")

    v_en = num("english_rate_after_p0")
    if v_en is not None and v_en < float(th["english_rate_min"]):
        add_error("english_rate_after_p0", v_en, th["english_rate_min"], "threshold_min", "English share after P0 too low.")

    v_ce = num("clean_en_rows")
    if v_ce is not None and v_ce < float(th["clean_en_rows_min"]):
        add_error("clean_en_rows", v_ce, th["clean_en_rows_min"], "threshold_min", "clean_en_rows below delivery minimum.")

    v_miss = num("missing_key_fields_rate")
    if v_miss is not None and v_miss > float(th["missing_key_fields_rate_max"]):
        add_error(
            "missing_key_fields_rate",
            v_miss,
            th["missing_key_fields_rate_max"],
            "threshold_max",
            "missing_key_fields_rate too high.",
        )

    st = num("short_text_rate_lt5")
    warn_st = float(th.get("short_text_rate_lt5_warn", 0.30))
    if st is not None and st > warn_st:
        add_warn("short_text_rate_lt5", st, warn_st, "threshold_max", "short_text_rate_lt5 elevated (non-blocking).")

    return out


def check_sqlite_rows(cfg: dict[str, Any], latest: pd.Series, run_ts: str, today: date) -> list[Alert]:
    out: list[Alert] = []
    if is_muted(cfg, "sqlite_reviews_count", today):
        return out
    n_db, subset, meta_rows = _sqlite_meta(DEFAULT_DB)
    if n_db is None:
        out.append(
            Alert(
                run_ts,
                "WARN",
                "sqlite_reviews_count",
                None,
                None,
                "missing",
                f"SQLite DB not found or unreadable: {DEFAULT_DB}",
            )
        )
        return out

    expected: Optional[int] = None
    label = "clean_en_rows"
    if subset == "clean_en_only":
        v = latest.get("clean_en_rows")
        expected = int(v) if not pd.isna(v) else None
    elif subset == "clean_all_languages":
        v = latest.get("clean_all_rows")
        label = "clean_all_rows"
        expected = int(v) if not pd.isna(v) else None
    else:
        out.append(
            Alert(
                run_ts,
                "INFO",
                "sqlite_reviews_count",
                n_db,
                subset,
                "unknown_subset",
                f"ingestion_meta.data_subset={subset!r}; skipping row-count equality check.",
            )
        )
        return out

    if expected is None:
        out.append(
            Alert(
                run_ts,
                "WARN",
                "sqlite_reviews_count",
                n_db,
                None,
                "missing",
                f"{label} is NaN; cannot compare to SQLite row count.",
            )
        )
        return out

    if int(n_db) != int(expected):
        out.append(
            Alert(
                run_ts,
                "ERROR",
                "sqlite_reviews_count",
                int(n_db),
                int(expected),
                "eq",
                f"reviews row count ({n_db}) != {label} ({expected}) for subset {subset!r}.",
            )
        )
    elif meta_rows is not None and int(meta_rows) != int(n_db):
        out.append(
            Alert(
                run_ts,
                "WARN",
                "sqlite_ingestion_meta",
                meta_rows,
                n_db,
                "mismatch",
                "ingestion_meta.source_rows does not match COUNT(reviews); metadata may be stale.",
            )
        )
    return out


def check_drift(
    cfg: dict[str, Any],
    dist_hist: pd.DataFrame,
    latest_dist: pd.Series,
    run_ts: str,
    today: date,
) -> list[Alert]:
    out: list[Alert] = []
    drift = cfg["drift"]
    w = int(drift.get("baseline_window", 5))

    if len(dist_hist) < w + 1:
        out.append(
            Alert(
                run_ts,
                "INFO",
                "drift",
                len(dist_hist),
                w + 1,
                "cold_start",
                "Not enough distribution history rows for drift; skipping PSI / length z-score / volume spike / en_share drop.",
            )
        )
        return out

    base = dist_hist.iloc[-(w + 1) : -1].copy()

    cols = [f"score_{i}_pct" for i in range(1, 6)]
    cur_vec = np.array([latest_dist.get(c, np.nan) for c in cols], dtype=float)
    if np.any(np.isnan(cur_vec)):
        out.append(
            Alert(run_ts, "WARN", "score_dist_psi", None, None, "missing", "Current score distribution has NaN; PSI skipped.")
        )
    else:
        cur_vec = cur_vec / cur_vec.sum()
        q_mat = base[cols].to_numpy(dtype=float)
        q_mean = np.nanmean(q_mat, axis=0)
        if np.any(np.isnan(q_mean)) or q_mean.sum() == 0:
            out.append(Alert(run_ts, "WARN", "score_dist_psi", None, None, "missing", "Baseline score distribution incomplete; PSI skipped."))
        else:
            q_mean = q_mean / q_mean.sum()
            val = psi(cur_vec, q_mean)
            if not is_muted(cfg, "score_dist_psi", today) and val > float(drift.get("psi_rating_max", 0.2)):
                out.append(
                    Alert(
                        run_ts,
                        "WARN",
                        "score_dist_psi",
                        val,
                        drift.get("psi_rating_max", 0.2),
                        "psi_max",
                        "Rating distribution shifted vs recent baseline (PSI).",
                    )
                )

    hist_len = base["len_mean"].dropna().astype(float)
    cur_len = latest_dist.get("len_mean")
    if hist_len.size >= 2 and not pd.isna(cur_len):
        mu = float(hist_len.mean())
        sd = float(hist_len.std(ddof=0))
        if sd > 0:
            z = abs(float(cur_len) - mu) / sd
            if not is_muted(cfg, "len_mean_zscore", today) and z > float(drift.get("zscore_len_mean_max", 3.0)):
                out.append(
                    Alert(
                        run_ts,
                        "WARN",
                        "len_mean_zscore",
                        z,
                        drift.get("zscore_len_mean_max", 3.0),
                        "zscore_max",
                        "Comment length mean is an outlier vs recent baseline.",
                    )
                )

    hist_vol = base["last7d_daily_mean"].dropna().astype(float)
    cur_vol = latest_dist.get("last7d_daily_mean")
    if hist_vol.size >= 1 and not pd.isna(cur_vol):
        hist_mean = float(hist_vol.mean())
        if hist_mean > 0:
            ratio = float(cur_vol) / hist_mean
            thr = float(drift.get("daily_volume_spike_ratio", 2.0))
            if not is_muted(cfg, "last7d_daily_mean", today) and ratio > thr:
                out.append(
                    Alert(
                        run_ts,
                        "WARN",
                        "last7d_daily_mean",
                        float(cur_vol),
                        hist_mean * thr,
                        "spike_ratio",
                        f"last7d_daily_mean ({float(cur_vol):.1f}) exceeds {thr}x historical mean ({hist_mean:.1f}).",
                    )
                )

    hist_en = base["en_share"].dropna().astype(float)
    cur_en = latest_dist.get("en_share")
    if hist_en.size >= 1 and not pd.isna(cur_en):
        base_m = float(hist_en.mean())
        drop = base_m - float(cur_en)
        max_drop = float(drift.get("en_share_drop_max", 0.10))
        if not is_muted(cfg, "en_share_drop", today) and drop > max_drop:
            out.append(
                Alert(
                    run_ts,
                    "WARN",
                    "en_share_drop",
                    float(cur_en),
                    base_m - max_drop,
                    "threshold_min",
                    f"en_share dropped by {drop:.3f} vs baseline mean {base_m:.3f} (max allowed drop {max_drop}).",
                )
            )

    return out


def write_report(
    run_ts: str,
    alerts: list[Alert],
    latest_dq: pd.Series,
    latest_dist: pd.Series,
    overall: str,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    errs = [a for a in alerts if a.level == "ERROR"]
    warns = [a for a in alerts if a.level == "WARN"]
    infos = [a for a in alerts if a.level == "INFO"]

    def fmt_line(a: Alert) -> str:
        return f"- **{a.metric}** ({a.rule}): {a.message} — current=`{a.current}` vs baseline/threshold=`{a.baseline_or_threshold}`"

    rec = "All checks passed."
    if errs:
        rec = "Do **not** use this run as final delivery without investigation; fix upstream issues or rerun."
    elif warns:
        rec = "Usable, but review WARN items before making strong claims."

    en_snap = latest_dist.get("en_share", "n/a") if len(latest_dist) else "n/a"

    lines = [
        f"# Monitoring Report — {run_ts}",
        "",
        "## Run summary",
        f"- Overall status: **{overall}**",
        f"- Alerts: ERROR={len(errs)}, WARN={len(warns)}, INFO={len(infos)}",
        "",
        "## Hard-threshold alerts (ERROR)",
    ]
    lines.extend([fmt_line(a) for a in errs] or ["- —"])
    lines += ["", "## Drift / soft alerts (WARN)"]
    lines.extend([fmt_line(a) for a in warns] or ["- —"])
    lines += ["", "## Informational (INFO)"]
    lines.extend([fmt_line(a) for a in infos] or ["- —"])
    lines += [
        "",
        "## Key metrics (latest row snapshot)",
        f"- clean_en_rows: {latest_dq.get('clean_en_rows', 'n/a')}",
        f"- clean_all_rows: {latest_dq.get('clean_all_rows', 'n/a')}",
        f"- raw_rows: {latest_dq.get('raw_rows', 'n/a')}",
        f"- duplicate_rate: {latest_dq.get('duplicate_rate', 'n/a')}",
        f"- parseable_time_rate: {latest_dq.get('parseable_time_rate', 'n/a')}",
        f"- english_rate_after_p0: {latest_dq.get('english_rate_after_p0', 'n/a')}",
        f"- en_share (dist): {en_snap}",
        "",
        "## Recommendation",
        rec,
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_checks() -> int:
    cfg, cfg_alerts = load_config()
    gen_ts = _now_ts()
    today = datetime.now(timezone.utc).date()

    all_a: list[Alert] = []
    for a in cfg_alerts:
        all_a.append(Alert(gen_ts, a.level, a.metric, a.current, a.baseline_or_threshold, a.rule, a.message))

    if not DQ_PATH.exists() or DQ_PATH.stat().st_size == 0:
        all_a.append(
            Alert(
                gen_ts,
                "WARN",
                "data_quality_history",
                None,
                None,
                "missing",
                f"{DQ_PATH} missing or empty; run collect_run_metrics.py first.",
            )
        )
        write_report(gen_ts, all_a, pd.Series(dtype=object), pd.Series(dtype=object), "WARN")
        append_alerts([a.row() for a in all_a])
        return 0

    dq_hist = pd.read_csv(DQ_PATH)
    if dq_hist.empty:
        all_a.append(Alert(gen_ts, "WARN", "data_quality_history", 0, None, "empty", "data_quality_history has no rows."))
        write_report(gen_ts, all_a, pd.Series(dtype=object), pd.Series(dtype=object), "WARN")
        append_alerts([a.row() for a in all_a])
        return 0

    latest_dq = dq_hist.iloc[-1]
    dq_run_ts = str(latest_dq.get("run_ts", gen_ts))

    all_a = [
        Alert(dq_run_ts, a.level, a.metric, a.current, a.baseline_or_threshold, a.rule, a.message) for a in all_a
    ]

    all_a.extend(check_hard_thresholds(cfg, latest_dq, dq_run_ts, today))
    all_a.extend(check_sqlite_rows(cfg, latest_dq, dq_run_ts, today))

    dist_hist = pd.read_csv(DIST_PATH) if DIST_PATH.exists() and DIST_PATH.stat().st_size > 0 else pd.DataFrame()
    if not dist_hist.empty:
        latest_dist = dist_hist.iloc[-1]
        all_a.extend(check_drift(cfg, dist_hist, latest_dist, dq_run_ts, today))
    else:
        all_a.append(
            Alert(
                dq_run_ts,
                "WARN",
                "distribution_history",
                None,
                None,
                "missing",
                f"{DIST_PATH} missing or empty; drift checks skipped.",
            )
        )
        latest_dist = pd.Series(dtype=object)

    has_error = any(a.level == "ERROR" for a in all_a)
    overall = "ERROR" if has_error else ("WARN" if any(a.level == "WARN" for a in all_a) else "OK")

    append_alerts([a.row() for a in all_a])
    write_report(
        dq_run_ts,
        all_a,
        latest_dq,
        latest_dist if not dist_hist.empty else pd.Series(dtype=object),
        overall,
    )
    print(f"Wrote {REPORT_PATH} and appended {len(all_a)} alert row(s) to {ALERTS_PATH}")
    return 1 if has_error else 0


if __name__ == "__main__":
    _mon = Path(__file__).resolve().parent
    if str(_mon) not in sys.path:
        sys.path.insert(0, str(_mon))
    from _runlog import run_logger  # noqa: E402

    with run_logger(
        script="scripts/07_monitor/check_drift_and_alerts.py",
        args=" ".join(sys.argv[1:]),
        log_path=str(ROOT / "logs/pipeline_runs.jsonl"),
    ) as ctx:
        code = run_checks()
        ctx.set_rows_out(2)
        ctx.add_output("reports/monitoring/monitoring_report.md")
        ctx.add_output("reports/monitoring/alerts.csv")
    raise SystemExit(code)
