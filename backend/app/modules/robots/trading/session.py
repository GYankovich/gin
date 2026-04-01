"""
Торговая сессия для одного робота
WebSocket и торговля в независимых потоках через очередь
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.logging_config import get_logger, register_trading_session_logger
from app.core.robot_logging import APILogger
from app.modules.robots.common.mixins import TradePersistenceMixin, PriceParsingMixin
from app.modules.robots.trading.stages.stage2_websocket import Stage2WebSocket
from app.modules.robots.trading.stages.stage3_portfolio import Stage3Portfolio
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage5_signals import Stage5Signals
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders
from app.modules.robots.trading import queries as trading_queries
from app.modules.tinvest.facade import TInvestFacade

# Получаем системный логгер
system_log = get_logger("robots.trading.session")


class TradingSession(TradePersistenceMixin, PriceParsingMixin):
    """
    Торговая сессия для одного робота
    WebSocket и торговля в независимых потоках через очередь
    """

    def __init__(
            self,
            db,
            schema: str,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            config: Dict,
            log_func=None
    ):
        self.db = db
        self.schema = schema
        self.robot_id = robot_id
        self.user_id = user_id
        self.token_id = token_id
        self.token = token
        self._log_func = log_func
        self._session_logger = register_trading_session_logger(robot_id)

        # Создаем свою сессию БД если не передана
        self._own_db = db is None
        if self._own_db:
            self.db = SessionLocal()

        # ID выполнения (для БД логов)
        self._execution_log_id: Optional[int] = None
        self._api_logger: Optional[APILogger] = None

        # Компоненты
        self.websocket = None
        self.portfolio = None
        self.positions = None
        self._facade: Optional[TInvestFacade] = None

        # Очереди для потоков
        self.price_queue = asyncio.Queue(maxsize=1000)
        self.order_queue = asyncio.Queue(maxsize=100)
        self.signal_queue = asyncio.Queue(maxsize=100)

        # Флаги состояния
        self.websocket_connected = False
        self.running = True

        # Кэши
        self.cached_prices: Dict[str, float] = {}
        self.cached_positions: List[Dict] = []

        # Статистика
        self.stats = {
            "prices_received": 0,
            "signals_generated": 0,
            "orders_placed": 0,
            "errors": 0
        }

        # Параметры
        self.config = None
        self.account_id = None
        self.allowed_figis = []
        self.strategy_name = "ma_cross"
        self.strategy_params = {}
        self.risk_params = {}
        self.update_interval = 10

        # Обновляем конфиг
        self._update_config(config)

    @property
    def facade(self) -> TInvestFacade:
        """Ленивая инициализация фасада"""
        if self._facade is None:
            self._facade = TInvestFacade(self.token)
        return self._facade

    def _write_log(self, message: str):
        """Запись в лог (и в файл, и в system_log)"""
        self._session_logger.info(message)
        if self._log_func:
            try:
                self._log_func(f"[SESSION {self.robot_id}] {message}")
            except Exception:
                pass
        else:
            system_log.debug(f"[ROBOT_{self.robot_id}] {message}")

    async def _create_execution_log(self) -> Optional[int]:
        """Создает запись о запуске сессии в БД"""
        if not self.db:
            return None

        try:
            query = trading_queries.build_create_execution_log_query().format(schema=self.schema)
            result = self.db.execute(
                text(query),
                {
                    "robot_id": self.robot_id,
                    "action_type": 1,
                    "status": 0,
                    "now": datetime.now(timezone.utc)
                }
            ).first()
            self.db.commit()
            if result:
                self._execution_log_id = result[0]
                self._api_logger = APILogger(
                    db=self.db,
                    schema=self.schema,
                    robot_type="trading",
                    robot_name=f"robot_{self.robot_id}",
                    robot_version="1.0.0",
                    execution_log_id=self._execution_log_id
                )
                self._write_log(f"Execution log ID: {self._execution_log_id}")
            return self._execution_log_id
        except Exception as e:
            self._write_log(f"❌ Failed to create execution log: {e}")
            return None

    async def _complete_execution_log(self, status: int, message: str = None, execution_time_ms: int = None):
        """Завершает запись выполнения в БД"""
        if not self.db or not self._execution_log_id:
            return

        try:
            query = trading_queries.build_update_execution_log_query().format(schema=self.schema)
            self.db.execute(
                text(query),
                {
                    "log_id": self._execution_log_id,
                    "status": status,
                    "message": message[:500] if message else None,
                    "execution_time_ms": execution_time_ms,
                    "error_stack": None
                }
            )
            self.db.commit()
        except Exception as e:
            self._write_log(f"❌ Failed to complete execution log: {e}")

    async def _log_api_call(
            self,
            endpoint: str,
            request_data: Optional[Dict] = None,
            response_data: Optional[Dict] = None,
            response_status: Optional[int] = None,
            error_message: Optional[str] = None,
            token_id: Optional[int] = None,
            user_id: Optional[int] = None,
            started_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Логирует API вызов в БД и файл
        """
        if not self._api_logger:
            # Только файловое логирование
            self._write_log(f"📡 API: {endpoint}")
            return None

        return await self._api_logger.log(
            endpoint=endpoint,
            request_data=request_data,
            response_data=response_data,
            response_status=response_status,
            error_message=error_message,
            token_id=token_id or self.token_id,
            user_id=user_id or self.user_id,
            started_at=started_at
        )

    def _update_config(self, config: Dict):
        """Обновляет параметры из конфига"""
        self.config = config or {}
        self.account_id = self.config.get("account_id")
        self.allowed_figis = self.config.get("allowed_figis", [])
        self.strategy_name = self.config.get("strategy", "ma_cross")
        self.strategy_params = self.config.get("strategy_params", {})
        self.risk_params = self.config.get("risk", {})
        self.update_interval = self.config.get("update_interval_seconds", 10)

        self._write_log(f"📋 Конфигурация обновлена:")
        self._write_log(f"   Account ID: {self.account_id}")
        self._write_log(f"   FIGIs: {self.allowed_figis}")
        self._write_log(f"   Strategy: {self.strategy_name}")
        self._write_log(f"   Update interval: {self.update_interval} сек")

    async def refresh_config(self):
        """Обновляет конфигурацию из БД (для live-обновлений)"""
        if not self.db:
            return

        self._write_log("🔄 Обновление конфигурации из БД...")

        try:
            query = trading_queries.build_get_robot_config_query().format(schema=self.schema)
            result = self.db.execute(text(query), {"robot_id": self.robot_id}).first()
            if result and result[0]:
                new_config = result[0]
                old_figis = set(self.allowed_figis)
                new_figis = set(new_config.get("allowed_figis", []))

                self._update_config(new_config)

                if old_figis != new_figis and self.websocket:
                    self._write_log(f"   FIGI изменились: {old_figis} -> {new_figis}")
                    asyncio.create_task(self.websocket.subscribe(list(new_figis)))

            self.db.commit()

        except Exception as e:
            self._write_log(f"   ❌ Ошибка обновления конфига: {e}")
            if self.db:
                self.db.rollback()

    # ============================================================
    # WebSocket поток
    # ============================================================

    async def _websocket_worker(self):
        """WebSocket поток: получает цены и кладёт в очередь"""
        self._write_log("🔌 [WS] Запуск WebSocket потока")

        while self.running:
            try:
                self.websocket = Stage2WebSocket(self.token, self.robot_id, self._write_log)

                self._write_log("🔌 [WS] Подключение...")
                if not await self.websocket.connect():
                    self._write_log("❌ [WS] Не удалось подключиться, переподключение через 5 сек...")
                    await asyncio.sleep(5)
                    continue

                self.websocket_connected = True
                self._write_log("✅ [WS] WebSocket подключен")

                await self.websocket.subscribe(self.allowed_figis)

                consecutive_errors = 0
                while self.running and self.websocket_connected:
                    try:
                        prices = await self.websocket.receive_prices(duration_seconds=2)

                        if prices:
                            for figi, price in prices.items():
                                self.cached_prices[figi] = price

                                await self._put_to_queue_with_limit(
                                    self.price_queue,
                                    {
                                        "type": "price",
                                        "figi": figi,
                                        "price": price,
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }
                                )
                                self.stats["prices_received"] += 1

                            if len(prices) > 0:
                                self._write_log(f"📡 [WS] Получено {len(prices)} цен (очередь: {self.price_queue.qsize()})")

                        consecutive_errors = 0

                    except Exception as e:
                        consecutive_errors += 1
                        self._write_log(f"❌ [WS] Ошибка получения цен ({consecutive_errors}): {e}")
                        if consecutive_errors >= 3:
                            self.websocket_connected = False
                            break
                        await asyncio.sleep(1)

                if self.websocket:
                    await self.websocket.close()
                    self.websocket = None

                self.websocket_connected = False
                self._write_log("🔄 [WS] WebSocket отключен, переподключение через 5 сек...")
                await asyncio.sleep(5)

            except Exception as e:
                self._write_log(f"❌ [WS] Критическая ошибка: {e}")
                await asyncio.sleep(5)

        self._write_log("🛑 [WS] WebSocket поток остановлен")

    async def _put_to_queue_with_limit(self, queue: asyncio.Queue, item: Dict):
        """Кладёт элемент в очередь с обработкой переполнения"""
        try:
            await queue.put(item)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await queue.put(item)

    # ============================================================
    # Торговый поток
    # ============================================================

    async def _trading_worker(self):
        """Торговый поток: генерирует сигналы и выставляет заявки"""
        self._write_log("💰 [TRADE] Запуск торгового потока")

        # Создаём запись о запуске в БД
        await self._create_execution_log()

        await self._update_portfolio()

        cycle_count = 0

        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                cycle_count += 1

                self._write_log(f"\n🔄 [TRADE] ЦИКЛ {cycle_count}")

                await self.refresh_config()

                prices = await self._get_latest_prices_from_queue()
                queue_size = self.price_queue.qsize()
                if queue_size > 0:
                    self._write_log(f"📊 Очередь цен: {queue_size} сообщений")

                if prices:
                    await self._update_positions()

                    closed = await self._check_stop_loss(prices)

                    signals = await self._generate_signals(prices)
                    if signals:
                        signal_ids = await self.save_signals(self.db, self.schema, self.robot_id, signals)
                        self._write_log(f"   💾 Сохранено сигналов: {len(signal_ids)}")

                    trades = await self._execute_orders(signals)
                    if trades:
                        trade_ids = await self.save_trades(self.db, self.schema, self.robot_id, trades)
                        self._write_log(f"   💾 Сохранено сделок: {len(trade_ids)}")

                    self.stats["signals_generated"] += len(signals)
                    self.stats["orders_placed"] += len(trades)

                await self._process_order_statuses()

                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.update_interval - elapsed)
                if wait_time > 0:
                    self._write_log(f"⏱️ [TRADE] Ожидание {wait_time:.1f} сек...")
                    await asyncio.sleep(wait_time)

            except asyncio.CancelledError:
                self._write_log("⏹️ [TRADE] Торговый поток отменен")
                raise
            except Exception as e:
                self._write_log(f"❌ [TRADE] Ошибка в цикле: {e}")
                import traceback
                self._write_log(traceback.format_exc())
                self.stats["errors"] += 1
                await asyncio.sleep(5)

        # Завершаем запись выполнения
        execution_time_ms = int(self.stats.get("execution_time", 0))
        await self._complete_execution_log(
            status=1 if self.stats["errors"] == 0 else 2,
            message=f"Completed. Signals: {self.stats['signals_generated']}, Trades: {self.stats['orders_placed']}",
            execution_time_ms=execution_time_ms
        )

        self._write_log("🛑 [TRADE] Торговый поток остановлен")

    async def _get_latest_prices_from_queue(self) -> Dict[str, float]:
        """Забирает последние цены из очереди"""
        prices = {}

        while not self.price_queue.empty():
            try:
                item = self.price_queue.get_nowait()
                if item.get("type") == "price":
                    prices[item["figi"]] = item["price"]
            except asyncio.QueueEmpty:
                break

        if prices:
            self.cached_prices.update(prices)
            return prices

        return self.cached_prices.copy()

    async def _process_order_statuses(self):
        """Обрабатывает статусы заявок из очереди"""
        statuses = []

        while not self.order_queue.empty():
            try:
                item = self.order_queue.get_nowait()
                statuses.append(item)
            except asyncio.QueueEmpty:
                break

        for status in statuses:
            self._write_log(f"📋 [TRADE] Статус заявки: {status.get('order_id')} -> {status.get('status')}")
            if self.db:
                await self.update_trade_status(
                    self.db, self.schema,
                    status.get("order_id"),
                    status.get("status")
                )

    # ============================================================
    # Основной метод run
    # ============================================================

    async def run(self) -> Dict[str, Any]:
        """Запуск торговой сессии"""
        start_time = datetime.now(timezone.utc)

        self._write_log("=" * 60)
        self._write_log(f"🚀 СТАРТ ТОРГОВОЙ СЕССИИ для робота {self.robot_id}")
        self._write_log(f"   Account ID: {self.account_id}")
        self._write_log(f"   FIGIs: {self.allowed_figis}")
        self._write_log(f"   Strategy: {self.strategy_name}")
        self._write_log(f"   Update interval: {self.update_interval} сек")
        self._write_log("=" * 60)

        try:
            if not self.account_id:
                raise Exception("account_id не указан в конфигурации")
            if not self.allowed_figis:
                raise Exception("allowed_figis не указан в конфигурации")

            websocket_task = asyncio.create_task(self._websocket_worker())
            trading_task = asyncio.create_task(self._trading_worker())

            await asyncio.gather(websocket_task, trading_task)

        except asyncio.CancelledError:
            self._write_log("⏹️ Сессия отменена")
        except Exception as e:
            self._write_log(f"❌ Критическая ошибка: {e}")
            import traceback
            self._write_log(traceback.format_exc())
        finally:
            self.running = False
            await self.facade.close()
            self._api_logger = None
            if self._own_db and self.db:
                self.db.close()

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.stats["execution_time"] = execution_time * 1000

        self._write_log("=" * 60)
        self._write_log(f"✅ СЕССИЯ ЗАВЕРШЕНА")
        self._write_log(f"   Время работы: {execution_time:.1f} сек")
        self._write_log(f"   📊 Статистика:")
        self._write_log(f"      Цен получено: {self.stats['prices_received']}")
        self._write_log(f"      Сигналов: {self.stats['signals_generated']}")
        self._write_log(f"      Заявок: {self.stats['orders_placed']}")
        self._write_log(f"      Ошибок: {self.stats['errors']}")
        self._write_log("=" * 60)

        return {
            "status": "success" if self.stats["errors"] == 0 else "partial",
            "duration_seconds": execution_time,
            "stats": self.stats
        }

    # ============================================================
    # Вспомогательные методы
    # ============================================================

    async def _update_portfolio(self):
        """Обновляет информацию о портфеле"""
        self._write_log("💰 [TRADE] Обновление портфеля...")
        try:
            stage3 = Stage3Portfolio(self.token, self.account_id, self._write_log)
            self.portfolio = await stage3.get_portfolio()
            if self.portfolio:
                self._write_log(f"   Портфель: {self.portfolio.get('total_value', 0):.2f} руб.")
                self._write_log(f"   Свободно: {self.portfolio.get('free_funds', 0):.2f} руб.")
        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения портфеля: {e}")
            self.portfolio = {"total_value": 0, "free_funds": 0}

    async def _update_positions(self):
        """Обновляет информацию об открытых позициях"""
        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для получения позиций")
            return

        self._write_log("📊 [TRADE] Получение открытых позиций...")
        try:
            stage4 = Stage4Positions(
                self.db, self.schema, self.token, self.account_id,
                self.robot_id, self._write_log
            )
            self.positions = await stage4.get_open_positions()
            self.cached_positions = self.positions
            self._write_log(f"   Открыто позиций: {len(self.positions)}")
        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения позиций: {e}")
            self.positions = self.cached_positions

    async def _check_stop_loss(self, prices: Dict[str, float]) -> List[Dict]:
        """Проверяет стоп-лоссы и тейк-профиты"""
        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для проверки стоп-лоссов")
            return []

        self._write_log("🔴 [TRADE] Проверка стоп-лоссов...")
        try:
            stage4 = Stage4Positions(
                self.db, self.schema, self.token, self.account_id,
                self.robot_id, self._write_log
            )
            closed = await stage4.check_stop_loss_take_profit(
                self.positions or [], prices, self.risk_params
            )
            if closed:
                self._write_log(f"   Закрыто позиций: {len(closed)}")
            return closed
        except Exception as e:
            self._write_log(f"   ❌ Ошибка проверки стоп-лоссов: {e}")
            return []

    async def _generate_signals(self, prices: Dict[str, float]) -> List[Dict]:
        """Генерирует сигналы через Stage5Signals"""
        self._write_log("🎯 [TRADE] Генерация сигналов...")

        stage5 = Stage5Signals(self.token, self._write_log)

        # Функция для логирования API вызовов
        async def log_api_call_wrapper(**kwargs):
            await self._log_api_call(**kwargs)

        signals = await stage5.generate_signals(
            figis=self.allowed_figis,
            strategy_name=self.strategy_name,
            strategy_params=self.strategy_params,
            risk_params=self.risk_params,
            portfolio_value=self.portfolio.get("total_value", 0) if self.portfolio else 0,
            free_funds=self.portfolio.get("free_funds", 0) if self.portfolio else 0,
            open_positions=self.positions or [],
            current_prices=prices,
            log_api_call_func=log_api_call_wrapper,
            token_id=self.token_id,
            user_id=self.user_id
        )

        return signals

    async def _execute_orders(self, signals: List[Dict]) -> List[Dict]:
        """Выставляет заявки"""
        if not signals:
            return []

        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для сохранения заявок")
            return []

        self._write_log("📊 [TRADE] Выставление заявок...")
        stage6 = Stage6Orders(
            self.db, self.schema, self.token, self.account_id,
            self.robot_id, self.token_id, self.user_id, self._write_log
        )
        trades = await stage6.execute_signals(signals)

        for trade in trades:
            if trade.get("order_id"):
                await self._put_to_queue_with_limit(
                    self.order_queue,
                    {
                        "type": "order_status",
                        "order_id": trade["order_id"],
                        "status": trade["status"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

        return trades