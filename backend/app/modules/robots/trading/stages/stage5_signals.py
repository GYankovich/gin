"""
Stage 5: Генерация сигналов на основе стратегий
"""
from typing import Dict, List, Optional
import logging
import pandas as pd

from app.modules.robots.trading.costs import calculate_position_size

logger = logging.getLogger(__name__)


class Stage5Signals:
    """Генерация сигналов"""

    def __init__(self, log_func=None):
        self.log_func = log_func

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE5] {message}")
        else:
            logger.info(f"[STAGE5] {message}")

    def candles_to_dataframe(self, candles: List[Dict]):
        """Преобразует свечи в DataFrame"""
        try:
            data = []
            for c in candles:
                close = c.get("close", {})
                units = close.get("units", 0)
                nano = close.get("nano", 0)

                try:
                    units = float(units) if units else 0
                except (TypeError, ValueError):
                    units = 0
                try:
                    nano = float(nano) if nano else 0
                except (TypeError, ValueError):
                    nano = 0

                close_price = units + nano / 1e9

                data.append({
                    "time": c.get("time"),
                    "close": close_price
                })

            df = pd.DataFrame(data)
            if not df.empty:
                df = df.sort_values("time")
            return df
        except Exception as e:
            self._write_log(f"   ❌ Ошибка преобразования свечей: {e}")
            return None

    def calculate_ma_cross_signal(self, df, params: Dict) -> Optional[str]:
        """Рассчитывает сигнал MA Cross"""
        try:
            fast_period = params.get("fast_period", 10)
            slow_period = params.get("slow_period", 30)

            if len(df) < slow_period + 1:
                return None

            df['fast_ma'] = df['close'].rolling(fast_period).mean()
            df['slow_ma'] = df['close'].rolling(slow_period).mean()

            prev_fast = df['fast_ma'].iloc[-2]
            prev_slow = df['slow_ma'].iloc[-2]
            curr_fast = df['fast_ma'].iloc[-1]
            curr_slow = df['slow_ma'].iloc[-1]

            if pd.notna(prev_fast) and pd.notna(prev_slow) and pd.notna(curr_fast) and pd.notna(curr_slow):
                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    return "BUY"
                elif prev_fast >= prev_slow and curr_fast < curr_slow:
                    return "SELL"

            return None
        except Exception as e:
            self._write_log(f"   ❌ Ошибка расчета сигнала: {e}")
            return None

    async def generate_signals(
            self,
            candles: Dict[str, List[Dict]],
            prices: Dict[str, float],
            figis: List[str],
            strategy_name: str,
            strategy_params: Dict,
            risk_params: Dict,
            portfolio_value: float,
            free_funds: float,
            open_positions: List[Dict]
    ) -> List[Dict]:
        """Генерирует сигналы на основе стратегии"""
        self._write_log("🎯 Генерация сигналов")
        self._write_log(f"   Стратегия: {strategy_name}")
        self._write_log(f"   FIGIs: {figis}")
        self._write_log(f"   Открытые позиции: {len(open_positions)}")

        signals = []
        open_figis = {p["figi"] for p in open_positions if p.get("status") == "open"}

        if strategy_name == "ma_cross":
            for figi in figis:
                self._write_log(f"\n   📊 Анализ {figi}:")

                if figi in open_figis:
                    self._write_log(f"      ⏭️ Пропуск: уже есть открытая позиция")
                    continue

                current_price = prices.get(figi)
                if not current_price:
                    self._write_log(f"      ⏭️ Пропуск: нет текущей цены")
                    continue

                candle_data = candles.get(figi, [])
                slow_period = strategy_params.get("slow_period", 30)
                if len(candle_data) < slow_period + 1:
                    self._write_log(f"      ⏭️ Пропуск: недостаточно свечей ({len(candle_data)}/{slow_period+1})")
                    continue

                df = self.candles_to_dataframe(candle_data)
                if df is None:
                    continue

                signal = self.calculate_ma_cross_signal(df, strategy_params)

                if signal:
                    max_position_rub = risk_params.get("max_position_rub")
                    max_position_percent = risk_params.get("max_position_percent", 10)

                    quantity = calculate_position_size(
                        portfolio_value=portfolio_value,
                        current_price=current_price,
                        max_position_percent=max_position_percent,
                        max_position_rub=max_position_rub,
                        free_funds=free_funds
                    )

                    signals.append({
                        "figi": figi,
                        "signal": signal,
                        "price": current_price,
                        "quantity": quantity,
                        "strategy": strategy_name
                    })
                    self._write_log(f"      🎯 {signal} {quantity} лотов по {current_price:.4f} руб.")
                else:
                    self._write_log(f"      ⏭️ Сигнала нет")

        self._write_log(f"\n   Итого сигналов: {len(signals)}")
        return signals