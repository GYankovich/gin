from typing import Dict, Optional, List, Any

import numpy as np
import pandas as pd

from .base import BaseStrategy
from app.modules.robots.trading.indicators.library import (
    build_frame as _lib_build_frame,
    calc_adx as _lib_calc_adx,
    price_from_quotation,
)


def _price(q: Optional[Dict[str, Any]]) -> float:
    """Обратно совместимый алиас на `indicators.library.price_from_quotation`."""
    return price_from_quotation(q)


#///EPIC Backtesting.ITEM StrategySignals.TOPIC Candle Normalization And ADX [1]
#/// Стратегия приводится к устойчивой numeric-модели: свечи нормализуются в float,
#/// inf/NaN чистятся перед индикаторами, ADX считается через EWM с защитой деления на 0.
#/// Это устраняет падения pandas на object/NAType в rolling/ewm во время history-backtest.
def _build_frame(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """Делегат в `indicators.library.build_frame` (без смены поведения)."""
    return _lib_build_frame(candles)


def _calc_adx(df: pd.DataFrame, period: int) -> pd.Series:
    """Делегат в `indicators.library.calc_adx` (без смены поведения)."""
    return _lib_calc_adx(df["high"], df["low"], df["close"], period)


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
        profile = str(self.params.get("signal_profile", "legacy")).strip().lower()
        if profile in ("tz_signals_v1", "tz_doc_v1", "backtest_review"):
            adx_period = int(self.params.get("adx_period", 14))
            ma_slow = int(self.params.get("ma_slow_period", 20))
            bb_period = int(self.params.get("bb_period", 20))
            return max(adx_period, ma_slow, bb_period) + 35
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
        self.skip_reasons = {}
        profile = str(self.params.get("signal_profile", "legacy")).strip().lower()
        if profile in ("tz_signals_v1", "tz_doc_v1", "backtest_review"):
            return await self._signals_tz_review_v1(candles_data)

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
            reason = (
                f"TARGET_BELOW_COMMISSION min_profit={min_profit_target_pct:.4f} "
                f"round_trip={round_trip_commission_pct:.4f}"
            )
            for figi in self.figis:
                self._record_skip_reason(figi, reason)
                signals[figi] = None
            return signals

        for figi in self.figis:
            candles = candles_data.get(figi, [])
            if len(candles) < min_count:
                self._record_skip_reason(
                    figi, f"INSUFFICIENT_CANDLES have={len(candles)} need>={min_count}"
                )
                signals[figi] = None
                continue

            df = _build_frame(candles)
            if df.empty or (df["close"] <= 0).any():
                self._record_skip_reason(figi, "INVALID_CANDLE_FRAME")
                signals[figi] = None
                continue

            # 1) Gap filter: open(now) vs close(prev)
            prev_close = float(df["close"].iloc[-2])
            open_now = float(df["open"].iloc[-1])
            if prev_close <= 0:
                self._record_skip_reason(figi, "PREV_CLOSE_INVALID")
                signals[figi] = None
                continue
            gap_pct = abs((open_now - prev_close) / prev_close) * 100.0
            if gap_pct > gap_filter_pct:
                self._record_skip_reason(
                    figi, f"GAP_FILTER gap_pct={gap_pct:.3f}>{gap_filter_pct:.3f}"
                )
                signals[figi] = None
                continue

            # 2) Spread proxy через внутрисвечный диапазон.
            hl_spread_pct = ((df["high"] - df["low"]) / df["close"]).tail(3).mean() * 100.0
            spread_cap = spread_limit_pct * spread_proxy_multiplier
            if float(hl_spread_pct or 0.0) > spread_cap:
                self._record_skip_reason(
                    figi, f"SPREAD_PROXY hl={float(hl_spread_pct):.3f}>{spread_cap:.3f}"
                )
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
                self._record_skip_reason(
                    figi, f"ATR_TOO_LOW atr_pct={atr_pct:.3f}<{atr_min_pct:.3f}"
                )
                signals[figi] = None
                continue

            # Проверка "пространства" для покрытия комиссий.
            commission_space = round_trip_commission_pct * 10.0
            if atr_pct < commission_space:
                self._record_skip_reason(
                    figi, f"ATR_BELOW_COMMISSION_SPACE atr_pct={atr_pct:.3f}<{commission_space:.3f}"
                )
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
                    self._record_skip_reason(figi, f"MA_NAN adx={adx_curr:.2f} trend")
                    signals[figi] = None
                    continue

                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    signals[figi] = "BUY"
                    self._record_skip_reason(
                        figi, f"BUY_MA_CROSSOVER adx={adx_curr:.2f} atr_pct={atr_pct:.3f}"
                    )
                elif prev_fast >= prev_slow and curr_fast < curr_slow:
                    signals[figi] = "SELL"
                    self._record_skip_reason(
                        figi, f"SELL_MA_CROSSOVER adx={adx_curr:.2f} atr_pct={atr_pct:.3f}"
                    )
                else:
                    self._record_skip_reason(
                        figi,
                        f"NO_MA_CROSS adx={adx_curr:.2f} fast={float(curr_fast):.6f} "
                        f"slow={float(curr_slow):.6f}",
                    )
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
                    self._record_skip_reason(figi, f"BB_NAN adx={adx_curr:.2f} flat")
                    signals[figi] = None
                    continue
                if px <= lo:
                    signals[figi] = "BUY"
                    self._record_skip_reason(
                        figi, f"BUY_BB_LOWER adx={adx_curr:.2f} px={float(px):.6f} lo={float(lo):.6f}"
                    )
                elif px >= up:
                    signals[figi] = "SELL"
                    self._record_skip_reason(
                        figi, f"SELL_BB_UPPER adx={adx_curr:.2f} px={float(px):.6f} up={float(up):.6f}"
                    )
                else:
                    self._record_skip_reason(
                        figi,
                        f"NO_BB_TOUCH adx={adx_curr:.2f} px={float(px):.6f} "
                        f"lo={float(lo):.6f} up={float(up):.6f}",
                    )
                    signals[figi] = None

        return signals

    async def _signals_tz_review_v1(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        """Вход по docs/backtest_review §6.5: (пробой BB вверх ИЛИ golden cross MA) И ADX>порог И объём выше среднего за 5 баров."""
        adx_period = int(self.params.get("adx_period", 14))
        adx_threshold = float(self.params.get("adx_threshold", 22.0))
        ma_fast = int(self.params.get("ma_fast_period", 5))
        ma_slow = int(self.params.get("ma_slow_period", 20))
        bb_period = int(self.params.get("bb_period", 20))
        bb_stddev = float(self.params.get("bb_stddev", 2.0))
        min_count = max(adx_period, ma_slow, bb_period) + 6
        out: Dict[str, Optional[str]] = {}
        for figi in self.figis:
            candles = candles_data.get(figi, [])
            if len(candles) < min_count:
                self._record_skip_reason(
                    figi, f"INSUFFICIENT_CANDLES have={len(candles)} need>={min_count}"
                )
                out[figi] = None
                continue
            df = _build_frame(candles)
            if df.empty:
                self._record_skip_reason(figi, "INVALID_CANDLE_FRAME")
                out[figi] = None
                continue
            adx = _calc_adx(df, adx_period)
            adx_curr = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0.0
            if adx_curr <= adx_threshold:
                self._record_skip_reason(
                    figi, f"ADX_TOO_LOW adx={adx_curr:.2f}<={adx_threshold:.2f}"
                )
                out[figi] = None
                continue
            vol_tail = df["volume"].iloc[-6:-1]
            if len(vol_tail) < 5 or float(vol_tail.mean()) <= 0:
                self._record_skip_reason(figi, "VOLUME_AVG_INVALID")
                out[figi] = None
                continue
            if float(df["volume"].iloc[-1]) <= float(vol_tail.mean()):
                self._record_skip_reason(
                    figi,
                    f"VOLUME_BELOW_AVG last={float(df['volume'].iloc[-1]):.2f} "
                    f"avg5={float(vol_tail.mean()):.2f}",
                )
                out[figi] = None
                continue
            mid = df["close"].rolling(bb_period).mean()
            std = df["close"].rolling(bb_period).std()
            upper = (mid + bb_stddev * std).iloc[-1]
            px = float(df["close"].iloc[-1])
            bb_breakout = bool(pd.notna(upper) and px > float(upper))
            fast_ma = df["close"].rolling(ma_fast).mean()
            slow_ma = df["close"].rolling(ma_slow).mean()
            prev_fast = fast_ma.iloc[-2]
            prev_slow = slow_ma.iloc[-2]
            curr_fast = fast_ma.iloc[-1]
            curr_slow = slow_ma.iloc[-1]
            if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
                self._record_skip_reason(figi, "MA_NAN")
                out[figi] = None
                continue
            golden = bool(prev_fast <= prev_slow and curr_fast > curr_slow)
            if not (bb_breakout or golden):
                self._record_skip_reason(
                    figi,
                    f"NO_BB_OR_GOLDEN adx={adx_curr:.2f} bb_breakout={bb_breakout} golden={golden}",
                )
                out[figi] = None
                continue
            out[figi] = "BUY"
            why = "BUY_BB_BREAKOUT" if bb_breakout else "BUY_GOLDEN_CROSS"
            self._record_skip_reason(figi, f"{why} adx={adx_curr:.2f}")
        return out
