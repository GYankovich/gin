"""V2 BacktestHost crypto funding (parity with session_backtest R7.3)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.backtest.funding import (
    apply_funding_charges_for_bar,
    crypto_funding_enabled,
    funding_events_in_window,
    instrument_category_for_config,
)
from app.modules.robots_v2.backtest.host import BacktestHost
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.paper_ledger import PaperLedger, PaperPosition
from app.modules.trading_core.contracts import Candle


def _perp_config() -> TradingRobotConfigV4:
    return TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "perpetual",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, True, True],
                "timeFrom": "00:00",
                "timeTo": "23:59",
                "pollInterval": "1h",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 5},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["BTCUSDT"],
            "excluded": [],
            "maxAssets": 5,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 10_000,
            "maxPositionSharePct": 50,
            "stopLossPct": 5,
            "takeProfitPct": 10,
            "maxDailyLoss": 5_000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.0,
            "taxPct": 0,
            "slippagePct": 0.0,
            "stopMode": "soft",
            "eodFlatten": {"enabled": False},
        },
    })


def test_crypto_funding_enabled_for_perp():
    cfg = _perp_config()
    assert crypto_funding_enabled(cfg) is True
    assert instrument_category_for_config(cfg) == "linear"
    cfg.core.instrument_type = "stock"
    assert crypto_funding_enabled(cfg) is False


def test_funding_events_in_window_datetime():
    events = [
        {"funding_time": datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc), "funding_rate": 0.0001},
        {"funding_time": datetime(2024, 6, 1, 16, 0, tzinfo=timezone.utc), "funding_rate": 0.0002},
    ]
    due = funding_events_in_window(
        datetime(2024, 6, 1, 7, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
        events,
    )
    assert len(due) == 1
    assert due[0]["funding_rate"] == 0.0001


def test_paper_ledger_funding_long_pays():
    ledger = PaperLedger(cash=10_000.0, commission_rate=0.0, allow_short=True)
    ledger.positions["BTCUSDT"] = PaperPosition(
        ticker="BTCUSDT", side="LONG", quantity=1, avg_entry_price=100.0,
    )
    cash_before = ledger.cash
    adj = ledger.apply_funding_charge("BTCUSDT", 0.0001, mark_price=100.0)
    assert adj == -0.01
    assert ledger.cash == cash_before - 0.01


def test_paper_ledger_funding_short_receives():
    ledger = PaperLedger(cash=10_000.0, commission_rate=0.0, allow_short=True)
    ledger.positions["BTCUSDT"] = PaperPosition(
        ticker="BTCUSDT", side="SHORT", quantity=1, avg_entry_price=100.0,
    )
    cash_before = ledger.cash
    adj = ledger.apply_funding_charge("BTCUSDT", 0.0001, mark_price=100.0)
    assert adj == 0.01
    assert ledger.cash == cash_before + 0.01


def test_apply_funding_charges_for_bar_dedupes():
    ledger = PaperLedger(cash=10_000.0, commission_rate=0.0, allow_short=True)
    ledger.positions["BTCUSDT"] = PaperPosition(
        ticker="BTCUSDT", side="LONG", quantity=1, avg_entry_price=100.0,
    )
    ft = datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc)
    funding = {"BTCUSDT": [{"funding_time": ft, "funding_rate": 0.0001}]}
    keys: set[tuple[str, str]] = set()
    adj1 = apply_funding_charges_for_bar(
        ledger,
        funding_by_symbol=funding,
        prev_bar_time=datetime(2024, 6, 1, 7, 0, tzinfo=timezone.utc),
        bar_time=datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
        prices={"BTCUSDT": 100.0},
        applied_keys=keys,
    )
    adj2 = apply_funding_charges_for_bar(
        ledger,
        funding_by_symbol=funding,
        prev_bar_time=datetime(2024, 6, 1, 7, 0, tzinfo=timezone.utc),
        bar_time=datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
        prices={"BTCUSDT": 100.0},
        applied_keys=keys,
    )
    assert adj1 == -0.01
    assert adj2 == 0.0
    assert len(keys) == 1


def test_backtest_host_applies_funding_with_open_position():
    """Flat book → no cash hit; seeded long → debit notional * rate once."""
    config = _perp_config()
    base = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(8):
        px = 100.0
        candles.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=px,
            high=px,
            low=px,
            close=px,
            volume=1_000,
            secid="BTCUSDT",
        ))

    funding = {
        "BTCUSDT": [
            {
                "funding_time": base + timedelta(hours=3),
                "funding_rate": 0.01,
            }
        ],
    }

    result_flat = BacktestHost().run_sync(
        config=config,
        universe=["BTCUSDT"],
        candles_by_ticker={"BTCUSDT": candles},
        initial_capital=10_000,
        session_id=42_001,
        funding_by_symbol=funding,
    )
    assert result_flat.funding_charges_total == 0.0
    assert result_flat.history_stats.get("funding_events", 0) == 0

    ledger = PaperLedger(cash=10_000.0, commission_rate=0.0, allow_short=True)
    ledger.positions["BTCUSDT"] = PaperPosition(
        ticker="BTCUSDT", side="LONG", quantity=1, avg_entry_price=100.0,
    )
    keys: set[tuple[str, str]] = set()
    total = 0.0
    prev = None
    for c in candles:
        total += apply_funding_charges_for_bar(
            ledger,
            funding_by_symbol=funding,
            prev_bar_time=prev,
            bar_time=c.time,
            prices={"BTCUSDT": float(c.close)},
            applied_keys=keys,
        )
        prev = c.time
    assert total == -1.0  # 100 * 0.01
    assert ledger.cash == 9_999.0
