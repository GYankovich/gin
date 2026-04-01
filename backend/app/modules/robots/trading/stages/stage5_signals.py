"""
Stage 5: Генерация сигналов на основе стратегий из модуля strategies
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

from app.modules.tinvest.facade import TInvestFacade
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.trading.costs import calculate_position_size
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage5Signals:
    """
    Генерация сигналов с использованием стратегий из модуля strategies
    """

    def __init__(self, token: str, log_func=None):
        """
        Args:
            token: Токен T-Invest API
            log_func: Функция для логирования
        """
        self.token = token
        self.log_func = log_func
        self._facade: Optional[TInvestFacade] = None
        self._cache = None

    @property
    def facade(self) -> TInvestFacade:
        """Ленивая инициализация фасада"""
        if self._facade is None:
            self._facade = TInvestFacade(self.token)
        return self._facade

    @property
    def cache(self):
        """Ленивая инициализация кэша"""
        if self._cache is None:
            try:
                from app.modules.robots.trading.cache import get_candles_cache
                self._cache = get_candles_cache()
            except ImportError:
                self._cache = SimpleCache()
        return self._cache

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

        try:
            # Получаем класс стратегии
            strategy_class = get_strategy_class(strategy_name)
            strategy = strategy_class(self.facade.instruments, {**strategy_params, "figis": figis})

            # Получаем свечи для всех FIGI
            candles_data = await self._get_candles_for_strategy(
                figis, strategy_params,
                log_api_call_func=log_api_call_func,
                token_id=token_id,
                user_id=user_id
            )

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
                        free_funds=free_funds
                    )

                    if quantity > 0:
                        signals.append({
                            "figi": figi,
                            "signal": signal,
                            "price": current_price,
                            "quantity": quantity,
                            "strategy": strategy_name,
                            "strength": 100
                        })
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

    async def _get_candles_for_strategy(
            self,
            figis: List[str],
            strategy_params: Dict,
            log_api_call_func=None,
            token_id: int = None,
            user_id: int = None
    ) -> Dict[str, List[Dict]]:
        """
        Получает свечи для всех FIGI с кэшированием

        Параметры свечей берутся ИСКЛЮЧИТЕЛЬНО из strategy_params
        """
        # Обязательные параметры — если нет, ошибка
        interval = strategy_params.get("interval")
        if not interval:
            raise ValueError("strategy_params.interval is required")

        if strategy_params.get("fast_period") is None:
            raise ValueError("strategy_params.fast_period is required")
        if strategy_params.get("slow_period") is None:
            raise ValueError("strategy_params.slow_period is required")

        days = strategy_params.get("candle_days", 60)

        self._write_log(f"   📊 Получение свечей (интервал={interval}, дней={days})")

        candles_data = {}
        from_cache = 0
        from_api = 0
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)

        for figi in figis:
            # Проверяем кэш
            cached = self.cache.get(figi, interval, days)

            if cached is not None:
                candles_data[figi] = cached
                from_cache += 1
                self._write_log(f"      {figi}: ✅ из кэша ({len(cached)} свечей)")
                continue

            # Нет в кэше - запрашиваем из API
            try:
                start_time = datetime.now(timezone.utc)

                if log_api_call_func:
                    candles = await self.facade.get_candles_with_logging(
                        figi=figi,
                        from_date=from_date,
                        to_date=to_date,
                        interval=interval,
                        log_api_call_func=log_api_call_func,
                        token_id=token_id,
                        user_id=user_id
                    )

                else:
                    candles = await self.facade.get_candles(figi, from_date, to_date, interval)

                duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

                candles_data[figi] = candles
                self.cache.set(figi, interval, days, candles)
                from_api += 1

                self._write_log(f"      {figi}: 📡 из API ({len(candles)} свечей, {duration:.0f}ms)")
            except Exception as e:
                self._write_log(f"      ❌ {figi}: ошибка - {e}")
                candles_data[figi] = []

        self._write_log(f"   📊 Кэш: из кэша={from_cache}, из API={from_api}")
        return candles_data

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


class SimpleCache:
    """
    Простой кэш для свечей (используется если модуль cache не найден)
    """

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Dict] = {}
        self._ttl = ttl_seconds

    def _make_key(self, figi: str, interval: str, days: int) -> str:
        return f"{figi}:{interval}:{days}"

    def get(self, figi: str, interval: str, days: int) -> Optional[List[Dict]]:
        key = self._make_key(figi, interval, days)
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry["expires_at"]:
                return entry["data"]
            else:
                del self._cache[key]
        return None

    def set(self, figi: str, interval: str, days: int, candles: List[Dict]):
        key = self._make_key(figi, interval, days)
        self._cache[key] = {
            "data": candles,
            "expires_at": datetime.now() + timedelta(seconds=self._ttl)
        }

    def clear(self):
        self._cache.clear()