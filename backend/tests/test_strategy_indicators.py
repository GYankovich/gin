"""Fast last-value indicators match the previous pandas rolling/EWM results."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.contracts import Candle
from app.modules.robots.trading.indicators.library import (
    build_frame,
    calc_atr,
    calc_ma,
    calc_rsi,
    previous_high,
)
from app.modules.robots_v2.strategy.indicators import (
    atr_value,
    breakout_high,
    rsi_value,
    sma_close,
    sma_volume,
    stochastic_k,
)


def _candles(n: int = 80) -> list[Candle]:
    base = datetime(2025, 1, 2, tzinfo=timezone.utc)
    out: list[Candle] = []
    px = 100.0
    for i in range(n):
        px += (1.2 if i % 3 else -0.8) + (i % 7) * 0.05
        out.append(Candle(
            interval="1h",
            time=base + timedelta(hours=i),
            open=px - 0.4,
            high=px + 1.1,
            low=px - 1.3,
            close=px,
            volume=1000 + i * 10,
            secid="AAA",
        ))
    return out


def test_sma_matches_pandas_rolling():
    candles = _candles()
    df = build_frame(candles)
    expected = float(calc_ma(df["close"], 20).iloc[-1])
    assert abs(sma_close(candles, 20) - expected) < 1e-9
    vol = float(df["volume"].rolling(20).mean().iloc[-1])
    assert abs(sma_volume(candles, 20) - vol) < 1e-9


def test_breakout_and_stoch_and_atr_match_pandas():
    candles = _candles()
    df = build_frame(candles)
    assert breakout_high(candles, 5) == previous_high(df["high"], 5)
    window = candles[-14:]
    last = float(window[-1].close)
    lo = min(float(c.low) for c in window)
    hi = max(float(c.high) for c in window)
    assert stochastic_k(candles, 14) == 100.0 * (last - lo) / (hi - lo)
    expected_atr = float(calc_atr(df["high"], df["low"], df["close"], 14).iloc[-1])
    assert abs(atr_value(candles, 14) - expected_atr) < 1e-9


def test_rsi_matches_pandas_ewm_and_incremental():
    candles = _candles()
    df = build_frame(candles)
    expected = float(calc_rsi(df["close"], 14).iloc[-1])
    assert abs(rsi_value(candles, 14) - expected) < 1e-9

    state: dict = {}
    last = None
    for i in range(15, len(candles) + 1):
        last = rsi_value(candles[:i], 14, state=state)
    assert last is not None
    assert abs(last - expected) < 1e-9
