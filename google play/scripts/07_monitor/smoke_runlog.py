"""Smoke test for _runlog.py using a temp JSONL file.

Run from ``google play/`` root::

    python3 scripts/07_monitor/smoke_runlog.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _runlog import run_logger  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "runs.jsonl"
        try:
            with run_logger(
                script="smoke_test.py",
                args="--dry-run",
                log_path=str(log_path),
            ) as ctx:
                ctx.set_rows_out(42)
                ctx.add_output("reports/quality_report.csv")
        except RuntimeError:
            pass

        # failure path
        try:
            with run_logger(
                script="smoke_fail.py",
                args="",
                log_path=str(log_path),
            ):
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, lines
        a = json.loads(lines[0])
        b = json.loads(lines[1])
        assert a["status"] == "success" and a["rows_out"] == 42
        assert b["status"] == "failed" and "boom" in (b.get("exception") or "")
    print("smoke_runlog: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
