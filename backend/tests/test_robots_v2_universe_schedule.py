"""Unit tests for day-by-day universe schedule + dividend filtering."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.corporate_actions.dividend_calendar_service import DividendExclusionPolicy
from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.backtest.host import BacktestHost
from app.modules.robots_v2.backtest.universe_schedule import (
    apply_dividend_exclusions,
    list_trade_dates,
)
from app.modules.robots_v2.config.v4_schema import ScheduleConfig, TradingRobotConfigV4


def _schedule_weekdays() -> ScheduleConfig:
    return ScheduleConfig.model_validate({
        "weekdays": [True, True, True, True, True, False, False],
        "timeFrom": "10:00",
        "timeTo": "18:45",
        "pollInterval": "5m",
    })


def test_list_trade_dates_skips_weekend():
    days = list_trade_dates(date(2025, 1, 3), date(2025, 1, 6), _schedule_weekdays())
    assert days == [date(2025, 1, 3), date(2025, 1, 6)]


def test_apply_dividend_exclusions_uses_cached_index():
    db = MagicMock()
    policy = DividendExclusionPolicy(strict_exclude_on_ex_date=True, exclude_weekdays_before_ex=0)
    ex_index = {"SBER": [date(2025, 1, 6)], "GAZP": []}
    kept = apply_dividend_exclusions(
        db,
        ["SBER", "GAZP"],
        trade_date=date(2025, 1, 6),
        policy=policy,
        ex_index=ex_index,
    )
    assert kept == ["GAZP"]


def _sample_config(tickers: list[str]) -> TradingRobotConfigV4:
    return TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, True, True],
                "timeFrom": "00:00",
                "timeTo": "23:59",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 5},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": tickers,
            "excluded": [],
            "maxAssets": 10,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 50,
            "stopLossPct": 5,
            "takeProfitPct": 10,
            "maxDailyLoss": 50_000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.0,
            "stopMode": "soft",
        },
    })


def _series(ticker: str, n: int = 40, start: float = 100.0) -> list[Candle]:
    base = datetime(2025, 1, 6, 7, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        px = start + i * 0.5
        out.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=px,
            high=px + 0.5,
            low=px - 0.5,
            close=px,
            volume=1000,
            secid=ticker,
        ))
    return out


def test_host_respects_universe_by_day():
    config = _sample_config(["AAA", "BBB"])
    candles = {
        "AAA": _series("AAA"),
        "BBB": _series("BBB", start=50.0),
    }
    day = date(2025, 1, 6)
    host = BacktestHost()
    result = host.run_sync(
        config=config,
        universe=["AAA", "BBB"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=42,
        trade_from=datetime(2025, 1, 6, 7, 0, tzinfo=timezone.utc),
        universe_by_day={day: ["AAA"]},
    )
    assert result.history_stats.get("universe_days") == 1
    traded_tickers = {str(t.get("figi") or "").upper() for t in result.trades}
    assert "BBB" not in traded_tickers
