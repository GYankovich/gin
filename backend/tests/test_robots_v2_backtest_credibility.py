"""Credibility mode: intrabar SL/TP, NDFL, liquidity cap, cost stress."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.backtest.credibility import (
    build_cost_stress,
    cap_fill_quantity,
    intrabar_protective_hit,
    plan_intrabar_sl_tp_intents,
)
from app.modules.robots_v2.backtest.host import BacktestHost
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.paper_ledger import PaperLedger


def _sample_config() -> TradingRobotConfigV4:
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


def test_cap_fill_quantity_unknown_volume_uncapped():
    assert cap_fill_quantity(500, None) == (500, False)
    assert cap_fill_quantity(500, 0) == (500, False)


def test_cap_fill_quantity_ten_percent_participation():
    filled, capped = cap_fill_quantity(500, 1_000, participation=0.10)
    assert capped is True
    assert filled == 100


def test_intrabar_both_hit_prefers_stop_loss():
    hit = intrabar_protective_hit(
        is_long=True,
        stop_loss=95.0,
        take_profit=110.0,
        high=120.0,
        low=90.0,
    )
    assert hit == ("stop_loss", 95.0)


def test_intrabar_tp_only_when_low_holds():
    hit = intrabar_protective_hit(
        is_long=True,
        stop_loss=95.0,
        take_profit=110.0,
        high=120.0,
        low=100.0,
    )
    assert hit == ("take_profit", 110.0)


def test_intrabar_short_both_hit_prefers_stop():
    hit = intrabar_protective_hit(
        is_long=False,
        stop_loss=110.0,
        take_profit=90.0,
        high=120.0,
        low=80.0,
    )
    assert hit == ("stop_loss", 110.0)


def test_plan_intrabar_emits_market_at_stop_not_close():
    bar = Candle(
        interval="1h",
        time=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
        open=100, high=101, low=90, close=100,
        volume=10_000, secid="SBER",
    )
    intents = plan_intrabar_sl_tp_intents(
        [{"figi": "SBER", "side": "long", "quantity": 10, "entry_price": 100.0}],
        {"SBER": 100.0},
        {"SBER": bar},
        {"stop_loss_percent": 5, "take_profit_percent": 10, "min_hold_seconds": 0, "min_tp_move_bps": 0},
        cost_kw={"broker_commission_rate": 0.0005, "ndfl_rate": 0.13},
    )
    assert len(intents) == 1
    assert intents[0].reason == "stop_loss"
    assert intents[0].order_type == "MARKET"
    assert intents[0].meta.get("intrabar") is True
    assert intents[0].price < 100.0
    assert abs(intents[0].price - 100.0) > 1.0


def test_paper_ledger_ndfl_on_profitable_long_close():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0, tax_rate=0.13)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=10, price=100.0)
    pnl = ledger.apply_fill(ticker="SBER", side="SELL", quantity=10, price=110.0, reduce_only=True)
    # Gross 100; tax 13; net 87. Cash: 10_000 - 1000 + 1100 - 13 = 10_087.
    assert abs(pnl - 87.0) < 1e-6
    assert abs(ledger.tax_paid - 13.0) < 1e-6
    assert abs(ledger.cash - 10_087) < 1e-6
    assert abs(ledger.last_fill_tax - 13.0) < 1e-6


def test_paper_ledger_no_ndfl_on_loss():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0, tax_rate=0.13)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=10, price=100.0)
    pnl = ledger.apply_fill(ticker="SBER", side="SELL", quantity=10, price=90.0, reduce_only=True)
    assert pnl == -100.0
    assert ledger.tax_paid == 0.0
    assert ledger.last_fill_tax == 0.0


def test_paper_ledger_crypto_skips_tax_when_rate_zero():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0, allow_short=True, tax_rate=0.0)
    ledger.apply_fill(ticker="BTCUSDT", side="SELL", quantity=1, price=100.0)
    pnl = ledger.apply_fill(ticker="BTCUSDT", side="BUY", quantity=1, price=90.0, reduce_only=True)
    assert pnl == 10.0
    assert ledger.tax_paid == 0.0


def test_cost_stress_overlay_is_analytical():
    trades = [
        {"price": 100.0, "quantity": 10, "commission": 5.0},
        {"price": 110.0, "quantity": 10, "commission": 5.5},
    ]
    stress = build_cost_stress(
        trades=trades,
        initial_capital=10_000,
        final_equity=10_100,
        slippage_pct=0.5,
    )
    extra_comm = 10.5 * 0.5
    extra_slip = (1000 + 1100) * 0.005
    assert abs(stress["commission_plus_50pct"]["extra_cost"] - extra_comm) < 1e-6
    assert abs(stress["slippage_x2"]["extra_cost"] - extra_slip) < 1e-6
    assert stress["combined"]["final_equity"] < stress["commission_plus_50pct"]["final_equity"]


def _breakout_then_intrabar_stop() -> list[Candle]:
    base = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(30):
        out.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=100, high=101, low=99, close=100,
            volume=1_000, secid="AAA",
        ))
    out.append(Candle(
        interval="CANDLE_INTERVAL_HOUR",
        time=base + timedelta(hours=30),
        open=100, high=132, low=100, close=130,
        volume=50_000, secid="AAA",
    ))
    # Next-open fill bar — range stays above a 5% stop.
    out.append(Candle(
        interval="CANDLE_INTERVAL_HOUR",
        time=base + timedelta(hours=31),
        open=110, high=112, low=109, close=111,
        volume=10_000, secid="AAA",
    ))
    # Close stays above SL, low pierces it.
    out.append(Candle(
        interval="CANDLE_INTERVAL_HOUR",
        time=base + timedelta(hours=32),
        open=111, high=112, low=80, close=111,
        volume=10_000, secid="AAA",
    ))
    return out


def test_host_intrabar_stop_fills_at_stop_not_close():
    config = _sample_config()
    candles = {"AAA": _breakout_then_intrabar_stop()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_041,
    )
    stops = [t for t in result.trades if t.get("reason") == "stop_loss"]
    assert stops, "expected an intrabar stop-loss fill"
    stop = stops[0]
    close_of_stop_bar = 111.0
    assert float(stop["price"]) < close_of_stop_bar
    assert result.credibility.get("intrabar_sl_tp") is True
    assert result.fee_summary.get("tax_total") is not None
    assert "cost_stress" in result.fee_summary
    assert result.fee_summary["cost_stress"]["combined"]["final_equity"] <= result.final_equity
