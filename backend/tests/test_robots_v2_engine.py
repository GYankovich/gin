"""Tests for robots v2 paper engine and risk."""

import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots.trading.contracts import Signal
from app.modules.robots_v2.config.v4_schema import RiskConfig
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.adapter import risk_params_from_v4
from app.modules.robots_v2.risk.engine import RiskEngine


def _risk_config() -> RiskConfig:
    return RiskConfig.model_validate({
        "capital": 100_000,
        "maxPositionSharePct": 10,
        "stopLossPct": 2,
        "takeProfitPct": 4,
        "maxDailyLoss": 5000,
        "maxConcurrentPositions": 3,
        "brokerCommissionPct": 0.05,
        "taxPct": 13,
    })


def test_paper_ledger_buy_and_equity():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0005)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=10, price=100.0)
    assert "SBER" in ledger.positions
    assert ledger.cash < 100_000


def test_risk_adapter_maps_v4_fields():
    params = risk_params_from_v4(_risk_config())
    assert params.max_position_pct == 10
    assert params.stop_loss_pct == 2


def test_risk_engine_denies_when_entries_paused():
    engine = RiskEngine(_risk_config())
    engine.pause_entries()
    signal = Signal(secid="SBER", side="BUY", reason="test", price_at_signal=100.0)
    decision, audit = engine.pre_trade(signal, cash=100_000, equity=100_000, positions={})
    assert not decision.allow
    assert audit.code == "ENTRIES_PAUSED"
