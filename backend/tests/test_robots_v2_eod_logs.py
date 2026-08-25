"""Tests for EOD flatten + event bus history."""

import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

import asyncio

from app.modules.robots_v2.config.v4_schema import RiskConfig, ScheduleConfig, TradingRobotConfigV4
from app.modules.robots_v2.engine.event_bus import EventBus
from app.modules.robots_v2.risk.eod import should_eod_flatten


def _schedule() -> ScheduleConfig:
    return ScheduleConfig.model_validate({
        "weekdays": [True, True, True, True, True, True, True],
        "timeFrom": "10:00",
        "timeTo": "18:30",
        "pollInterval": "5m",
    })


def _risk(**kwargs) -> RiskConfig:
    raw = {
        "capital": 100_000,
        "maxPositionSharePct": 10,
        "stopLossPct": 2,
        "takeProfitPct": 4,
        "maxDailyLoss": 5000,
        "maxConcurrentPositions": 3,
        "brokerCommissionPct": 0.05,
        "taxPct": 13,
        **kwargs,
    }
    return RiskConfig.model_validate(raw)


def test_eod_default_on_for_stock():
    risk = _risk()
    assert risk.eod_flatten_enabled_for("stock") is True
    assert risk.eod_flatten_enabled_for("perpetual") is False


def test_eod_window_triggers_near_close():
    risk = _risk()
    schedule = _schedule()
    # Monday 18:20 MSK = 15:20 UTC
    now = datetime(2026, 8, 10, 15, 20, tzinfo=timezone.utc)
    assert should_eod_flatten(risk=risk, schedule=schedule, instrument_type="stock", now=now) is True


def test_eod_not_in_window():
    risk = _risk()
    schedule = _schedule()
    now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)  # 13:00 MSK
    assert should_eod_flatten(risk=risk, schedule=schedule, instrument_type="stock", now=now) is False


def test_eod_not_all_evening_after_close():
    """Regression: after MOEX close, mins is largely negative — must NOT stay in EOD forever."""
    risk = _risk()
    schedule = _schedule()
    # Monday 22:20 MSK = 19:20 UTC
    now = datetime(2026, 8, 10, 19, 20, tzinfo=timezone.utc)
    assert should_eod_flatten(risk=risk, schedule=schedule, instrument_type="stock", now=now) is False


def test_eod_grace_just_after_close():
    risk = _risk()
    schedule = _schedule()
    # Monday 18:40 MSK = 15:40 UTC (10 min past close, within 30m grace)
    now = datetime(2026, 8, 10, 15, 40, tzinfo=timezone.utc)
    assert should_eod_flatten(risk=risk, schedule=schedule, instrument_type="stock", now=now) is True


def test_eod_explicit_off():
    risk = _risk(eodFlatten={"enabled": False, "minutesBeforeClose": 15})
    schedule = _schedule()
    now = datetime(2026, 8, 10, 15, 20, tzinfo=timezone.utc)
    assert should_eod_flatten(risk=risk, schedule=schedule, instrument_type="stock", now=now) is False


def test_event_bus_keeps_history():
    bus = EventBus(history_limit=10)

    async def _run():
        await bus.publish(7, "cycle", {"equity": 1})
        await bus.publish(7, "signal", {"ticker": "SBER"})
        await bus.publish(7, "order", {"ticker": "SBER"})

    asyncio.run(_run())
    all_items = bus.recent(7, limit=10)
    assert len(all_items) == 3
    signals = bus.recent(7, event_type="signal")
    assert len(signals) == 1
    assert signals[0]["ticker"] == "SBER"


def test_event_bus_drops_oldest_when_full():
    bus = EventBus()

    async def _run():
        q = bus.subscribe(1)
        for i in range(256):
            await bus.publish(1, "cycle", {"n": i})
        await bus.publish(1, "cycle", {"n": 256})
        first = q.get_nowait()
        assert first["n"] == 1
        last = first
        while True:
            try:
                last = q.get_nowait()
            except asyncio.QueueEmpty:
                break
        assert last["n"] == 256

    asyncio.run(_run())


def test_v4_config_accepts_eod_flatten():
    cfg = TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
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
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0},
        },
        "universe": {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 5},
        "risk": {
            "capital": 100000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "eodFlatten": {"enabled": True, "minutesBeforeClose": 20},
        },
    })
    assert cfg.risk.eod_flatten.minutes_before_close == 20
