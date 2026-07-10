"""
Библиотека технических индикаторов для торговых стратегий.

Чистые функции (без побочных эффектов) поверх pandas DataFrame / Series.

Все функции рассчитаны на то, чтобы давать **идентичный** результат с
существующей реализацией в `grain_seed.py` (см. тест test_indicators), чтобы
рефакторинг не менял торговое поведение.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingIndicatorsLibrary [1]
#/// Исходный модуль `backend/app/modules/robots/trading/indicators/library.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from app.modules.robots.trading.contracts import Candle


CandleLike = Union[Dict[str, Any], Candle]


# ---------------------------------------------------------------------------
# Нормализация цены T-Invest формата (units/nano)
# ---------------------------------------------------------------------------

def price_from_quotation(q: Optional[Any]) -> float:
    """Парсит число в формате T-Invest Quotation (`{units, nano}`) либо число.

    Возвращает 0.0 при невозможности.
    """
    if q is None:
        return 0.0
    if isinstance(q, (int, float)):
        return float(q)
    if isinstance(q, str):
        try:
            return float(q)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(q, dict):
        units = int(q.get("units", 0) or 0)
        nano = int(q.get("nano", 0) or 0)
        return float(units) + float(nano) / 1e9
    return 0.0


# ---------------------------------------------------------------------------
# Построение DataFrame из свечей
# ---------------------------------------------------------------------------

def build_frame(candles: List[CandleLike]) -> pd.DataFrame:
    """Строит DataFrame с колонками open/high/low/close/volume.

    Принимает как список dict (T-Invest формат с units/nano), так и список Candle.
    Чистит inf/NaN, заменяет на 0.0 — поведение идентично текущему `_build_frame`
    в `grain_seed.py`.
    """
    rows: List[Dict[str, float]] = []
    for c in candles:
        if isinstance(c, Candle):
            rows.append({
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume or 0),
            })
        else:
            rows.append({
                "open": price_from_quotation(c.get("open")),
                "high": price_from_quotation(c.get("high")),
                "low": price_from_quotation(c.get("low")),
                "close": price_from_quotation(c.get("close")),
                "volume": float(c.get("volume", 0) or 0),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan)
    return df.fillna(0.0)


# ---------------------------------------------------------------------------
# Moving average
# ---------------------------------------------------------------------------

def calc_ma(close: pd.Series, period: int) -> pd.Series:
    """Простая скользящая средняя (Simple MA) — `rolling(period).mean()`."""
    return close.rolling(period).mean()


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def calc_bb(close: pd.Series, period: int, stddev: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Возвращает (mid, upper, lower) для Bollinger Bands.

    mid = SMA(close, period); upper = mid + stddev * std; lower = mid - stddev * std.
    """
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + stddev * std
    lower = mid - stddev * std
    return mid, upper, lower


# ---------------------------------------------------------------------------
# True Range и ATR
# ---------------------------------------------------------------------------

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average True Range через rolling mean (legacy совместимость c grain_seed)."""
    tr = _true_range(high, low, close)
    return tr.rolling(period).mean()


def calc_atr_ewm(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """ATR через EWM (Wilder smoothing) — используется внутри ADX."""
    tr = _true_range(high, low, close)
    alpha = 1.0 / max(period, 1)
    return tr.ewm(alpha=alpha, adjust=False).mean()


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------

def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average Directional Index.

    Реализация **должна давать** результат, идентичный `_calc_adx` из
    `grain_seed.py` (alpha=1/period, EWM, защита деления на ноль).
    """
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = _true_range(high, low, close)
    alpha = 1.0 / max(period, 1)
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean().fillna(0.0)


# ---------------------------------------------------------------------------
# RSI (Wilder)
# ---------------------------------------------------------------------------

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder, EWM с alpha=1/period).

    Возвращает Series от 0 до 100. Для первых `period` точек NaN заменяется
    на нейтральное значение 50 (как в большинстве торговых платформ при
    недостаточной истории).
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    alpha = 1.0 / max(period, 1)
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


# ---------------------------------------------------------------------------
# Volume avg / breakout helpers
# ---------------------------------------------------------------------------

def rolling_mean(series: pd.Series, period: int) -> pd.Series:
    """Общая обёртка `series.rolling(period).mean()`."""
    return series.rolling(period).mean()


def previous_high(high: pd.Series, lookback: int) -> Optional[float]:
    """Максимум `high` за последние `lookback` значений, исключая последнее (для breakout)."""
    if high is None or len(high) < lookback + 1:
        return None
    window = high.iloc[-(lookback + 1):-1]
    if window.empty:
        return None
    try:
        return float(window.max())
    except (TypeError, ValueError):
        return None


__all__ = [
    "build_frame",
    "price_from_quotation",
    "calc_ma",
    "calc_bb",
    "calc_atr",
    "calc_atr_ewm",
    "calc_adx",
    "calc_rsi",
    "rolling_mean",
    "previous_high",
]
