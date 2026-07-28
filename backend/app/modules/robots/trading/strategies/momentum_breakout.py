"""
Стратегия MOMENTUM_BREAKOUT — пробой максимума последних N дней в первые M минут.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §6.2.

Контракт совместим с базовым `BaseStrategy.generate_signals(candles_data)`,
который возвращает `Dict[figi, "BUY"/"SELL"/None]`. Свечи в `candles_data`
ожидаются в T-Invest формате (`open/high/low/close` как `{units, nano}` или
числа, `time` — ISO-строка). Для определения «утра дня» используется первая
свеча в серии.

В отличие от GRAIN_SEED, эта стратегия требует **двух** входных потоков:
- интрадей-свечи дня D (тот же `candles_data`, что и для grain_seed);
- предыдущие дневные high — передаются через `self.params["daily_highs"]` либо
  через `self.params["lookback_days"]` + сам ряд (если интрадей-серия покрывает
  больше одного дня, мы рассчитываем previous_highs автоматически).
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStrategiesMomentumBreakout [1]
#/// Исходный модуль `backend/app/modules/robots/trading/strategies/momentum_breakout.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from app.core.logging_config import get_logger

from .base import BaseStrategy
from app.modules.robots.trading.indicators.library import build_frame

logger = get_logger(__name__)


class MomentumBreakoutStrategy(BaseStrategy):
    """Пробой максимума за `lookback_days` в первые `entry_minutes_from_open` минут."""

    async def get_required_candles_count(self) -> int:
        # Берём с запасом: нужно покрыть lookback_days + сегодняшнее утро.
        # При интервале M10 это ~ 39 баров в день. Для 5 дней + сегодня:
        lookback = int(self.params.get("lookback_days", 5))
        entry_min = int(self.params.get("entry_minutes_from_open", 30))
        per_day = max(1, 360 // 10)  # 6h сессии / 10 минут
        return per_day * (lookback + 1) + max(3, entry_min // 10)

    async def generate_signals(
        self,
        candles_data: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Optional[str]]:
        lookback_days = int(self.params.get("lookback_days", 5))
        entry_minutes = int(self.params.get("entry_minutes_from_open", 30))
        hold_candles = int(self.params.get("hold_candles", 4))  # не используется в самом сигнале (выход — у RiskManager / engine)
        allow_entry_all_day = bool(self.params.get("allow_entry_all_day", False))
        require_vol = bool(self.params.get("volume_confirmation", True))
        vol_mult = float(self.params.get("volume_multiplier", 1.5))
        exit_on_reverse = bool(self.params.get("exit_on_reverse", True))

        signals: Dict[str, Optional[str]] = {}

        for figi in self.figis:
            candles = candles_data.get(figi) or []
            if len(candles) < lookback_days + 1:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=NOT_ENOUGH_CANDLES count=%s need>%s",
                    figi, len(candles), lookback_days + 1
                )
                signals[figi] = None
                continue

            # группируем по дню (первые 10 символов time)
            df = _to_frame_with_day(candles)
            if df.empty:
                logger.info("[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=EMPTY_FRAME", figi)
                signals[figi] = None
                continue

            days = sorted(df["day"].unique())
            if len(days) < 2:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=NOT_ENOUGH_DAYS days=%s",
                    figi, len(days)
                )
                signals[figi] = None
                continue
            current_day = days[-1]
            previous_days = days[-(lookback_days + 1):-1]
            if not previous_days:
                logger.info("[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=NO_PREVIOUS_DAYS", figi)
                signals[figi] = None
                continue

            # уровень пробоя — максимум high за предыдущие lookback_days дней
            prev_mask = df["day"].isin(previous_days)
            try:
                breakout_level = float(df.loc[prev_mask, "high"].max())
            except (TypeError, ValueError):
                logger.info("[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=BAD_BREAKOUT_LEVEL", figi)
                signals[figi] = None
                continue
            if breakout_level <= 0:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=NON_POSITIVE_BREAKOUT level=%.6f",
                    figi, breakout_level
                )
                signals[figi] = None
                continue

            today = df[df["day"] == current_day].copy()
            if today.empty:
                logger.info("[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=EMPTY_TODAY_SERIES", figi)
                signals[figi] = None
                continue

            # лимит «в первые N минут от открытия»: берём первые N // 10 баров
            n_bars = max(1, entry_minutes // 10)
            today_window = today.head(n_bars)

            close = float(today.iloc[-1]["close"])
            logger.info(
                "[MOMENTUM_BREAKOUT] %s diagnostics close=%.6f breakout=%.6f today_bars=%s window_bars=%s",
                figi, close, breakout_level, len(today), n_bars
            )

            # выход при обратном пробое — приоритет, если позиция есть
            if exit_on_reverse and close < breakout_level:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=SELL reason=EXIT_ON_REVERSE close=%.6f breakout=%.6f",
                    figi, close, breakout_level
                )
                signals[figi] = "SELL"
                continue

            # вход — только в окне первых N минут
            in_window = allow_entry_all_day or (len(today) <= n_bars)
            if not in_window:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=OUTSIDE_ENTRY_WINDOW today_bars=%s window_bars=%s",
                    figi, len(today), n_bars
                )
                signals[figi] = None
                continue

            if close <= breakout_level:
                logger.info(
                    "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=NO_BREAKOUT close=%.6f breakout=%.6f",
                    figi, close, breakout_level
                )
                signals[figi] = None
                continue

            if require_vol:
                # средний объём в окне vs последний бар
                last_vol = float(today_window.iloc[-1]["volume"])
                avg_vol = float(today_window["volume"].mean() or 0.0)
                if avg_vol <= 0 or last_vol < vol_mult * avg_vol:
                    logger.info(
                        "[MOMENTUM_BREAKOUT] %s raw_signal=NONE reason=VOLUME_FILTER last_vol=%.2f avg_vol=%.2f vol_mult=%.2f",
                        figi, last_vol, avg_vol, vol_mult
                    )
                    signals[figi] = None
                    continue

            logger.info(
                "[MOMENTUM_BREAKOUT] %s raw_signal=BUY reason=BREAKOUT_CONFIRMED close=%.6f breakout=%.6f",
                figi, close, breakout_level
            )
            signals[figi] = "BUY"

        return signals


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _to_frame_with_day(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    df = build_frame(candles)
    if df.empty:
        return df
    days: List[str] = []
    for c in candles:
        t = c.get("time")
        if isinstance(t, str) and len(t) >= 10:
            days.append(t[:10])
        elif isinstance(t, dict):
            sec = int(t.get("seconds", 0) or 0)
            import datetime as _dt
            days.append(_dt.datetime.fromtimestamp(sec, tz=_dt.timezone.utc).date().isoformat())
        else:
            days.append("")
    # выровнять длину, отрезать пустые
    df = df.iloc[: len(days)].copy()
    df["day"] = days
    return df[df["day"] != ""]


__all__ = ["MomentumBreakoutStrategy"]
