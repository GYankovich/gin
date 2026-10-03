"""V2 paper cycle signal log: executed + rejected reasons."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.cycle_sync import run_paper_cycle_sync
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.trading_core.contracts import Candle, Signal
from app.modules.trading_core.risk.manager import RiskDecision


def _cfg() -> TradingRobotConfigV4:
    return TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:40",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 10},
        },
        "universe": {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 1, "exitOnDrop": False},
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 1,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.1,
            "stopMode": "soft",
        },
    })


def test_signal_log_records_risk_reject_and_entry():
    cfg = _cfg()
    ledger = PaperLedger(cash=100_000.0, commission_rate=0.0005)
    risk = RiskEngine(cfg.risk)
    risk.begin_session(100_000.0)

    runtime = MagicMock()
    runtime.evaluate.return_value = [
        Signal(secid="SBER", side="BUY", reason="momentum_breakout", price_at_signal=250.0),
        Signal(secid="GAZP", side="BUY", reason="momentum_breakout", price_at_signal=150.0),
    ]

    decisions = [
        (RiskDecision(allow=True, quantity=10, reason="ALLOW"), SimpleNamespace(code="ALLOW")),
        (RiskDecision(allow=False, quantity=0, reason="MAX_POSITIONS"), SimpleNamespace(code="MAX_POSITIONS")),
    ]
    risk.pre_trade = MagicMock(side_effect=decisions)  # type: ignore[method-assign]
    risk.build_entry_intent = RiskEngine.build_entry_intent.__get__(risk, RiskEngine)

    exec_svc = MagicMock()
    exec_svc.poll_resting_fills_sync.return_value = []
    exec_svc._resting = {}
    exec_svc._limit_would_fill.return_value = True
    fill = SimpleNamespace(
        status="filled",
        side="BUY",
        ticker="SBER",
        reason="momentum_breakout",
        pnl=0.0,
        price=250.0,
        quantity=10,
        kind="entry",
    )
    exec_svc.execute_intent_sync.return_value = fill

    clock = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    candles = {
        "SBER": [Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=clock, open=249, high=251, low=248, close=250, volume=1000, secid="SBER",
        )],
        "GAZP": [Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=clock, open=149, high=151, low=148, close=150, volume=1000, secid="GAZP",
        )],
    }
    out = run_paper_cycle_sync(
        robot_id=1,
        config=cfg,
        universe=["SBER", "GAZP"],
        ledger=ledger,
        risk=risk,
        prices={"SBER": 250.0, "GAZP": 150.0},
        candle_history=candles,
        session_id=1,
        cycle_number=1,
        execution=exec_svc,
        runtime=runtime,
        now=clock,
        defer_market_fills=False,
    )

    log = out["signal_log"]
    assert len(log) == 2
    executed = [e for e in log if e["was_executed"] == 1]
    rejected = [e for e in log if e["status"] == "rejected"]
    assert len(executed) == 1
    assert executed[0]["figi"] == "SBER"
    assert executed[0]["reason"] == "momentum_breakout"
    assert len(rejected) == 1
    assert rejected[0]["figi"] == "GAZP"
    assert rejected[0]["reject_reason"] == "MAX_POSITIONS"
