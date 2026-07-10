from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots import service as robot_service
from app.modules.robots.trading.backtest.run_file_logger import (
    backtest_run_dir,
    read_backtest_run_summary_on_disk,
)


def test_read_backtest_run_summary_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.robots.trading.backtest.run_file_logger.resolve_backtest_log_root",
        lambda: tmp_path,
    )
    started = datetime(2026, 6, 24, 11, 0, tzinfo=timezone.utc)
    run_dir = backtest_run_dir(99, started_at=started)
    run_dir.mkdir(parents=True)
    payload = {"run_id": 99, "status": "FAILED", "error": "boom", "finished_at": started.isoformat()}
    (run_dir / "summary.json").write_text(json.dumps(payload), encoding="utf-8")

    read = read_backtest_run_summary_on_disk(99, started_at=started)
    assert read is not None
    assert read["status"] == "FAILED"
    assert read["error"] == "boom"


def test_maybe_reconcile_from_run_summary_updates_running(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.modules.robots.trading.backtest.run_file_logger.resolve_backtest_log_root",
        lambda: tmp_path,
    )
    started = datetime(2026, 6, 24, 11, 0, tzinfo=timezone.utc)
    run_dir = backtest_run_dir(163, started_at=started)
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": 163,
                "status": "FAILED",
                "error": "db down",
                "finished_at": started.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    db = MagicMock()
    db.execute.return_value.mappings.return_value.first.side_effect = [
        {"status": "RUNNING"},
    ]

    out = robot_service._maybe_reconcile_from_run_summary(db, 163, started)
    assert out == "FAILED"
    assert db.commit.called
