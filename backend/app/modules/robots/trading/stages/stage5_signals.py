"""
Stage 5: Генерация сигналов на основе стратегий из модуля strategies
"""
from typing import Dict, List, Optional

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.trading.costs import calculate_position_size
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage5Signals:
    """
    Генерация сигналов с использованием стратегий из модуля strategies
    """

    def __init__(self, broker: BrokerFacade, log_func=None):
        """
        Args:
            broker: Брокерский фасад
            log_func: Функция для логирования
        """
        self.broker = broker
        self.log_func = log_func

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE5] {message}")
        else:
            logger.info(f"[STAGE5] {message}")

    async def generate_signals(
            self,
            figis: List[str],
            strategy_name: str,
            strategy_params: Dict,
            risk_params: Dict,
            portfolio_value: float,
            free_funds: float,
            open_positions: List[Dict],
            current_prices: Optional[Dict[str, float]] = None,
            log_api_call_func=None,
            token_id: int = None,
            user_id: int = None
    ) -> List[Dict]:
        """
        Генерирует сигналы на основе стратегии
        """
        self._write_log("🎯 Генерация сигналов")
        self._write_log(f"   Стратегия: {strategy_name}")
        self._write_log(f"   FIGIs: {figis}")
        self._write_log(f"   Открытые позиции: {len(open_positions)}")

        signals = []
        open_figis = {p["figi"] for p in open_positions if p.get("status") == "open"}
        remaining_funds = float(free_funds or 0.0)

        try:
            # Получаем класс стратегии
            strategy_class = get_strategy_class(strategy_name)
            strategy = strategy_class(None, {**strategy_params, "figis": figis})

            # Получаем свечи для всех FIGI
            candles_data = await self._get_candles_for_strategy(figis, strategy_params)

            # Генерируем сигналы через стратегию
            raw_signals = await strategy.generate_signals(candles_data)

            # Конвертируем сигналы в формат для Stage6
            for figi in figis:
                self._write_log(f"\n   📊 Анализ {figi}:")

                if figi in open_figis:
                    self._write_log(f"      ⏭️ Пропуск: уже есть открытая позиция")
                    continue

                # Получаем текущую цену
                current_price = current_prices.get(figi) if current_prices else None
                if not current_price:
                    candles = candles_data.get(figi, [])
                    if candles:
                        last_candle = candles[-1]
                        current_price = self._parse_candle_price(last_candle.get("close"))
                        if current_price:
                            self._write_log(f"      📊 Цена из свечи: {current_price:.4f} руб.")

                if not current_price:
                    self._write_log(f"      ⏭️ Пропуск: нет текущей цены")
                    continue

                signal = raw_signals.get(figi)

                if signal:
                    max_position_percent = risk_params.get("max_position_percent", 10)
                    max_position_rub = risk_params.get("max_position_rub")

                    quantity = calculate_position_size(
                        portfolio_value=portfolio_value,
                        current_price=current_price,
                        max_position_percent=max_position_percent,
                        max_position_rub=max_position_rub,
                        free_funds=remaining_funds
                    )

                    if quantity > 0:
                        indicators = self._calculate_indicators_for_figi(
                            strategy_name=strategy_name,
                            candles=candles_data.get(figi, []),
                            strategy_params=strategy_params,
                        )
                        target_price = self._calculate_target_price(
                            signal=signal,
                            current_price=current_price,
                            risk_params=risk_params,
                        )
                        if signal == "BUY":
                            gross_return = float(risk_params.get("take_profit_percent", 3)) / 100.0
                            broker_commission = float(risk_params.get("broker_commission", 0.0005))
                            exchange_fee = float(risk_params.get("exchange_fee", 0.0001))
                            slippage = float(risk_params.get("slippage_bps", 0.0)) / 10000.0
                            ndfl = float(risk_params.get("ndfl", 0.13))
                            net_return = gross_return - broker_commission - exchange_fee - slippage - (ndfl * max(gross_return, 0))
                            if net_return <= 0:
                                self._write_log(f"      ⏭️ Пропуск BUY: net_return={net_return:.4f} <= 0")
                                continue

                        signals.append({
                            "figi": figi,
                            "signal": signal,
                            "price": current_price,
                            "target_price": target_price,
                            "indicators": indicators,
                            "quantity": quantity,
                            "strategy": strategy_name,
                            "strength": 100
                        })
                        remaining_funds = max(0.0, remaining_funds - (quantity * current_price))
                        self._write_log(f"      🎯 {signal} {quantity} лотов по {current_price:.4f} руб.")
                    else:
                        self._write_log(f"      ⏭️ Недостаточно средств для сделки")
                else:
                    self._write_log(f"      ⏭️ Сигнала нет")

        except ValueError as e:
            self._write_log(f"   ❌ Неизвестная стратегия: {e}")
        except Exception as e:
            self._write_log(f"   ❌ Ошибка генерации сигналов: {e}")
            import traceback
            self._write_log(traceback.format_exc())

        self._write_log(f"\n   Итого сигналов: {len(signals)}")
        return signals

    def _extract_closes(self, candles: List[Dict]) -> List[float]:
        closes: List[float] = []
        for c in candles:
            close = c.get("close")
            if not close:
                continue
            units = int(close.get("units", 0) or 0)
            nano = int(close.get("nano", 0) or 0)
            closes.append(units + nano / 1e9)
        return closes

    def _calculate_indicators_for_figi(self, strategy_name: str, candles: List[Dict], strategy_params: Dict) -> Dict[str, float]:
        # Для grain_seed детальные индикаторы рассчитываются внутри стратегии.
        closes = self._extract_closes(candles)
        if len(closes) < 3:
            return {}
        return {
            "last_close": round(closes[-1], 6),
            "prev_close": round(closes[-2], 6),
        }

    def _calculate_target_price(self, signal: str, current_price: float, risk_params: Dict) -> float:
        take_profit_pct = float(risk_params.get("take_profit_percent", 3.0))
        if signal == "BUY":
            return round(current_price * (1 + take_profit_pct / 100.0), 6)
        if signal == "SELL":
            return round(current_price * (1 - take_profit_pct / 100.0), 6)
        return round(current_price, 6)

    async def _get_candles_for_strategy(
            self,
            figis: List[str],
            strategy_params: Dict,
    ) -> Dict[str, List[Dict]]:
        """
        Получает свечи для всех FIGI с кэшированием

        Параметры свечей берутся ИСКЛЮЧИТЕЛЬНО из strategy_params
        """
        # Обязательные параметры — если нет, ошибка
        interval = strategy_params.get("interval")
        if not interval:
            raise ValueError("strategy_params.interval is required")

        days = strategy_params.get("candle_days", 60)

        self._write_log(f"   📊 Получение индикаторных данных из кэша (интервал={interval}, дней={days})")
        return await indicator_service.get_candles_batch(self.broker, figis, strategy_params)

    def _parse_candle_price(self, price_data: dict) -> Optional[float]:
        """Парсит цену из свечи"""
        if not price_data:
            return None

        units = price_data.get("units", 0)
        nano = price_data.get("nano", 0)

        try:
            units = int(units) if units else 0
            nano = int(nano) if nano else 0
        except (TypeError, ValueError):
            return None

        return units + nano / 1e9

