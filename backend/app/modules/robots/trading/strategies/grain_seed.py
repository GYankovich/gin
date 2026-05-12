from typing import Dict, Optional, List, Any

import numpy as np
import pandas as pd

from .base import BaseStrategy


def _price(q: Optional[Dict[str, Any]]) -> float:
    if not q:
        return 0.0
    if isinstance(q, (int, float)):
        return float(q)
    if isinstance(q, str):
        try:
            return float(q)
        except Exception:
            return 0.0
    units = int(q.get("units", 0) or 0)
    nano = int(q.get("nano", 0) or 0)
    return float(units + nano / 1e9)


#///EPIC Backtesting.ITEM StrategySignals.TOPIC Candle Normalization And ADX [1]
#/// Стратегия приводится к устойчивой numeric-модели: свечи нормализуются в float,
#/// inf/NaN чистятся перед индикаторами, ADX считается через EWM с защитой деления на 0.
#/// Это устраняет падения pandas на object/NAType в rolling/ewm во время history-backtest.
def _build_frame(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for c in candles:
        rows.append(
            {
                "open": _price(c.get("open")),
                "high": _price(c.get("high")),
                "low": _price(c.get("low")),
                "close": _price(c.get("close")),
                "volume": float(c.get("volume", 0) or 0),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan)
    return df.fillna(0.0)


def _calc_adx(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / max(period, 1)
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean().fillna(0.0)


class GrainSeedStrategy(BaseStrategy):
    """
    "По зёрнышку, по семечке" — осторожная intraday-логика сигналов.

    В рамках текущего движка стратегии доступны только свечи.
    Поэтому здесь реализованы фильтры/режимы на candle-данных:
    - gap filter
    - ATR filter
    - режим trend/flat через ADX
    - trigger через MA crossover (trend) или Bollinger touch (flat)
    - базовая проверка на покрытие комиссий
    """

    async def get_required_candles_count(self) -> int:
        atr_period = int(self.params.get("atr_period", 14))
        adx_period = int(self.params.get("adx_period", 14))
        ma_slow = int(self.params.get("ma_slow_period", 20))
        bb_period = int(self.params.get("bb_period", 20))
        return max(atr_period, adx_period, ma_slow, bb_period) + 30

    #///EPIC Backtesting.ITEM StrategySignals.TOPIC Grain Seed Decision Pipeline [2]
    #/// Последовательность сигналов: gap -> spread proxy -> ATR -> ADX regime,
    #/// далее trigger (MA crossover для trend, Bollinger touch для flat) и отсев
    #/// по минимальной цели прибыли с учетом round-trip комиссии.
    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        gap_filter_pct = float(self.params.get("gap_filter_pct", 2.5))
        spread_limit_pct = float(self.params.get("spread_limit_pct", 0.15))
        spread_proxy_multiplier = float(self.params.get("spread_proxy_multiplier", 8.0))
        atr_period = int(self.params.get("atr_period", 14))
        atr_min_pct = float(self.params.get("atr_min_pct", 1.5))
        adx_period = int(self.params.get("adx_period", 14))
        adx_threshold = float(self.params.get("adx_threshold", 22.0))
        ma_fast = int(self.params.get("ma_fast_period", 5))
        ma_slow = int(self.params.get("ma_slow_period", 20))
        bb_period = int(self.params.get("bb_period", 20))
        bb_stddev = float(self.params.get("bb_stddev", 2.0))
        min_profit_target_pct = float(self.params.get("min_profit_target_pct", 0.35))
        commission_pct = float(self.params.get("commission_pct", 0.05))

        if ma_fast >= ma_slow:
            raise ValueError("strategy_params.ma_fast_period must be less than strategy_params.ma_slow_period")

        min_count = max(atr_period, adx_period, ma_slow, bb_period) + 3
        signals: Dict[str, Optional[str]] = {}

        round_trip_commission_pct = commission_pct * 2.0
        if min_profit_target_pct <= round_trip_commission_pct:
            # Глобально бессмысленно входить, если цель не перекрывает комиссии.
            return {figi: None for figi in self.figis}

        for figi in self.figis:
            candles = candles_data.get(figi, [])
            if len(candles) < min_count:
                signals[figi] = None
                continue

            df = _build_frame(candles)
            if df.empty or (df["close"] <= 0).any():
                signals[figi] = None
                continue

            # 1) Gap filter: open(now) vs close(prev)
            prev_close = float(df["close"].iloc[-2])
            open_now = float(df["open"].iloc[-1])
            if prev_close <= 0:
                signals[figi] = None
                continue
            gap_pct = abs((open_now - prev_close) / prev_close) * 100.0
            if gap_pct > gap_filter_pct:
                signals[figi] = None
                continue

            # 2) Spread proxy через внутрисвечный диапазон.
            #    В движке нет orderbook, поэтому используем консервативную аппроксимацию.
            hl_spread_pct = ((df["high"] - df["low"]) / df["close"]).tail(3).mean() * 100.0
            if float(hl_spread_pct or 0.0) > (spread_limit_pct * spread_proxy_multiplier):
                signals[figi] = None
                continue

            # 3) ATR filter
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["close"].shift(1)).abs()
            tr3 = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(atr_period).mean()
            curr_close = float(df["close"].iloc[-1])
            curr_atr = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0
            atr_pct = (curr_atr / curr_close) * 100.0 if curr_close > 0 else 0.0
            if atr_pct < atr_min_pct:
                signals[figi] = None
                continue

            # Проверка "пространства" для покрытия комиссий.
            if atr_pct < round_trip_commission_pct * 10.0:
                signals[figi] = None
                continue

            # 4) Market regime через ADX
            adx = _calc_adx(df, adx_period)
            adx_curr = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0.0
            trend_mode = adx_curr > adx_threshold

            # 5) Trigger
            if trend_mode:
                fast_ma = df["close"].rolling(ma_fast).mean()
                slow_ma = df["close"].rolling(ma_slow).mean()

                prev_fast = fast_ma.iloc[-2]
                prev_slow = slow_ma.iloc[-2]
                curr_fast = fast_ma.iloc[-1]
                curr_slow = slow_ma.iloc[-1]

                if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
                    signals[figi] = None
                    continue

                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    signals[figi] = "BUY"
                elif prev_fast >= prev_slow and curr_fast < curr_slow:
                    signals[figi] = "SELL"
                else:
                    signals[figi] = None
            else:
                mid = df["close"].rolling(bb_period).mean()
                std = df["close"].rolling(bb_period).std()
                upper = mid + bb_stddev * std
                lower = mid - bb_stddev * std

                up = upper.iloc[-1]
                lo = lower.iloc[-1]
                px = df["close"].iloc[-1]
                if pd.isna(up) or pd.isna(lo):
                    signals[figi] = None
                    continue
                if px <= lo:
                    signals[figi] = "BUY"
                elif px >= up:
                    signals[figi] = "SELL"
                else:
                    signals[figi] = None

        return signals
