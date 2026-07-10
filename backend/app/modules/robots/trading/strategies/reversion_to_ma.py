"""
Стратегия REVERSION_TO_MA — отскок от MA при перекупленности/перепроданности.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §6.3.

BUY: close < MA * (1 - deviation_pct/100) AND RSI < rsi_oversold.
SELL: close >= MA OR RSI > rsi_overbought OR прошло max_hold_candles
  (последнее условие применяется уровнем выше — RiskManager / engine, чтобы
  стратегия не дублировала состояние позиции).

В первой версии — только LONG. SHORT — backlog (см. BRD-ARCH-03 §14).
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStrategiesReversionToMa [1]
#/// Исходный модуль `backend/app/modules/robots/trading/strategies/reversion_to_ma.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.logging_config import get_logger
from .base import BaseStrategy
from app.modules.robots.trading.indicators.library import (
    build_frame,
    calc_ma,
    calc_rsi,
    rolling_mean,
)

logger = get_logger(__name__)


class ReversionToMaStrategy(BaseStrategy):
    """Mean-reversion: BUY на перепроданности, SELL на возврате к MA."""

    async def get_required_candles_count(self) -> int:
        ma_period = int(self.params.get("ma_period", 20))
        rsi_period = int(self.params.get("rsi_period", 14))
        return max(ma_period, rsi_period) + 20

    async def generate_signals(
        self,
        candles_data: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Optional[str]]:
        ma_period = int(self.params.get("ma_period", 20))
        deviation_pct = float(self.params.get("deviation_pct", 2.0))
        rsi_period = int(self.params.get("rsi_period", 14))
        rsi_overbought = float(self.params.get("rsi_overbought", 80))
        rsi_oversold = float(self.params.get("rsi_oversold", 20))
        use_volume = bool(self.params.get("use_volume_filter", True))

        signals: Dict[str, Optional[str]] = {}
        self.skip_reasons = {}
        min_candles = max(ma_period, rsi_period) + 2

        for figi in self.figis:
            candles = candles_data.get(figi) or []
            if len(candles) < min_candles:
                reason = f"NOT_ENOUGH_CANDLES count={len(candles)} need>={min_candles}"
                self._record_skip_reason(figi, reason)
                logger.info("[REVERSION_TO_MA] %s raw_signal=NONE reason=%s", figi, reason)
                signals[figi] = None
                continue

            df = build_frame(candles)
            if df.empty or (df["close"] <= 0).any():
                reason = "EMPTY_OR_INVALID_FRAME"
                self._record_skip_reason(figi, reason)
                logger.info("[REVERSION_TO_MA] %s raw_signal=NONE reason=%s", figi, reason)
                signals[figi] = None
                continue

            ma = calc_ma(df["close"], ma_period)
            rsi = calc_rsi(df["close"], rsi_period)

            ma_last = float(ma.iloc[-1]) if pd.notna(ma.iloc[-1]) else 0.0
            rsi_last = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0
            close_last = float(df["close"].iloc[-1])

            if ma_last <= 0 or close_last <= 0:
                reason = "INVALID_MA_OR_PRICE"
                self._record_skip_reason(figi, reason)
                logger.info("[REVERSION_TO_MA] %s raw_signal=NONE reason=%s", figi, reason)
                signals[figi] = None
                continue

            deviation = (close_last - ma_last) / ma_last * 100.0

            if use_volume:
                vol_avg = float(rolling_mean(df["volume"], ma_period).iloc[-1] or 0.0)
                vol_last = float(df["volume"].iloc[-1] or 0.0)
                if vol_avg > 0 and vol_last < vol_avg * 0.5:
                    reason = (
                        f"VOLUME_FILTER last_vol={vol_last:.2f} "
                        f"avg_vol={vol_avg:.2f} threshold={vol_avg * 0.5:.2f}"
                    )
                    self._record_skip_reason(figi, reason)
                    logger.info("[REVERSION_TO_MA] %s raw_signal=NONE reason=%s", figi, reason)
                    signals[figi] = None
                    continue

            if close_last >= ma_last or rsi_last > rsi_overbought:
                sell_parts: List[str] = []
                if close_last >= ma_last:
                    sell_parts.append(f"close={close_last:.6f}>=ma={ma_last:.6f}")
                if rsi_last > rsi_overbought:
                    sell_parts.append(f"rsi={rsi_last:.1f}>{rsi_overbought:.1f}")
                sell_reason = " OR ".join(sell_parts) or "EXIT_CONDITION"
                logger.info(
                    "[REVERSION_TO_MA] %s raw_signal=SELL reason=%s deviation=%.2f%% rsi=%.1f",
                    figi,
                    sell_reason,
                    deviation,
                    rsi_last,
                )
                signals[figi] = "SELL"
                continue

            if deviation <= -deviation_pct and rsi_last < rsi_oversold:
                logger.info(
                    "[REVERSION_TO_MA] %s raw_signal=BUY reason=OVERSOLD "
                    "deviation=%.2f%% rsi=%.1f close=%.6f ma=%.6f",
                    figi,
                    deviation,
                    rsi_last,
                    close_last,
                    ma_last,
                )
                signals[figi] = "BUY"
                continue

            reason = (
                f"NO_ENTRY_CONDITION deviation={deviation:.2f}% "
                f"(need<=-{deviation_pct:.2f}%) rsi={rsi_last:.1f} "
                f"(need<{rsi_oversold:.1f}) close={close_last:.6f} ma={ma_last:.6f}"
            )
            self._record_skip_reason(figi, reason)
            logger.info("[REVERSION_TO_MA] %s raw_signal=NONE reason=%s", figi, reason)
            signals[figi] = None

        return signals


__all__ = ["ReversionToMaStrategy"]
