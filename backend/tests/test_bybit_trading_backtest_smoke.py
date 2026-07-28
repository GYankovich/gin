"""
Smoke: type2_bybit history replay через BacktestTradingSession (mainnet policy, без API).

Проверяет end-to-end цепочку:
  type2_bybit config → SimBacktestBrokerFacade → run_history_replay → BacktestResult
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config
from app.modules.robots.trading.backtest.types import BacktestResult
from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
from app.modules.robots.trading.runtime.orchestrator import (
    TradingOrchestrator,
    build_allowed_symbols_by_date,
)
from app.modules.robots.trading.session_backtest import BacktestTradingSession


def _price_q(value: float) -> Dict[str, Any]:
    units = int(value)
    nano = int(round((value - units) * 1_000_000_000))
    return {"units": units, "nano": nano}


def _make_crypto_candles(
    *,
    start: datetime | None = None,
    count: int = 48,
    step_hours: int = 1,
    base_price: float = 50_000.0,
) -> List[Dict[str, Any]]:
    """Synthetic BTCUSDT hourly bars with oscillating close (enough for reversion_to_ma)."""
    t0 = start or datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
    out: List[Dict[str, Any]] = []
    for i in range(count):
        ts = t0 + timedelta(hours=i * step_hours)
        # Dip every 12 bars → potential BUY; recovery → SELL
        wave = 0.92 + 0.16 * ((i % 12) / 11.0)
        close = base_price * wave
        q = _price_q(close)
        out.append(
            {
                "time": ts.isoformat().replace("+00:00", "Z"),
                "open": q,
                "high": _price_q(close * 1.002),
                "low": _price_q(close * 0.998),
                "close": q,
                "volume": 500 + i * 5,
            }
        )
    return out


def _type2_bybit_smoke_config() -> Dict[str, Any]:
    model = validate_robot_config(
        robot_type=2,
        raw={
            "broker_type": "bybit",
            "allowed_symbols": ["BTCUSDT"],
            "bybit": {"instrument_category": "linear", "leverage": 1},
            "costs": {
                "maker_fee_rate": 0.0001,
                "taker_fee_rate": 0.0006,
                "funding_rate_enabled": False,
            },
            "signal_generation": {
                "strategy": "reversion_to_ma",
                "params": {
                    "interval": "1h",
                    "ma_period": 10,
                    "rsi_period": 7,
                    "deviation_pct": 1.5,
                    "use_volume_filter": False,
                },
                "data_source": "bybit",
                "update_interval_seconds": 60,
            },
            "risk": {
                "max_position_size": 0.5,
                "max_positions": 3,
                "stop_loss_percent": 5.0,
            },
        },
        broker_type="bybit",
    )
    return dump_robot_config(model)


def _build_session(
    config: Dict[str, Any],
    candles_by_symbol: Dict[str, List[Dict[str, Any]]],
    allowed_by_date: Dict[str, List[str]],
    *,
    initial_capital: float = 10_000.0,
) -> BacktestTradingSession:
    broker = SimBacktestBrokerFacade(
        initial_capital=initial_capital,
        candles_by_figi=candles_by_symbol,
        ndfl_rate=0.0,
        robot_config=config,
    )
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    db.execute.return_value.fetchone.return_value = None
    return BacktestTradingSession(
        db=db,
        schema="ganaly",
        robot_id=9001,
        user_id=1,
        token_id=0,
        token="smoke-token",
        config=config,
        sim_broker=broker,
        allowed_figis_by_date=allowed_by_date,
    )


def test_bybit_backtest_session_smoke_replay():
    """Full BacktestTradingSession replay on synthetic BTCUSDT candles."""

    async def _run() -> BacktestResult:
        config = _type2_bybit_smoke_config()
        candles = _make_crypto_candles(count=48)
        candles_by_symbol = {"BTCUSDT": candles}
        allowed_by_date = build_allowed_symbols_by_date(candles_by_symbol)
        session = _build_session(config, candles_by_symbol, allowed_by_date)
        return await session.run_history_replay(candles_by_figi=candles_by_symbol)

    result = asyncio.run(_run())

    assert isinstance(result, BacktestResult)
    assert result.initial_capital == pytest.approx(10_000.0)
    assert result.final_equity > 0
    assert len(result.equity_curve) > 0


def test_bybit_orchestrator_backtest_replay_smoke():
    """TradingOrchestrator.run_backtest_replay with crypto config (no prefetch)."""

    async def _run() -> BacktestResult:
        config = _type2_bybit_smoke_config()
        candles = _make_crypto_candles(count=36)
        candles_by_symbol = {"BTCUSDT": candles}
        allowed_by_date = build_allowed_symbols_by_date(candles_by_symbol)
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        db.execute.return_value.fetchone.return_value = None
        orch = TradingOrchestrator()
        return await orch.run_backtest_replay(
            db=db,
            schema="ganaly",
            robot_id=9002,
            user_id=1,
            token_id=0,
            token="smoke-token",
            config=config,
            candles_by_figi=candles_by_symbol,
            allowed_figis_by_date=allowed_by_date,
            initial_capital=5_000.0,
        )

    result = asyncio.run(_run())

    assert isinstance(result, BacktestResult)
    assert result.initial_capital == pytest.approx(5_000.0)
    assert result.final_equity > 0
    assert len(result.equity_curve) >= 1


def test_type2_bybit_config_validates_for_smoke():
    cfg = _type2_bybit_smoke_config()
    assert cfg["schema_profile"] == "type2_bybit"
    assert cfg["broker_type"] == "bybit"
    assert "BTCUSDT" in cfg["allowed_symbols"]
