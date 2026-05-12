"""
Торговая сессия для одного робота
WebSocket и торговля в независимых потоках через очередь
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingSession [1]
#/// Исходный модуль `backend/app/modules/robots/trading/session.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Tuple

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
from app.modules.robots.trading.grain_seed_orchestrator import (
    evaluate_grain_seed_orchestration,
    filter_grain_seed_signals,
)
from app.modules.robots.trading.brokers import BrokerFacade, create_broker_facade
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.costs import resolve_robot_cost_rates, TradingCosts
from app.modules.robots.live_hub import live_event_hub

# Получаем системный логгер
system_log = get_logger("robots.trading.session")

_GRAIN_ORDER_ACTIVE = frozenset({
    "EXECUTION_REPORT_STATUS_NEW",
    "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
})


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
        self._cycle_id: Optional[int] = None
        self._api_logger: Optional[APILogger] = None

        # Компоненты
        self.websocket = None
        self.portfolio = None
        self.positions = None
        self.broker_type = "tinvest"
        self._broker: Optional[BrokerFacade] = None

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
        self._daily_trade_counter: Dict[str, int] = {}
        self._last_trade_by_figi: Dict[str, datetime] = {}
        self._pending_position_closures: Dict[str, Dict[str, Any]] = {}

        self._grain_seed_orchestration = None
        self._grain_seed_mismatch_logged = False
        self._grain_seed_force_time_logged = False
        self._grain_seed_streak_block_logged = False
        self._grain_seed_flatten_sent: Set[str] = set()

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
        self.strategy_name = "grain_seed"
        self.strategy_params = {}
        self.risk_params = {}
        self.update_interval = 10
        self.cost_params: Dict[str, float] = {
            "broker_commission_rate": 0.0005,
            "ndfl_rate": 0.15,
        }

        # Обновляем конфиг
        self._update_config(config)

    @property
    def broker(self) -> BrokerFacade:
        """Ленивая инициализация фасада брокера"""
        if self._broker is None:
            self._broker = create_broker_facade(self.broker_type, self.token)
        return self._broker

    def _write_log(self, message: str):
        """Запись в лог (и в файл, и в system_log)"""
        self._session_logger.info(message)
        try:
            asyncio.create_task(self._publish_live_event({
                "type": "log",
                "level": "INFO",
                "message": message,
                "robot_id": self.robot_id,
                "time": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass
        if self._log_func:
            try:
                self._log_func(f"[SESSION {self.robot_id}] {message}")
            except Exception:
                pass
        else:
            system_log.debug(f"[ROBOT_{self.robot_id}] {message}")

    async def _publish_live_event(self, payload: Dict[str, Any]) -> None:
        try:
            if "run_id" not in payload:
                payload["run_id"] = self._execution_log_id
            if "cycle_id" not in payload:
                payload["cycle_id"] = self._cycle_id
            await live_event_hub.publish(self.robot_id, payload)
        except Exception:
            pass

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
        self.strategy_name = self.config.get("strategy", "grain_seed")
        self.strategy_params = self.config.get("strategy_params", {})
        br, tx = resolve_robot_cost_rates(self.config)
        self.cost_params = {"broker_commission_rate": br, "ndfl_rate": tx}
        rp = dict(self.config.get("risk") or {})
        rp["broker_commission"] = br
        rp["ndfl"] = tx
        self.risk_params = rp
        self.broker_type = self.config.get("broker_type", "tinvest")
        self.update_interval = self.config.get("update_interval_seconds", 10)

        self._write_log(f"📋 Конфигурация обновлена:")
        self._write_log(f"   Account ID: {self.account_id}")
        self._write_log(f"   FIGIs: {self.allowed_figis}")
        self._write_log(f"   Strategy: {self.strategy_name}")
        self._write_log(f"   Broker: {self.broker_type}")
        self._write_log(
            f"   Издержки: комиссия {br:.6f}, НДФЛ {tx:.4f}"
        )
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
                old_strategy_params = dict(self.strategy_params)

                self._update_config(new_config)

                if old_figis != new_figis and self.websocket:
                    self._write_log(f"   FIGI изменились: {old_figis} -> {new_figis}")
                    asyncio.create_task(self.websocket.subscribe(list(new_figis)))
                if old_figis != new_figis or old_strategy_params != self.strategy_params:
                    await indicator_service.unregister_robot(self.robot_id)
                    await indicator_service.register_robot(self.robot_id, self.broker, self.allowed_figis, self.strategy_params)

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
                self.websocket = Stage2WebSocket(
                    broker=self.broker,
                    user_id=self.user_id,
                    robot_id=self.robot_id,
                    broker_type=self.broker_type,
                    log_func=self._write_log,
                )

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
            queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

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
                self._cycle_id = await self.create_run_cycle(
                    self.db,
                    self.schema,
                    self.robot_id,
                    execution_log_id=self._execution_log_id,
                    context={"cycle": cycle_count, "strategy": self.strategy_name, "broker_type": self.broker_type},
                )

                self._write_log(f"\n🔄 [TRADE] ЦИКЛ {cycle_count}")

                await self.refresh_config()

                if self.strategy_name == "grain_seed":
                    await self._update_portfolio()

                prices = await self._get_latest_prices_from_queue()
                queue_size = self.price_queue.qsize()
                if queue_size > 0:
                    self._write_log(f"📊 Очередь цен: {queue_size} сообщений")

                if prices:
                    await self._update_positions()

                    if self.strategy_name == "grain_seed":
                        await self._apply_grain_seed_orchestration()

                    orch = self._grain_seed_orchestration
                    flatten_trades: List[Dict[str, Any]] = []
                    use_force_flatten = (
                        self.strategy_name == "grain_seed"
                        and orch is not None
                        and orch.allow_only_reduce
                        and bool(self.strategy_params.get("force_market_flatten", True))
                    )
                    if use_force_flatten:
                        await self._grain_seed_cancel_open_orders_on_broker()
                        flatten_trades, closed = await self._grain_seed_market_close_open_positions(
                            prices
                        )
                    else:
                        closed = await self._check_stop_loss(prices)

                    for item in closed:
                        if item.get("order_id"):
                            self._pending_position_closures[item["order_id"]] = item
                            await self._put_to_queue_with_limit(
                                self.order_queue,
                                {
                                    "type": "order_status",
                                    "order_id": item["order_id"],
                                    "status": "pending_close",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )

                    signals = await self._generate_signals(prices)
                    if (
                        self.strategy_name == "grain_seed"
                        and self._grain_seed_orchestration is not None
                    ):
                        signals = filter_grain_seed_signals(
                            signals, self._grain_seed_orchestration
                        )
                    if await self._is_daily_loss_limit_breached():
                        self._write_log("🛑 [TRADE] Достигнут лимит max_daily_loss, новые сигналы пропущены")
                        signals = []
                    signal_ids = []
                    if signals:
                        signal_ids = await self.save_signals(self.db, self.schema, self.robot_id, signals)
                        self._write_log(f"   💾 Сохранено сигналов: {len(signal_ids)}")
                        for s in signals:
                            decision_id = await self.save_decision(
                                self.db,
                                self.schema,
                                self.robot_id,
                                stage="stage5_signals",
                                decision_type="signal",
                                decision=str(s.get("signal", "")).lower(),
                                reason_code=None,
                                payload=s,
                                execution_log_id=self._execution_log_id,
                                cycle_id=self._cycle_id,
                                figi=s.get("figi"),
                            )
                            await self._publish_live_event({
                                "type": "signal",
                                "robot_id": self.robot_id,
                                "figi": s.get("figi"),
                                "signal_type": str(s.get("signal", "")).lower(),
                                "price": s.get("price"),
                                "target_price": s.get("target_price"),
                                "indicators": s.get("indicators", {}),
                                "decision_id": decision_id,
                                "time": datetime.now(timezone.utc).isoformat(),
                            })

                    trades = await self._execute_orders(signals)
                    if flatten_trades and self.db:
                        ft_ids = await self.save_trades(
                            self.db, self.schema, self.robot_id, flatten_trades
                        )
                        self._write_log(f"   💾 [grain_seed] Сохранено принудительных заявок: {len(ft_ids)}")
                        for t in flatten_trades:
                            await self._publish_live_event({
                                "type": "order",
                                "robot_id": self.robot_id,
                                "figi": t.get("figi"),
                                "side": t.get("side"),
                                "quantity": t.get("quantity"),
                                "price": t.get("price"),
                                "status": t.get("status"),
                                "reason": "grain_seed_force_flatten",
                                "time": datetime.now(timezone.utc).isoformat(),
                            })

                    if trades:
                        trade_ids = await self.save_trades(self.db, self.schema, self.robot_id, trades)
                        self._write_log(f"   💾 Сохранено сделок: {len(trade_ids)}")
                        for idx, t in enumerate(trades):
                            trade_id = trade_ids[idx] if idx < len(trade_ids) else None
                            await self.save_decision(
                                self.db,
                                self.schema,
                                self.robot_id,
                                stage="stage6_orders",
                                decision_type="order",
                                decision=str(t.get("status", "unknown")),
                                reason_code=t.get("error"),
                                payload=t,
                                execution_log_id=self._execution_log_id,
                                cycle_id=self._cycle_id,
                                figi=t.get("figi"),
                            )
                            await self.save_order_event(
                                self.db,
                                self.schema,
                                self.robot_id,
                                order_id=t.get("order_id"),
                                status=str(t.get("status", "unknown")),
                                event_type="created",
                                trade_id=trade_id,
                                payload=t,
                            )
                            event_type = "order" if t.get("status") not in {"skipped"} else "skipped"
                            await self._publish_live_event({
                                "type": event_type,
                                "robot_id": self.robot_id,
                                "figi": t.get("figi"),
                                "side": t.get("side"),
                                "quantity": t.get("quantity"),
                                "price": t.get("price"),
                                "status": t.get("status"),
                                "reason": t.get("error"),
                                "time": datetime.now(timezone.utc).isoformat(),
                            })
                        executed_signal_ids = [
                            int(t["signal_id"])
                            for t in trades
                            if t.get("signal_id") and t.get("status") not in {"failed", "skipped"}
                        ]
                        marked = await self.mark_signals_executed(self.db, self.schema, executed_signal_ids)
                        if marked:
                            self._write_log(f"   ✅ Отмечено исполненных сигналов: {marked}")

                    self.stats["signals_generated"] += len(signals)
                    self.stats["orders_placed"] += len(trades) + len(flatten_trades)

                await self._process_order_statuses()

                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.update_interval - elapsed)
                if wait_time > 0:
                    self._write_log(f"⏱️ [TRADE] Ожидание {wait_time:.1f} сек...")
                    await asyncio.sleep(wait_time)
                if self._cycle_id:
                    await self.complete_run_cycle(self.db, self.schema, self._cycle_id, status="completed")
                    self._cycle_id = None

            except asyncio.CancelledError:
                self._write_log("⏹️ [TRADE] Торговый поток отменен")
                if self._cycle_id:
                    await self.complete_run_cycle(self.db, self.schema, self._cycle_id, status="cancelled")
                    self._cycle_id = None
                raise
            except Exception as e:
                self._write_log(f"❌ [TRADE] Ошибка в цикле: {e}")
                import traceback
                self._write_log(traceback.format_exc())
                self.stats["errors"] += 1
                if self._cycle_id:
                    await self.complete_run_cycle(
                        self.db,
                        self.schema,
                        self._cycle_id,
                        status="failed",
                        context={"error": str(e)},
                    )
                    self._cycle_id = None
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
        order_ids: List[str] = []

        while not self.order_queue.empty():
            try:
                item = self.order_queue.get_nowait()
                statuses.append(item)
                if item.get("order_id"):
                    order_ids.append(item.get("order_id"))
            except asyncio.QueueEmpty:
                break

        order_ids.extend(await self._get_open_order_ids())
        dedup_order_ids = list(dict.fromkeys([oid for oid in order_ids if oid]))
        if not dedup_order_ids:
            return

        stage6 = Stage6Orders(
            self.db, self.schema, self.broker, self.account_id,
            self.robot_id, self.token_id, self.user_id, self._write_log,
            daily_trade_counter=self._daily_trade_counter,
            last_trade_by_figi=self._last_trade_by_figi,
            cost_params=self.cost_params,
        )

        for order_id in dedup_order_ids:
            state = await stage6.update_order_status(order_id)
            execution_status = state.get("status", "UNKNOWN")
            self._write_log(f"📋 [TRADE] Статус заявки: {order_id} -> {execution_status}")
            if self.db:
                await self.update_trade_status(
                    self.db, self.schema,
                    order_id,
                    execution_status,
                    executed_price=state.get("executed_price"),
                    filled_quantity=state.get("lots_executed"),
                    commission=state.get("commission"),
                )
                await self.save_order_event(
                    self.db,
                    self.schema,
                    self.robot_id,
                    order_id=order_id,
                    status=str(execution_status),
                    event_type="status_update",
                    payload=state,
                )
            await self._publish_live_event({
                "type": "order",
                "robot_id": self.robot_id,
                "order_id": order_id,
                "status": Stage6Orders.map_execution_status_to_trade_status(str(execution_status)),
                "execution_status": execution_status,
                "filled_quantity": state.get("lots_executed"),
                "time": datetime.now(timezone.utc).isoformat(),
            })

            if execution_status == "EXECUTION_REPORT_STATUS_FILL":
                pending_close = self._pending_position_closures.pop(order_id, None)
                if pending_close:
                    await self._finalize_position_close(pending_close)

    async def _get_open_order_ids(self) -> List[str]:
        if not self.db:
            return []
        query = f"""
            SELECT order_id
            FROM {self.schema}.robot_trades
            WHERE robot_id = :robot_id
              AND order_id IS NOT NULL
              AND status IN ('open', 'pending', 'partial')
            ORDER BY created_at DESC
            LIMIT 200
        """
        try:
            rows = self.db.execute(text(query), {"robot_id": self.robot_id}).fetchall()
            return [r[0] for r in rows if r and r[0]]
        except Exception:
            return []

    async def _finalize_position_close(self, pending: Dict[str, Any]) -> None:
        if not self.db:
            return
        stage4 = Stage4Positions(
            self.db, self.schema, self.broker, self.account_id,
            self.robot_id, self._write_log, cost_params=self.cost_params,
        )
        await stage4._close_trade(
            pending["trade_id"],
            pending["exit_price"],
            pending.get("reason", "filled"),
            pending.get("profit", 0.0),
            0.0,
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
        self._write_log(f"   Broker: {self.broker_type}")
        self._write_log(
            f"   Издержки: комиссия {self.cost_params['broker_commission_rate']:.6f}, "
            f"НДФЛ {self.cost_params['ndfl_rate']:.4f}"
        )
        self._write_log(f"   Update interval: {self.update_interval} сек")
        self._write_log("=" * 60)

        try:
            if not self.account_id:
                raise Exception("account_id не указан в конфигурации")
            if not self.allowed_figis:
                raise Exception("allowed_figis не указан в конфигурации")

            await indicator_service.register_robot(self.robot_id, self.broker, self.allowed_figis, self.strategy_params)

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
            await indicator_service.unregister_robot(self.robot_id)
            await self.broker.close()
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
            stage3 = Stage3Portfolio(self.account_id, self.broker, self._write_log)
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
                self.db, self.schema, self.broker, self.account_id,
                self.robot_id, self._write_log, cost_params=self.cost_params,
            )
            self.positions = await stage4.get_open_positions()
            self.cached_positions = self.positions
            self._write_log(f"   Открыто позиций: {len(self.positions)}")
        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения позиций: {e}")
            self.positions = self.cached_positions

    async def _apply_grain_seed_orchestration(self) -> None:
        """Правила сессии для grain_seed: резерв средств, серия убытков, сверка с брокером, окно закрытия МСК."""
        if self.strategy_name != "grain_seed" or not self.account_id:
            return
        try:
            portfolio_raw = await self.broker.get_portfolio(self.account_id)
        except Exception as e:
            self._write_log(f"   ❌ [grain_seed] Портфель для оркестрации: {e}")
            return

        orch = evaluate_grain_seed_orchestration(
            now_utc=datetime.now(timezone.utc),
            portfolio=portfolio_raw,
            strategy_params=self.strategy_params,
            open_positions=self.positions or [],
            db=self.db,
            schema=self.schema,
            robot_id=self.robot_id,
        )
        self._grain_seed_orchestration = orch
        if self.portfolio:
            self.portfolio["free_funds"] = orch.effective_free_funds

        if orch.position_mismatch and not self._grain_seed_mismatch_logged:
            self._grain_seed_mismatch_logged = True
            self._write_log(
                "⚠️ [grain_seed] Позиции брокера и БД различаются: "
                f"broker={sorted(orch.broker_non_currency_figis)} "
                f"db_open={sorted(orch.db_open_figis)}"
            )

        if orch.block_new_entries and not self._grain_seed_streak_block_logged:
            self._grain_seed_streak_block_logged = True
            self._write_log(f"🛑 [grain_seed] Новые покупки отключены: {orch.block_reason}")
        if orch.allow_only_reduce and not self._grain_seed_force_time_logged:
            self._grain_seed_force_time_logged = True
            self._write_log(
                "⏱️ [grain_seed] Время принудительного сворачивания (МСК): новые BUY отфильтрованы."
            )

    async def _grain_seed_cancel_open_orders_on_broker(self) -> None:
        """Отмена активных заявок робота, которые ещё есть на стороне брокера."""
        if not self.account_id or not self.db:
            return
        try:
            broker_orders = await self.broker.get_orders(self.account_id)
        except Exception as e:
            self._write_log(f"   ❌ [grain_seed] GetOrders: {e}")
            return
        by_id = {o.get("orderId"): o for o in broker_orders if o.get("orderId")}
        our_ids = await self._get_open_order_ids()
        for oid in our_ids:
            bo = by_id.get(oid)
            if not bo:
                continue
            st = bo.get("executionReportStatus", "")
            if st not in _GRAIN_ORDER_ACTIVE:
                continue
            try:
                await self.broker.cancel_order(self.account_id, oid)
                self._write_log(f"   🧾 [grain_seed] Отменена заявка {oid} ({st})")
            except Exception as e:
                self._write_log(f"   ⚠️ [grain_seed] Отмена {oid}: {e}")

    async def _grain_seed_market_close_open_positions(
        self,
        prices: Dict[str, float],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Рыночное закрытие открытых позиций из БД (после времени force_close_time_msk).
        Возвращает (сделки для save_trades, элементы для pending_position_closures).
        """
        trades_out: List[Dict[str, Any]] = []
        closures: List[Dict[str, Any]] = []
        if not self.positions:
            return trades_out, closures

        open_figis = {str(p.get("figi")) for p in self.positions if p.get("figi")}
        self._grain_seed_flatten_sent &= open_figis

        cost_kw = {
            "broker_commission_rate": float(self.cost_params["broker_commission_rate"]),
            "ndfl_rate": float(self.cost_params["ndfl_rate"]),
        }

        for pos in self.positions:
            figi = str(pos.get("figi") or "")
            if not figi or figi in self._grain_seed_flatten_sent:
                continue
            qty = int(pos.get("quantity") or 0)
            if qty <= 0:
                continue
            side = str(pos.get("side", "")).lower()
            if side in ("buy", "long"):
                direction = "ORDER_DIRECTION_SELL"
                close_side = "sell"
                is_long = True
            elif side in ("sell", "short"):
                direction = "ORDER_DIRECTION_BUY"
                close_side = "buy"
                is_long = False
            else:
                continue

            px = prices.get(figi) or self.cached_prices.get(figi)
            if px is None or float(px) <= 0:
                lp = await self.broker.get_last_price(self.user_id, figi)
                px = float(lp or 0.0)
            if px <= 0:
                self._write_log(
                    f"   ⚠️ [grain_seed] Нет цены для рыночного закрытия {figi}, пропуск"
                )
                continue

            try:
                order = await self.broker.post_market_order(
                    figi, qty, direction, self.account_id
                )
            except Exception as e:
                self._write_log(f"   ❌ [grain_seed] Рыночная заявка {figi}: {e}")
                continue

            order_id = order.get("orderId")
            order_status = order.get(
                "executionReportStatus", "EXECUTION_REPORT_STATUS_NEW"
            )
            if order_status == "EXECUTION_REPORT_STATUS_REJECTED":
                self._write_log(f"   ⚠️ [grain_seed] Рыночная заявка отклонена {figi}")
                continue

            self._grain_seed_flatten_sent.add(figi)

            is_buy_close = close_side == "buy"
            costs_close = TradingCosts(px, qty, is_buy=is_buy_close, **cost_kw)
            commission = costs_close.calculate_commission()
            db_status = Stage6Orders.map_execution_status_to_trade_status(str(order_status))

            trades_out.append({
                "figi": figi,
                "side": close_side,
                "quantity": qty,
                "price": px,
                "total_amount": qty * px,
                "entry_price": px,
                "commission": commission,
                "status": db_status,
                "execution_status": order_status,
                "order_id": order_id,
            })

            costs_pos = TradingCosts(
                float(pos.get("entry_price") or px),
                qty,
                is_buy=is_long,
                **cost_kw,
            )
            profit_calc = costs_pos.calculate_actual_profit(px)

            closures.append({
                "trade_id": pos["id"],
                "order_id": order_id,
                "figi": figi,
                "exit_price": px,
                "reason": "grain_seed_force_flatten",
                "profit": profit_calc.get("net_profit", 0.0),
            })
            self._write_log(
                f"   📤 [grain_seed] Рыночное закрытие {figi} qty={qty} order={order_id} ({order_status})"
            )

        return trades_out, closures

    async def _check_stop_loss(self, prices: Dict[str, float]) -> List[Dict]:
        """Проверяет стоп-лоссы и тейк-профиты"""
        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для проверки стоп-лоссов")
            return []

        self._write_log("🔴 [TRADE] Проверка стоп-лоссов...")
        try:
            stage4 = Stage4Positions(
                self.db, self.schema, self.broker, self.account_id,
                self.robot_id, self._write_log, cost_params=self.cost_params,
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

    async def _is_daily_loss_limit_breached(self) -> bool:
        if not self.db:
            return False
        max_daily_loss = float(self.risk_params.get("max_daily_loss", 0) or 0)
        if max_daily_loss <= 0:
            return False
        total_value = float((self.portfolio or {}).get("total_value", 0) or 0)
        if total_value <= 0:
            return False
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = f"""
            SELECT COALESCE(SUM(COALESCE(profit, 0)), 0)
            FROM {self.schema}.robot_trades
            WHERE robot_id = :robot_id
              AND created_at >= :day_start
              AND status IN ('closed', 'cancelled', 'rejected')
        """
        try:
            result = self.db.execute(text(query), {"robot_id": self.robot_id, "day_start": day_start}).first()
            daily_pnl = float(result[0] if result and result[0] is not None else 0.0)
        except Exception:
            return False
        daily_loss_pct = (-daily_pnl / total_value) * 100.0 if daily_pnl < 0 else 0.0
        return daily_loss_pct >= max_daily_loss

    async def _generate_signals(self, prices: Dict[str, float]) -> List[Dict]:
        """Генерирует сигналы через Stage5Signals"""
        self._write_log("🎯 [TRADE] Генерация сигналов...")

        stage5 = Stage5Signals(self.broker, self._write_log)

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
            self.db, self.schema, self.broker, self.account_id,
            self.robot_id, self.token_id, self.user_id, self._write_log,
            daily_trade_counter=self._daily_trade_counter,
            last_trade_by_figi=self._last_trade_by_figi,
            cost_params=self.cost_params,
        )
        trades = await stage6.execute_signals(signals, risk_params=self.risk_params)
        skipped = [t for t in trades if t.get("status") == "skipped"]
        if skipped:
            reasons: Dict[str, int] = {}
            for trade in skipped:
                reason = trade.get("error", "UNKNOWN")
                reasons[reason] = reasons.get(reason, 0) + 1
            self._write_log(f"⚠️ [TRADE] Пропущено сделок: {len(skipped)}; причины: {reasons}")

        for trade in trades:
            if trade.get("order_id"):
                await self._put_to_queue_with_limit(
                    self.order_queue,
                    {
                        "type": "order_status",
                        "order_id": trade["order_id"],
                        "status": trade.get("execution_status", trade["status"]),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

        return trades