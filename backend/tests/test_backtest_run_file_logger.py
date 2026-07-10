"""Unit tests for per-run backtest file logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.modules.robots.trading.backtest import run_file_logger as rfl


def test_backtest_run_dir_uses_dd_mm_yyyy(tmp_path, monkeypatch):
    monkeypatch.setattr(rfl.settings, "BACKTEST_LOG_DIR", str(tmp_path))
    started = datetime(2026, 6, 18, 9, 30, tzinfo=timezone.utc)
    run_dir = rfl.backtest_run_dir(101, started_at=started)
    assert run_dir.parent.name == "18.06.2026"
    assert run_dir.name == "run_101"


def test_open_and_close_backtest_run_log_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(rfl.settings, "BACKTEST_LOG_DIR", str(tmp_path))
    started = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
    log_path = rfl.open_backtest_run_log(
        7,
        started_at=started,
        meta={"run_id": 7, "strategy": "grain_seed"},
    )
    rfl.log_backtest_run_info("hello %s", "world")
    rfl.log_backtest_run_phase(7, "scoring", phase_units_done=1, phase_units_total=10)
    rfl.close_backtest_run_log(
        7,
        status="SUCCESS",
        summary={"trades_total": 3},
    )
    assert log_path.exists()
    text = log_path.read_text(encoding="utf-8")
    assert "BACKTEST RUN 7 START" in text
    assert "STAGE" not in text
    assert "hello world" in text
    assert "PHASE scoring" in text
    assert "BACKTEST RUN 7 END status=SUCCESS" in text

    meta = json.loads((log_path.parent / "meta.json").read_text(encoding="utf-8"))
    assert meta["strategy"] == "grain_seed"
    summary = json.loads((log_path.parent / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "SUCCESS"
    assert summary["summary"]["trades_total"] == 3
