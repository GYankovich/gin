"""
Торговая сессия для одного робота
WebSocket и торговля в независимых потоках через очередь
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import logging
import json
from pathlib import Path

from sqlalchemy import text

from app.modules.robots.trading.stages.stage2_websocket import Stage2WebSocket
from app.modules.robots.trading.stages.stage3_portfolio import Stage3Portfolio
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage5_signals import Stage5Signals
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders
from app.modules.tinvest.methods.instruments import InstrumentsClient

logger = logging.getLogger(__name__)


class TradingSession:
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

        # Компоненты
        self.websocket = None
        self.portfolio = None
        self.positions = None

        # Очереди для потоков
        self.price_queue = asyncio.Queue(maxsize=1000)      # цены от WebSocket
        self.order_queue = asyncio.Queue(maxsize=100)       # статусы заявок
        self.signal_queue = asyncio.Queue(maxsize=100)      # сигналы на исполнение

        # Флаги состояния
        self.websocket_connected = False
        self.running = True

        # Кэши
        self.cached_prices: Dict[str, float] = {}           # последние цены
        self.cached_positions: List[Dict] = []              # открытые позиции

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

        # Файловый логгер
        self._file_log = None
        self._init_file_logger()

        # Обновляем конфиг
        self._update_config(config)

    def _init_file_logger(self):
        """Создает файловый логгер для сессии"""
        log_dir = Path("logs/trading_robots")
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"session_{self.robot_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._file_log = open(log_file, 'w', encoding='utf-8')
        self._write_file_log(f"Лог файл создан: {log_file}")
        self._write_file_log(f"Сессия робота {self.robot_id}")

    def _write_file_log(self, message: str):
        """Запись в файловый лог"""
        if self._file_log:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._file_log.write(f"[{timestamp}] [ROBOT_{self.robot_id}] {message}\n")
            self._file_log.flush()

    def _write_log(self, message: str):
        """Запись в лог (и в файл, и в system_log)"""
        self._write_file_log(message)
        if self._log_func:
            self._log_func(f"[SESSION {self.robot_id}] {message}")

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
        self._write_log("🔄 Обновление конфигурации из БД...")

        try:
            query = """
                SELECT config FROM {}.robots
                WHERE id = :robot_id AND status = 1
            """.format(self.schema)

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
            self.db.rollback()

    # ============================================================
    # WebSocket поток (независимый)
    # ============================================================

    async def _websocket_worker(self):
        """
        WebSocket поток:
        - Подключается к WebSocket
        - При разрыве переподключается
        - Получает цены и кладёт в очередь
        """
        self._write_log("🔌 [WS] Запуск WebSocket потока")

        while self.running:
            try:
                # Создаём WebSocket клиент
                self.websocket = Stage2WebSocket(self.token, self.robot_id, self._write_log)

                # Подключаемся
                self._write_log("🔌 [WS] Подключение...")
                if not await self.websocket.connect():
                    self._write_log("❌ [WS] Не удалось подключиться, переподключение через 5 сек...")
                    await asyncio.sleep(5)
                    continue

                self.websocket_connected = True
                self._write_log("✅ [WS] WebSocket подключен")

                # Подписываемся на FIGI
                await self.websocket.subscribe(self.allowed_figis)

                # Основной цикл получения цен
                consecutive_errors = 0
                while self.running and self.websocket_connected:
                    try:
                        # Получаем цены (блокирующий вызов)
                        prices = await self.websocket.receive_prices(duration_seconds=2)

                        if prices:
                            for figi, price in prices.items():
                                # Обновляем кэш
                                self.cached_prices[figi] = price

                                # Кладём в очередь для торгового потока
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

                # Если вышли из цикла, закрываем WebSocket
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
        """
        Кладёт элемент в очередь с обработкой переполнения
        Если очередь переполнена — удаляет старый элемент
        """
        try:
            await queue.put(item)
        except asyncio.QueueFull:
            # Очередь переполнена, удаляем один старый элемент
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await queue.put(item)

    # ============================================================
    # Торговый поток (независимый)
    # ============================================================

    async def _trading_worker(self):
        """
        Торговый поток:
        - Не зависит от состояния WebSocket
        - Читает цены из очереди
        - Генерирует сигналы
        - Выставляет заявки
        - Проверяет SL/TP
        """
        self._write_log("💰 [TRADE] Запуск торгового потока")

        # Получаем портфель один раз при старте
        await self._update_portfolio()

        cycle_count = 0

        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                cycle_count += 1

                self._write_log(f"\n🔄 [TRADE] ЦИКЛ {cycle_count}")

                # 1. Обновляем конфиг
                await self.refresh_config()

                # 2. Получаем актуальные цены из очереди
                prices = await self._get_latest_prices_from_queue()
                queue_size = self.price_queue.qsize()
                if queue_size > 0:
                    self._write_log(f"📊 Очередь цен: {queue_size} сообщений")

                # 3. Если есть новые цены — генерируем сигналы
                if prices:
                    # Обновляем позиции
                    await self._update_positions()

                    # Проверяем стоп-лоссы
                    closed = await self._check_stop_loss(prices)

                    # Генерируем сигналы
                    signals = await self._generate_signals(prices)
                    if signals:
                        signal_ids = await self._save_signals(signals)
                        self._write_log(f"   💾 Сохранено сигналов: {len(signal_ids)}")

                    # Выставляем заявки
                    trades = await self._execute_orders(signals)
                    if trades:
                        trade_ids = await self._save_trades(trades)
                        self._write_log(f"   💾 Сохранено сделок: {len(trade_ids)}")


                    # Обновляем статистику
                    self.stats["signals_generated"] += len(signals)
                    self.stats["orders_placed"] += len(trades)

                # 4. Проверяем статусы заявок из очереди
                await self._process_order_statuses()
                await self._update_order_statuses()

                # 5. Ждём следующий цикл
                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.update_interval - elapsed)
                if wait_time > 0:
                    self._write_log(f"⏱️ [TRADE] Ожидание {wait_time:.1f} сек...")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                self._write_log(f"❌ [TRADE] Ошибка в цикле: {e}")
                import traceback
                self._write_log(traceback.format_exc())
                self.stats["errors"] += 1
                await asyncio.sleep(5)

        self._write_log("🛑 [TRADE] Торговый поток остановлен")

    async def _get_latest_prices_from_queue(self) -> Dict[str, float]:
        """
        Забирает последние цены из очереди
        Возвращает словарь {figi: price} с самыми свежими ценами
        """
        prices = {}

        # Забираем все сообщения из очереди (не блокируя)
        while not self.price_queue.empty():
            try:
                item = self.price_queue.get_nowait()
                if item.get("type") == "price":
                    prices[item["figi"]] = item["price"]
            except asyncio.QueueEmpty:
                break

        # Если есть новые цены — обновляем кэш
        if prices:
            self.cached_prices.update(prices)
            return prices

        # Если нет новых — возвращаем кэш
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
            # TODO: обновить статус в БД

    # ============================================================
    # Основной метод run
    # ============================================================

    async def run(self) -> Dict[str, Any]:
        """
        Запуск торговой сессии
        Запускает WebSocket и торговый потоки параллельно
        """
        self._write_log("=" * 60)
        self._write_log(f"🚀 СТАРТ ТОРГОВОЙ СЕССИИ для робота {self.robot_id}")
        self._write_log(f"   Account ID: {self.account_id}")
        self._write_log(f"   FIGIs: {self.allowed_figis}")
        self._write_log(f"   Strategy: {self.strategy_name}")
        self._write_log(f"   Update interval: {self.update_interval} сек")
        self._write_log("=" * 60)

        start_time = datetime.now(timezone.utc)

        try:
            if not self.account_id:
                raise Exception("account_id не указан в конфигурации")
            if not self.allowed_figis:
                raise Exception("allowed_figis не указан в конфигурации")

            # Запускаем оба потока параллельно
            websocket_task = asyncio.create_task(self._websocket_worker())
            trading_task = asyncio.create_task(self._trading_worker())

            # Ждём оба потока (пока не остановят)
            await asyncio.gather(websocket_task, trading_task)

        except asyncio.CancelledError:
            self._write_log("⏹️ Сессия отменена")
        except Exception as e:
            self._write_log(f"❌ Критическая ошибка: {e}")
            import traceback
            self._write_log(traceback.format_exc())
        finally:
            self.running = False
            if self._file_log:
                self._file_log.close()

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Выводим итоговую статистику
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
            "status": "success",
            "duration_seconds": execution_time,
            "stats": self.stats
        }

    # ============================================================
    # Вспомогательные методы (портфель, позиции, сигналы, заявки)
    # ============================================================

    async def _update_portfolio(self):
        """Обновляет информацию о портфеле"""
        self._write_log("💰 [TRADE] Обновление портфеля...")
        try:
            stage3 = Stage3Portfolio(self.db, self.token, self.user_id, self.token_id, self.robot_id, self._write_log)
            self.portfolio = await stage3.get_portfolio()
            if self.portfolio:
                self._write_log(f"   Портфель: {self.portfolio.get('total_value', 0):.2f} руб.")
                self._write_log(f"   Свободно: {self.portfolio.get('free_funds', 0):.2f} руб.")
            self.db.commit()
        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения портфеля: {e}")
            self.db.rollback()
            self.portfolio = {"total_value": 0, "free_funds": 0}

    async def _update_positions(self):
        """Обновляет информацию об открытых позициях"""
        self._write_log("📊 [TRADE] Получение открытых позиций...")
        try:
            stage4 = Stage4Positions(
                self.db, self.schema, self.token, self.account_id,
                self.robot_id, self._write_log
            )
            self.positions = await stage4.get_open_positions()
            self.cached_positions = self.positions
            self._write_log(f"   Открыто позиций: {len(self.positions)}")
            self.db.commit()
        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения позиций: {e}")
            self.db.rollback()
            self.positions = self.cached_positions

    async def _check_stop_loss(self, prices: Dict[str, float]) -> List[Dict]:
        """Проверяет стоп-лоссы и тейк-профиты"""
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
            self.db.commit()
            return closed
        except Exception as e:
            self._write_log(f"   ❌ Ошибка проверки стоп-лоссов: {e}")
            self.db.rollback()
            return []

    async def _get_candles(self) -> Dict[str, List[Dict]]:
        """Получает свечи для стратегии"""
        self._write_log("📊 [TRADE] Получение свечей...")

        rest_client = InstrumentsClient(self.token)
        candles = {}

        interval = self.strategy_params.get("interval", "CANDLE_INTERVAL_DAY")
        days = self.strategy_params.get("candle_days", 60)

        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)

        for figi in self.allowed_figis:
            try:
                result = await rest_client.get_candles(figi, from_date, to_date, interval)
                candles[figi] = result
                self._write_log(f"   {figi}: получено {len(result)} свечей")
            except Exception as e:
                self._write_log(f"   ❌ Ошибка получения свечей {figi}: {e}")
                candles[figi] = []

        return candles

    async def _generate_signals(self, prices: Dict[str, float]) -> List[Dict]:
        """Генерирует сигналы"""
        self._write_log("🎯 [TRADE] Генерация сигналов...")

        candles = await self._get_candles()

        stage5 = Stage5Signals(self._write_log)
        signals = await stage5.generate_signals(
            candles=candles,
            prices=prices,
            figis=self.allowed_figis,
            strategy_name=self.strategy_name,
            strategy_params=self.strategy_params,
            risk_params=self.risk_params,
            portfolio_value=self.portfolio.get("total_value", 0) if self.portfolio else 0,
            free_funds=self.portfolio.get("free_funds", 0) if self.portfolio else 0,
            open_positions=self.positions or []
        )

        if signals:
            self._write_log(f"   Сгенерировано сигналов: {len(signals)}")
            for s in signals:
                self._write_log(f"      {s['figi']}: {s['signal']} {s['quantity']} лотов по {s['price']:.4f}")

        return signals

    async def _execute_orders(self, signals: List[Dict]) -> List[Dict]:
        """Выставляет заявки"""
        if not signals:
            return []

        self._write_log("📊 [TRADE] Выставление заявок...")
        stage6 = Stage6Orders(
            self.db, self.schema, self.token, self.account_id,
            self.robot_id, self.token_id, self.user_id, self._write_log
        )
        trades = await stage6.execute_signals(signals)

        # Отправляем статусы в очередь
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

    async def _save_signals(self, signals: List[Dict]) -> List[int]:
        """Сохраняет сигналы в БД"""
        if not self.db or not signals:
            return []

        signal_ids = []

        for signal in signals:
            query = """
                INSERT INTO {}.robot_signals
                (robot_id, figi, signal_type, signal_strength, price_at_signal, 
                 was_executed, created_at)
                VALUES
                (:robot_id, :figi, :signal_type, :signal_strength, :price, 
                 0, :now)
                RETURNING id
            """.format(self.schema)

            try:
                result = self.db.execute(
                    text(query),
                    {
                        "robot_id": self.robot_id,
                        "figi": signal["figi"],
                        "signal_type": signal["signal"].lower(),
                        "signal_strength": 100,
                        "price": signal["price"],
                        "now": datetime.now(timezone.utc)
                    }
                ).first()

                if result:
                    signal_ids.append(result[0])
                    self._write_log(f"   Сигнал сохранен: ID={result[0]}, {signal['figi']} {signal['signal']}")

            except Exception as e:
                self._write_log(f"   ❌ Ошибка сохранения сигнала: {e}")
                self.db.rollback()

        if signal_ids:
            self.db.commit()

        return signal_ids

    async def _save_trades(self, trades: List[Dict]) -> List[int]:
        """Сохраняет сделки в БД"""
        if not self.db or not trades:
            return []

        trade_ids = []

        for trade in trades:
            query = """
                INSERT INTO {}.robot_trades
                (robot_id, figi, side, quantity, price, total_amount, 
                 entry_price, commission, status, order_id, created_at)
                VALUES
                (:robot_id, :figi, :side, :quantity, :price, :total_amount,
                 :entry_price, :commission, :status, :order_id, :now)
                RETURNING id
            """.format(self.schema)

            try:
                result = self.db.execute(
                    text(query),
                    {
                        "robot_id": self.robot_id,
                        "figi": trade["figi"],
                        "side": trade["side"],
                        "quantity": trade["quantity"],
                        "price": trade["price"],
                        "total_amount": trade["total_amount"],
                        "entry_price": trade.get("entry_price"),
                        "commission": trade.get("commission"),
                        "status": trade["status"],
                        "order_id": trade.get("order_id"),
                        "now": datetime.now(timezone.utc)
                    }
                ).first()

                if result:
                    trade_ids.append(result[0])
                    self._write_log(f"   Сделка сохранена: ID={result[0]}, {trade['figi']} {trade['side']} {trade['quantity']} @ {trade['price']:.4f}")

            except Exception as e:
                self._write_log(f"   ❌ Ошибка сохранения сделки: {e}")
                self.db.rollback()

        if trade_ids:
            self.db.commit()

        return trade_ids

    async def _update_order_statuses(self):
        """Обновляет статусы всех открытых заявок"""
        if not self.positions:
            return

        # Получаем заявки со статусом open или partial
        open_orders = [p for p in self.positions if p.get("status") in ["open", "partial"]]

        if not open_orders:
            return

        self._write_log(f"🔄 Проверка статуса {len(open_orders)} заявок...")

        stage6 = Stage6Orders(
            self.db, self.schema, self.token, self.account_id,
            self.robot_id, self.token_id, self.user_id, self._write_log
        )

        for order in open_orders:
            order_id = order.get("order_id")
            if not order_id:
                continue

            status_info = await stage6.update_order_status(order_id)

            if status_info.get("is_filled") or status_info.get("is_cancelled") or status_info.get("is_rejected"):
                # Обновляем статус в БД
                await self._update_trade_status(
                    order_id,
                    status_info["status"],
                    status_info.get("executed_price"),
                    status_info.get("lots_executed"),
                    status_info.get("commission")
                )
                self._write_log(f"   ✅ Заявка {order_id}: {status_info['status']}")

    async def _update_trade_status(
            self,
            order_id: str,
            status: str,
            executed_price: float = None,
            filled_quantity: int = None,
            commission: float = None
    ):
        """Обновляет статус сделки в БД"""
        try:
            # Определяем новый статус
            if status == "EXECUTION_REPORT_STATUS_FILL":
                new_status = "closed"
            elif status == "EXECUTION_REPORT_STATUS_PARTIALLYFILL":
                new_status = "partial"
            elif status in ["EXECUTION_REPORT_STATUS_CANCELLED", "EXECUTION_REPORT_STATUS_REJECTED"]:
                new_status = "cancelled"
            else:
                new_status = status.lower()

            query = """
                UPDATE {}.robot_trades
                SET status = :status,
                    filled_quantity = COALESCE(:filled_quantity, filled_quantity),
                    avg_fill_price = COALESCE(:executed_price, avg_fill_price),
                    commission = COALESCE(:commission, commission),
                    updated_at = :now
                WHERE order_id = :order_id
            """.format(self.schema)

            self.db.execute(
                text(query),
                {
                    "order_id": order_id,
                    "status": new_status,
                    "filled_quantity": filled_quantity,
                    "executed_price": executed_price,
                    "commission": commission,
                    "now": datetime.now(timezone.utc)
                }
            )
            self.db.commit()

            # Если заявка полностью исполнена, обновляем entry_price и статус
            if status == "EXECUTION_REPORT_STATUS_FILL" and executed_price:
                await self._update_trade_entry_price(order_id, executed_price, filled_quantity)

        except Exception as e:
            self._write_log(f"   ❌ Ошибка обновления статуса сделки: {e}")
            self.db.rollback()

    async def _update_trade_entry_price(self, order_id: str, executed_price: float, filled_quantity: int):
        """Обновляет цену входа и количество для полностью исполненной заявки"""
        try:
            query = """
                UPDATE {}.robot_trades
                SET entry_price = :entry_price,
                    quantity = :quantity,
                    total_amount = :total_amount,
                    status = 'open'
                WHERE order_id = :order_id AND status IN ('pending', 'partial')
            """.format(self.schema)

            self.db.execute(
                text(query),
                {
                    "order_id": order_id,
                    "entry_price": executed_price,
                    "quantity": filled_quantity,
                    "total_amount": executed_price * filled_quantity
                }
            )
            self.db.commit()
            self._write_log(f"   📈 Обновлена цена входа: {executed_price:.4f} руб.")

        except Exception as e:
            self._write_log(f"   ❌ Ошибка обновления цены входа: {e}")
            self.db.rollback()