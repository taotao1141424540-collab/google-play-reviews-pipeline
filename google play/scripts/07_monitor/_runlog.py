"""Run-level structured logging to JSONL (append-only).

Run from repo root ``google play/`` so relative paths like ``logs/pipeline_runs.jsonl`` resolve correctly.
"""
from __future__ import annotations

import json
import subprocess
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return out.decode().strip()[:40]
    except Exception:
        return None


@dataclass
class RunContext:
    script: str
    args: str
    rows_in: Optional[int]
    output_files: List[str] = field(default_factory=list)
    rows_out: Optional[int] = None

    def set_rows_out(self, n: int) -> None:
        self.rows_out = int(n)

    def add_output(self, path: str) -> None:
        self.output_files.append(path)


@contextmanager
def run_logger(
    script: str,
    args: str = "",
    rows_in: Optional[int] = None,
    output_files: Optional[List[str]] = None,
    log_path: str = "logs/pipeline_runs.jsonl",
) -> Iterator[RunContext]:
    """Append one JSON line per run; on failure records *failed* then re-raises."""
    ctx = RunContext(
        script=script,
        args=args,
        rows_in=rows_in,
        output_files=list(output_files or []),
    )
    start = time.time()
    start_iso = _utc_now_iso()
    status = "success"
    exc_str: Optional[str] = None
    try:
        yield ctx
    except BaseException as e:  # noqa: BLE001 — we re-raise after logging
        status = "failed"
        exc_str = "".join(traceback.format_exception_only(type(e), e)).strip()
        raise
    finally:
        end_iso = _utc_now_iso()
        duration = int(max(0.0, time.time() - start))
        short = Path(script).stem
        run_id = f"{start_iso.replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:6]}_{short}"
        record: dict[str, Any] = {
            "run_id": run_id,
            "script": script,
            "args": args,
            "start_utc": start_iso,
            "end_utc": end_iso,
            "duration_sec": duration,
            "status": status,
            "exception": exc_str,
            "rows_in": ctx.rows_in,
            "rows_out": ctx.rows_out,
            "output_files": ctx.output_files,
            "git_sha": _git_sha(),
        }
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # Minimal manual smoke: python scripts/07_monitor/_runlog.py
    with run_logger(script="scripts/07_monitor/_runlog.py", args="--smoke", log_path="logs/pipeline_runs.jsonl") as c:
        c.set_rows_out(0)
        c.add_output("logs/pipeline_runs.jsonl")
    print("Wrote one smoke line to logs/pipeline_runs.jsonl")
