"""Indicator helpers for v2 strategy plugins.

Last-value math on the candle tail — no pandas DataFrame per bar.
SMA / ATR / stochastic of the last window match the previous rolling
implementations exactly. RSI uses Wilder EWM (alpha=1/period); pass
``state`` (plugin ticker_state) for O(1) updates after the first seed.
"""

from __future__ import annotations

from typing import Any, Optional

from app.modules.robots.trading.contracts import Candle


def last_close(candles: list[Candle]) -> Optional[float]:
    if not candles:
        return None
    return float(candles[-1].close)


def last_volume(candles: list[Candle]) -> float:
    if not candles:
        return 0.0
    return float(candles[-1].volume or 0)


def sma_close(candles: list[Candle], period: int) -> Optional[float]:
    if period <= 0 or len(candles) < period:
        return None
    total = 0.0
    for c in candles[-period:]:
        total += float(c.close)
    return total / period


def sma_volume(candles: list[Candle], period: int) -> Optional[float]:
    if period <= 0 or len(candles) < period:
        return None
    total = 0.0
    for c in candles[-period:]:
        total += float(c.volume or 0)
    return total / period


def breakout_high(candles: list[Candle], lookback: int) -> Optional[float]:
    if lookback <= 0 or len(candles) < lookback + 1:
        return None
    peak = None
    for c in candles[-(lookback + 1):-1]:
        h = float(c.high)
        peak = h if peak is None else max(peak, h)
    return peak


def stochastic_k(candles: list[Candle], period: int = 14) -> Optional[float]:
    if period <= 0 or len(candles) < period:
        return None
    window = candles[-period:]
    last = float(window[-1].close)
    lo = min(float(c.low) for c in window)
    hi = max(float(c.high) for c in window)
    denom = hi - lo
    if denom <= 0:
        return None
    return 100.0 * (last - lo) / denom


def atr_value(candles: list[Candle], period: int = 14) -> Optional[float]:
    if period <= 0 or len(candles) < period + 1:
        return None
    window = candles[-(period + 1):]
    total = 0.0
    prev_close = float(window[0].close)
    for c in window[1:]:
        high = float(c.high)
        low = float(c.low)
        close = float(c.close)
        tr = high - low
        tr = max(tr, abs(high - prev_close), abs(low - prev_close))
        total += tr
        prev_close = close
    return total / period


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _rsi_seed(candles: list[Candle], period: int) -> tuple[float, float, float]:
    """Wilder EWM matching pandas ewm(alpha=1/period, adjust=False) on close.diff()."""
    alpha = 1.0 / max(period, 1)
    avg_gain = 0.0
    avg_loss = 0.0
    prev = float(candles[0].close)
    for c in candles[1:]:
        close = float(c.close)
        delta = close - prev
        prev = close
        gain = delta if delta > 0.0 else 0.0
        loss = -delta if delta < 0.0 else 0.0
        avg_gain = alpha * gain + (1.0 - alpha) * avg_gain
        avg_loss = alpha * loss + (1.0 - alpha) * avg_loss
    return _rsi_from_avgs(avg_gain, avg_loss), avg_gain, avg_loss


def rsi_value(
    candles: list[Candle],
    period: int,
    *,
    state: dict[str, Any] | None = None,
) -> Optional[float]:
    if period <= 0 or len(candles) < period + 1:
        return None
    key = f"_rsi_{period}"
    close = float(candles[-1].close)
    n = len(candles)
    if state is not None:
        st = state.get(key)
        if (
            isinstance(st, dict)
            and st.get("len") == n - 1
            and st.get("last_close") is not None
        ):
            delta = close - float(st["last_close"])
            gain = delta if delta > 0.0 else 0.0
            loss = -delta if delta < 0.0 else 0.0
            alpha = 1.0 / max(period, 1)
            avg_gain = alpha * gain + (1.0 - alpha) * float(st["avg_gain"])
            avg_loss = alpha * loss + (1.0 - alpha) * float(st["avg_loss"])
            rsi = _rsi_from_avgs(avg_gain, avg_loss)
            state[key] = {
                "len": n,
                "avg_gain": avg_gain,
                "avg_loss": avg_loss,
                "last_close": close,
                "rsi": rsi,
            }
            return rsi
        rsi, avg_gain, avg_loss = _rsi_seed(candles, period)
        state[key] = {
            "len": n,
            "avg_gain": avg_gain,
            "avg_loss": avg_loss,
            "last_close": close,
            "rsi": rsi,
        }
        return rsi
    return _rsi_seed(candles, period)[0]
