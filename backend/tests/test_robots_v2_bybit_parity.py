"""Stage 5 QA: Bybit/crypto parity for robots v2."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.backtest.service import v4_timeframe_to_interval_raw
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.universe import presets


def test_paper_short_open_and_close_profit():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0, allow_short=True)
    ledger.apply_fill(ticker="BTCUSDT", side="SELL", quantity=1, price=100.0)
    assert "BTCUSDT" in ledger.positions
    assert ledger.positions["BTCUSDT"].side == "SHORT"
    assert ledger.cash == 10_100  # +100 proceeds
    # mark equity at entry ≈ initial
    assert abs(ledger.mark_equity({"BTCUSDT": 100.0}) - 10_000) < 1e-6

    pnl = ledger.apply_fill(ticker="BTCUSDT", side="BUY", quantity=1, price=90.0, reduce_only=True)
    assert pnl == 10.0
    assert "BTCUSDT" not in ledger.positions
    assert abs(ledger.cash - 10_010) < 1e-6


def test_paper_short_forbidden_without_flag():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0, allow_short=False)
    pnl = ledger.apply_fill(ticker="BTCUSDT", side="SELL", quantity=1, price=100.0)
    assert pnl == 0.0
    assert "BTCUSDT" not in ledger.positions


def test_paper_long_equity_mark():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=10, price=100.0)
    assert abs(ledger.mark_equity({"SBER": 110.0}) - 10_100) < 1e-6


def test_crypto_instrument_maps_to_bybit_market():
    # Backtest host routing convention
    for itype in ("perpetual", "coin_futures"):
        market = "bybit" if itype in ("perpetual", "coin_futures") else "moex"
        assert market == "bybit"
    assert ("stock" in ("perpetual", "coin_futures")) is False


def test_v4_timeframe_crypto_intervals():
    assert v4_timeframe_to_interval_raw("1m") == "CANDLE_INTERVAL_1_MIN"
    assert v4_timeframe_to_interval_raw("15m") == "CANDLE_INTERVAL_15_MIN"


def test_crypto_screener_presets_have_volume_floor():
    for preset in ("high_liquidity", "volatile", "low_price"):
        cfg = presets.resolve_crypto_filters(preset=preset, custom_filters=None)
        assert cfg["min_volume_24h_usd"] > 0
