import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.backtest.host import BacktestHost, build_bar_timeline, max_drawdown_percent
from app.modules.robots_v2.backtest.service import v4_timeframe_to_interval_raw
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4


def _sample_config() -> TradingRobotConfigV4:
    return TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:30",
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
            "fixedList": ["AAA"],
            "excluded": [],
            "maxAssets": 5,
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
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    })


def _synthetic_uptrend(n: int = 30, start: float = 100.0) -> list[Candle]:
    base = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        px = start + i * 2.0
        out.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=px,
            high=px + 1,
            low=px - 1,
            close=px,
            volume=10_000 + i * 100,
            secid="AAA",
        ))
    return out


def test_v4_timeframe_mapping():
    assert v4_timeframe_to_interval_raw("5m") == "CANDLE_INTERVAL_5_MIN"
    assert v4_timeframe_to_interval_raw("1h") == "CANDLE_INTERVAL_HOUR"


def test_bar_timeline_sorted():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    series = {
        "A": [
            Candle("1h", t0, 1, 1, 1, 1, secid="A"),
            Candle("1h", t1, 2, 2, 2, 2, secid="A"),
        ],
        "B": [Candle("1h", t1, 3, 3, 3, 3, secid="B")],
    }
    assert build_bar_timeline(series) == [t0, t1]


def test_max_drawdown():
    curve = [
        {"equity": 100},
        {"equity": 110},
        {"equity": 88},
    ]
    assert max_drawdown_percent(curve) == 20.0


def test_backtest_host_replay_runs():
    config = _sample_config()
    candles = {"AAA": _synthetic_uptrend(40)}
    host = BacktestHost()
    result = asyncio.run(host.run(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_001,
    ))
    assert result.initial_capital == 100_000
    assert len(result.equity_curve) == 40
    assert result.history_stats["bars"] == 40
