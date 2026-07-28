"""Tests for backtest persist checkpoint and DB retry."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError

from app.core.db_retry import run_db_with_retry
import logging

from app.modules.robots.trading.backtest.persist_checkpoint import (
    backtest_result_from_dict,
    backtest_result_to_dict,
    build_persist_checkpoint_payload,
    delete_persist_checkpoint,
    read_persist_checkpoint,
    write_persist_checkpoint,
)
from app.modules.robots.trading.backtest.types import BacktestResult
from app.modules.robots.trading.backtest.run_file_logger import append_backtest_run_log_line


def test_backtest_result_roundtrip():
    res = BacktestResult(
        initial_capital=10_000.0,
        final_equity=11_234.5,
        total_return_percent=12.345,
        max_drawdown_percent=3.2,
        trades=[{"figi": "BTCUSDT", "pnl_net": 100}],
        signals=[{"figi": "BTCUSDT", "signal_type": "BUY"}],
        cancelled=False,
    )
    restored = backtest_result_from_dict(backtest_result_to_dict(res))
    assert restored.final_equity == res.final_equity
    assert restored.trades == res.trades


def test_persist_checkpoint_write_read(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.robots.trading.backtest.persist_checkpoint.backtest_run_dir",
        lambda run_id, started_at=None: tmp_path / f"run_{run_id}",
    )
    started = datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc)
    res = BacktestResult(
        initial_capital=10_000.0,
        final_equity=10_500.0,
        total_return_percent=5.0,
        max_drawdown_percent=1.0,
    )
    payload = build_persist_checkpoint_payload(
        run_id=42,
        run_started_at=started,
        robot_pk=7,
        bt_run_id=None,
        slippage_pct=0.1,
        is_crypto_backtest=True,
        requested_from_utc=started,
        requested_to_utc=started,
        skip_heavy_persist=False,
        pipeline_user_cancelled=False,
        td_total=10,
        config={"strategy": "type2_bybit"},
        res=res,
        decisions_rows=[],
        result={"run_id": 42},
    )
    write_persist_checkpoint(42, started, payload)
    loaded = read_persist_checkpoint(42, started_at=started)
    assert loaded is not None
    assert loaded["run_id"] == 42
    assert loaded["res"]["final_equity"] == 10_500.0
    delete_persist_checkpoint(42, started)
    assert read_persist_checkpoint(42, started_at=started) is None


def test_append_backtest_run_log_line(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.robots.trading.backtest.run_file_logger.find_backtest_run_dir",
        lambda run_id: tmp_path / f"run_{run_id}",
    )
    append_backtest_run_log_line(99, logging.INFO, "RECONCILE test line")
    log_path = tmp_path / "run_99" / "backtest.log"
    assert log_path.is_file()
    assert "RECONCILE test line" in log_path.read_text(encoding="utf-8")


def test_run_db_with_retry_recovers():
    calls = {"n": 0}

    class _Db:
        def rollback(self) -> None:
            pass

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("stmt", {}, Exception("connection lost"))
        return "ok"

    out = run_db_with_retry(_Db(), _fn, max_attempts=5, delay_sec=0.0)
    assert out == "ok"
    assert calls["n"] == 3
