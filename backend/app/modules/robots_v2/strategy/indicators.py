"""Indicator helpers for v2 strategy plugins."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from app.modules.robots.trading.contracts import Candle
from app.modules.robots.trading.indicators.library import (
    build_frame,
    calc_atr,
    calc_ma,
    calc_rsi,
    previous_high,
)


def last_close(candles: list[Candle]) -> Optional[float]:
    if not candles:
        return None
    return float(candles[-1].close)


def last_volume(candles: list[Candle]) -> float:
    if not candles:
        return 0.0
    return float(candles[-1].volume or 0)


def sma_close(candles: list[Candle], period: int) -> Optional[float]:
    if len(candles) < period:
        return None
    df = build_frame(candles)
    ma = calc_ma(df["close"], period)
    val = ma.iloc[-1]
    return None if pd.isna(val) else float(val)


def sma_volume(candles: list[Candle], period: int) -> Optional[float]:
    if len(candles) < period:
        return None
    df = build_frame(candles)
    avg = df["volume"].rolling(period).mean()
    val = avg.iloc[-1]
    return None if pd.isna(val) else float(val)


def breakout_high(candles: list[Candle], lookback: int) -> Optional[float]:
    if len(candles) < lookback + 1:
        return None
    df = build_frame(candles)
    return previous_high(df["high"], lookback)


def rsi_value(candles: list[Candle], period: int) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    df = build_frame(candles)
    rsi = calc_rsi(df["close"], period)
    val = rsi.iloc[-1]
    return None if pd.isna(val) else float(val)


def stochastic_k(candles: list[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period:
        return None
    df = build_frame(candles)
    low_min = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    denom = (high_max - low_min).replace(0, pd.NA)
    k = 100.0 * (df["close"] - low_min) / denom
    val = k.iloc[-1]
    return None if pd.isna(val) else float(val)


def atr_value(candles: list[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    df = build_frame(candles)
    atr = calc_atr(df["high"], df["low"], df["close"], period)
    val = atr.iloc[-1]
    return None if pd.isna(val) else float(val)
