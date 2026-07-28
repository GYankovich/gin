"""
Торговая сессия для одного робота
WebSocket и торговля в независимых потоках через очередь
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingSession [1]
#/// Исходный модуль `backend/app/modules/robots/trading/session.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from datetime import datetime, timezone
from typing import Callable, Dict, Any, List, Optional, Set, Tuple

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.logging_config import get_logger, register_trading_session_logger
from app.core.robot_logging import APILogger
from app.modules.robots.common.mixins import TradePersistenceMixin, PriceParsingMixin
from app.modules.robots.trading.stages.stage2_websocket import Stage2WebSocket
from app.modules.robots.trading.stages.stage3_portfolio import Stage3Portfolio
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage5_signals import Stage5Signals
from app.modules.robots.trading.execution import execution_service_for_session
from app.modules.robots.trading.execution.service import LiveExecutionService
from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots.trading.symbol_guard import SymbolGuard
from app.modules.robots.trading.account_positions_book import (
    apply_trade_to_account_positions as apply_trade_to_book,
    signed_qty as book_signed_qty,
)
from app.modules.robots.trading.broker_position_sync import (
    broker_positions_missing_in_db,
    configured_leverage,
    extract_account_position_meta,
    is_fatal_broker_error,
    is_synthetic_broker_order_id,
)
from app.modules.robots.trading.account_health import (
    DEFAULT_LIQ_DISTANCE_HALT,
    DEFAULT_MM_RATE_HALT,
    DEFAULT_REFRESH_FAIL_HALT,
    evaluate_equity_drawdown_halt,
    evaluate_margin_halt,
    evaluate_refresh_fail_halt,
)
from app.modules.robots.trading.brokers.margin import resolve_margin_params
from app.modules.robots.trading import queries as trading_queries
from app.modules.robots.trading.grain_seed_orchestrator import (
    evaluate_grain_seed_orchestration,
    filter_grain_seed_signals,
)
from app.modules.robots.trading.brokers import (
    BrokerFacade,
    create_broker_facade,
    filter_allowed_instruments,
    normalize_broker_type,
)
from app.modules.robots.trading.brokers.routing import enforce_broker_for_token
from app.modules.robots.trading.brokers.global_websocket import global_websocket_manager
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.costs import resolve_robot_cost_rates, resolve_backtest_execution, TradingCosts
from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.live_events import (
    insert_session_log,
    notify_live_alert,
    notify_live_prices,
    publish_live_event,
    uses_postgres_live_events,
)

# Получаем системный логгер
system_log = get_logger("robots.trading.session")

_GRAIN_ORDER_ACTIVE = frozenset({
    "EXECUTION_REPORT_STATUS_NEW",
    "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
})

_WS_UPTIME_LOG_INTERVAL_SEC = 60


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
            log_func=None,
            mode: ExecutionMode = ExecutionMode.LIVE,
            token_extra_data: Optional[Dict] = None,
            token_type: Optional[int] = None,
    ):
        self.mode = mode
        self.db = db
        self.schema = schema
        self.robot_id = robot_id
        self.user_id = user_id
        self.token_id = token_id
        self.token = token
        self._token_type = int(token_type) if token_type is not None else None
        self._token_extra_data = dict(token_extra_data or {})
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
        self._ws_connected_at: Optional[datetime] = None
        self._ws_last_uptime_log_at: Optional[datetime] = None
        self._last_universe_sync_at: Optional[datetime] = None
        self._last_historical_screening_at: Optional[datetime] = None
        self.running = True

        # Кэши
        self.cached_prices: Dict[str, float] = {}
        self.cached_positions: List[Dict] = []
        self.account_positions: Dict[str, float] = {}
        # figi → {qty, avg_price, mark_price, side} for broker→DB import
        self.account_position_meta: Dict[str, Dict[str, Any]] = {}
        self._daily_trade_counter: Dict[str, int] = {}
        self._last_trade_by_figi: Dict[str, datetime] = {}
        # figi -> order_id: заявка отправлена, ждём FILL/CANCEL/REJECT
        self._in_flight_orders: Dict[str, str] = {}
        self._pending_position_closures: Dict[str, Dict[str, Any]] = {}
        # order_id -> {figi, side, applied_qty} — book mutated only by cumulative fills
        self._order_fill_watches: Dict[str, Dict[str, Any]] = {}
        self._trading_halted: bool = False
        self._trading_halt_reason: str = ""
        self._leverage_synced: bool = False
        # Broker book freshness: fail-closed when refresh fails.
        self._account_book_fresh: bool = False
        self._account_refresh_fail_streak: int = 0
        self._session_start_equity: Optional[float] = None
        self._session_peak_equity: float = 0.0
        self._margin_health: Dict[str, Any] = {}
        # Dirty prices to fan-out to Live UI (same stream as Stage2, throttled).
        self._live_price_dirty: Dict[str, float] = {}
        self._live_price_flush_task: Optional[asyncio.Task] = None
        self._live_price_flush_interval_sec = 0.35

        self._grain_seed_orchestration = None
        self._grain_seed_mismatch_logged = False
        self._grain_seed_force_time_logged = False
        self._grain_seed_streak_block_logged = False
        self._grain_seed_flatten_sent: Set[str] = set()

        self._last_funding_applied: Dict[str, str] = {}

        # BRD-ARCH-03 §7: универсальный RiskManager и §5: PipelineRunner.
        # Создаются лениво при `_update_config`, чтобы не ломать backward-совместимость
        # с grain_seed-веткой. Для стратегий momentum_breakout/reversion_to_ma они
        # будут основным источником риск-проверок.
        self._risk_manager = None
        self._pipeline_runner = None

        # Статистика
        self.stats = {
            "prices_received": 0,
            "signals_generated": 0,
            "orders_placed": 0,
            "errors": 0
        }
        self._cycle_api_counts: Dict[str, int] = {}
        self._session_api_counts: Dict[str, int] = {}

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

        # Backtest: override wall clock and skip sleep between cycles.
        self._clock_override: Optional[Callable[[], datetime]] = None
        self._skip_cycle_sleep = False

    def _now(self) -> datetime:
        if self._clock_override is not None:
            return self._clock_override()
        return datetime.now(timezone.utc)

    @property
    def is_live(self) -> bool:
        return self.mode == ExecutionMode.LIVE

    @property
    def is_backtest(self) -> bool:
        return self.mode == ExecutionMode.BACKTEST

    @property
    def broker(self) -> BrokerFacade:
        """Ленивая инициализация фасада брокера"""
        if self._broker is None:
            self._broker = create_broker_facade(
                self.broker_type,
                self.token,
                token_extra_data=self._token_extra_data,
                robot_config=self.config if isinstance(self.config, dict) else None,
            )
        return self._broker

    def _write_log(self, message: str):
        """Запись в лог (и в файл, и в system_log)"""
        self._session_logger.info(message)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._publish_live_event({
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
            if uses_postgres_live_events():
                event_type = str(payload.get("type") or "").strip().lower()
                if event_type == "log":
                    log_db = SessionLocal()
                    try:
                        insert_session_log(
                            log_db,
                            robot_id=self.robot_id,
                            message=str(payload.get("message") or ""),
                            level=str(payload.get("level") or "INFO"),
                            execution_log_id=self._execution_log_id,
                        )
                    finally:
                        log_db.close()
                return
            await publish_live_event(self.robot_id, payload)
        except Exception:
            pass

    def _queue_live_price_for_ui(self, figi: str, price: float) -> None:
        """Mark a Stage2 tick for Live UI fan-out (throttled batch NOTIFY)."""
        key = str(figi or "").strip().upper()
        try:
            px = float(price)
        except Exception:
            return
        if not key or not (px == px):
            return
        self._live_price_dirty[key] = px
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = self._live_price_flush_task
        if task is None or task.done():
            self._live_price_flush_task = loop.create_task(self._flush_live_prices_loop())

    async def _flush_live_prices_loop(self) -> None:
        """Coalesce dirty ticks and push to Live subscribers (~3 Hz)."""
        try:
            while self.running and self._live_price_dirty:
                await asyncio.sleep(self._live_price_flush_interval_sec)
                batch = self._live_price_dirty
                self._live_price_dirty = {}
                if not batch:
                    continue
                try:
                    notify_live_prices(
                        self.robot_id,
                        [{"figi": k, "price": v} for k, v in batch.items()],
                    )
                except Exception:
                    pass
        finally:
            self._live_price_flush_task = None
            # Final flush if session is stopping with leftovers.
            if self._live_price_dirty:
                batch = self._live_price_dirty
                self._live_price_dirty = {}
                try:
                    notify_live_prices(
                        self.robot_id,
                        [{"figi": k, "price": v} for k, v in batch.items()],
                    )
                except Exception:
                    pass

    async def _ensure_account_id(self) -> Optional[str]:
        """
        Гарантирует account_id для live-сессии.
        Если не задан в конфиге, пытается выбрать из списка счетов брокера.
        """
        if self.account_id:
            return self.account_id
        try:
            self._write_log("🔍 account_id не задан, пытаемся подобрать счет через брокера...")
            accounts = await self.broker.get_accounts()
            if not accounts:
                self._write_log("❌ У брокера не найдено счетов")
                return None

            preferred_statuses = {"open", "ACCOUNT_STATUS_OPEN"}
            preferred_types = {"broker", "ACCOUNT_TYPE_TINKOFF"}

            def _norm(v: Any) -> str:
                return str(v or "").strip()

            chosen = None
            for acc in accounts:
                status = _norm(acc.get("status")).lower()
                acc_type = _norm(acc.get("type")).lower()
                if status in {s.lower() for s in preferred_statuses} and acc_type in {t.lower() for t in preferred_types}:
                    chosen = acc
                    break

            if not chosen:
                for acc in accounts:
                    status = _norm(acc.get("status")).lower()
                    if status in {s.lower() for s in preferred_statuses}:
                        chosen = acc
                        break

            if not chosen:
                chosen = accounts[0]

            candidate = str((chosen or {}).get("id") or "").strip()
            if not candidate:
                self._write_log("❌ Не удалось определить account_id из ответа брокера")
                return None

            self.account_id = candidate
            if isinstance(self.config, dict):
                self.config["account_id"] = candidate
            self._write_log(f"✅ Автоматически выбран счет: {self.account_id}")
            return self.account_id
        except Exception as e:
            self._write_log(f"❌ Ошибка автоподбора account_id: {e}")
            return None

    @staticmethod
    def _to_float_qty(value: Any) -> float:
        if isinstance(value, dict):
            if value.get("decimal") is not None:
                try:
                    return float(value.get("decimal"))
                except Exception:
                    return 0.0
            units = value.get("units")
            nano = value.get("nano")
            try:
                return float(units or 0) + float(nano or 0) / 1_000_000_000.0
            except Exception:
                return 0.0
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    async def _enqueue_portfolio_sync(self) -> None:
        """Поставить portfolio_sync в portfolio lane (не блокировать heavy worker)."""
        if not self.db:
            return
        try:
            from app.core.background_jobs.repository import enqueue_background_job
            from app.core.background_jobs.worker import LANE_PORTFOLIO

            job_id = enqueue_background_job(
                self.db,
                lane=LANE_PORTFOLIO,
                job_type="portfolio_sync",
                payload={
                    "robot_id": self.robot_id,
                    "user_id": self.user_id,
                    "token_id": self.token_id,
                    "token": self.token,
                    "broker_type": self.broker_type,
                    "token_extra_data": self._token_extra_data or {},
                },
                idempotency_key=f"portfolio_sync:{self.robot_id}",
            )
            self.db.commit()
            if job_id:
                self._write_log(f"📋 portfolio_sync поставлен в очередь (job_id={job_id})")
            else:
                self._write_log("📋 portfolio_sync уже в очереди")
        except Exception as e:
            self._write_log(f"⚠️ portfolio_sync enqueue не выполнен: {e}")

    async def _refresh_account_positions(self) -> None:
        """Seed account_positions from broker (signed: long>0, short<0).

        Broker snapshot is authoritative. Live fills adjust the book between
        refreshes; place alone does not. On failure the book is marked stale
        (fail-closed for new orders).
        """
        if not self.account_id:
            self.account_positions = {}
            self.account_position_meta = {}
            self._order_fill_watches.clear()
            self._account_book_fresh = False
            return
        try:
            portfolio_raw = await self.broker.get_portfolio(self.account_id)
            positions = list((portfolio_raw or {}).get("positions") or [])
            # Keep free_funds in sync for Stage6 leverage gate.
            if isinstance(portfolio_raw, dict):
                if not isinstance(self.portfolio, dict):
                    self.portfolio = {}
                try:
                    self.portfolio["free_funds"] = float(portfolio_raw.get("free_funds") or 0)
                except Exception:
                    pass
                total = portfolio_raw.get("total_amount_portfolio")
                if isinstance(total, dict) and total.get("decimal") is not None:
                    try:
                        self.portfolio["total_value"] = float(total.get("decimal") or 0)
                    except Exception:
                        pass
                health = portfolio_raw.get("margin_health")
                if isinstance(health, dict):
                    self._margin_health = dict(health)
                    self.portfolio["margin_health"] = dict(health)
                    eq = float(health.get("equity") or self.portfolio.get("total_value") or 0)
                    if eq > 0:
                        if self._session_start_equity is None:
                            self._session_start_equity = eq
                        self._session_peak_equity = max(float(self._session_peak_equity or 0), eq)
                        self.portfolio["total_value"] = eq
            meta = extract_account_position_meta(positions)
            pos_map: Dict[str, float] = {
                k: float(v.get("qty") or 0.0) for k, v in meta.items()
            }
            self.account_positions.clear()
            self.account_positions.update(pos_map)
            self.account_position_meta = meta
            # Broker snapshot wins — drop in-flight fill watches (would double-count).
            self._order_fill_watches.clear()
            self._account_book_fresh = True
            self._account_refresh_fail_streak = 0
            self._write_log(
                f"📦 account_positions (broker seed): {len(self.account_positions)} "
                f"({', '.join(f'{k}:{v:g}' for k, v in sorted(self.account_positions.items())[:12])}"
                f"{'…' if len(self.account_positions) > 12 else ''})"
            )
            mm = float((self._margin_health or {}).get("account_mm_rate") or 0)
            if mm > 0:
                self._write_log(f"   📉 accountMMRate={mm:.4f}")
        except Exception as e:
            self._account_book_fresh = False
            self._account_refresh_fail_streak = int(self._account_refresh_fail_streak or 0) + 1
            self._write_log(
                f"⚠️ Не удалось обновить позиции счета: {e} "
                f"(fail_streak={self._account_refresh_fail_streak})"
            )

    async def _check_live_account_health(self) -> bool:
        """MMR / equity / refresh-fail gates. Returns False if trading must skip this cycle.

        May set HALT (session stop) on hard breaches.
        """
        if self._trading_halted:
            return False

        risk = self.risk_params if isinstance(self.risk_params, dict) else {}
        mm_halt = float(risk.get("margin_mm_rate_halt") or DEFAULT_MM_RATE_HALT)
        liq_halt = float(risk.get("liq_distance_halt") or DEFAULT_LIQ_DISTANCE_HALT)
        refresh_halt_n = int(risk.get("account_refresh_fail_halt") or DEFAULT_REFRESH_FAIL_HALT)

        halt, reason = evaluate_refresh_fail_halt(
            self._account_refresh_fail_streak,
            halt_after=refresh_halt_n,
        )
        if halt:
            await self._halt_trading(reason)
            return False

        if not self._account_book_fresh:
            self._write_log(
                "⏭️ [HEALTH] Книга позиций устарела — цикл без заявок (fail-closed)"
            )
            return False

        health = dict(self._margin_health or {})
        if health.get("min_liq_distance_pct") is None and self.account_position_meta:
            from app.modules.robots.trading.account_health import min_liq_distance_pct as _min_liq

            rows = [
                {
                    "instrument_type": "crypto_perpetual",
                    "mark_price": meta.get("mark_price"),
                    "liq_price": meta.get("liq_price"),
                }
                for meta in (self.account_position_meta or {}).values()
            ]
            dist = _min_liq(rows)
            if dist is not None:
                health["min_liq_distance_pct"] = dist

        halt, reason = evaluate_margin_halt(
            health,
            mm_rate_halt=mm_halt,
            liq_distance_halt=liq_halt,
        )
        if halt:
            await self._halt_trading(f"margin_health: {reason}")
            return False

        eq = float(
            health.get("equity")
            or (self.portfolio or {}).get("total_value")
            or 0
        )
        max_dd = float(risk.get("max_drawdown_percent") or 0)
        halt, reason = evaluate_equity_drawdown_halt(
            equity=eq,
            peak_equity=float(self._session_peak_equity or 0),
            session_start_equity=float(self._session_start_equity or 0),
            max_drawdown_percent=max_dd,
        )
        if halt:
            await self._halt_trading(f"equity_health: {reason}")
            return False

        return True

    def register_order_fill_watch(
        self,
        *,
        order_id: str,
        figi: str,
        side: str,
    ) -> None:
        """Watch an open order; book updates only when cumulative fill increases."""
        oid = str(order_id or "").strip()
        figi_key = str(figi or "").upper().strip()
        side_u = str(side or "").upper().strip()
        if not oid or not figi_key or side_u not in {"BUY", "SELL"}:
            return
        if oid not in self._order_fill_watches:
            self._order_fill_watches[oid] = {
                "figi": figi_key,
                "side": side_u,
                "applied_qty": 0.0,
            }

    def apply_fill_to_account_positions(
        self,
        *,
        order_id: str,
        filled_qty_total: float,
        figi: Optional[str] = None,
        side: Optional[str] = None,
    ) -> float:
        """Apply incremental fill qty (total cumExec - already applied). Returns new signed book qty."""
        oid = str(order_id or "").strip()
        watch = self._order_fill_watches.get(oid)
        if watch is None:
            figi_key = str(figi or "").upper().strip()
            side_u = str(side or "").upper().strip()
            if not figi_key or side_u not in {"BUY", "SELL"}:
                return 0.0
            watch = {"figi": figi_key, "side": side_u, "applied_qty": 0.0}
            self._order_fill_watches[oid] = watch
        try:
            filled = float(filled_qty_total or 0.0)
        except Exception:
            filled = 0.0
        applied = float(watch.get("applied_qty") or 0.0)
        delta = filled - applied
        if delta <= 1e-12:
            return book_signed_qty(self.account_positions, str(watch.get("figi") or ""))
        new_qty = apply_trade_to_book(
            self.account_positions,
            figi=str(watch.get("figi") or ""),
            side=str(watch.get("side") or ""),
            quantity=delta,
        )
        watch["applied_qty"] = filled
        self._write_log(
            f"📦 account_positions FILL order={oid} "
            f"{watch.get('figi')} {watch.get('side')} +{delta:g} "
            f"(cum={filled:g}) → {new_qty:g}"
        )
        return new_qty

    def clear_order_fill_watch(self, order_id: str) -> None:
        self._order_fill_watches.pop(str(order_id or "").strip(), None)

    # Backward-compatible aliases (old optimistic API → fill watch / no-op revert).
    def apply_trade_to_account_positions(
        self,
        *,
        figi: str,
        side: str,
        quantity: float,
        order_id: Optional[str] = None,
    ) -> float:
        """Deprecated: prefer register_order_fill_watch + apply_fill_to_account_positions."""
        if order_id:
            self.register_order_fill_watch(order_id=str(order_id), figi=figi, side=side)
            return self.apply_fill_to_account_positions(
                order_id=str(order_id),
                filled_qty_total=float(quantity or 0),
                figi=figi,
                side=side,
            )
        new_qty = apply_trade_to_book(
            self.account_positions,
            figi=figi,
            side=side,
            quantity=quantity,
        )
        self._write_log(
            f"📦 account_positions[{str(figi).upper()}] → {new_qty:g} "
            f"({str(side).upper()} {float(quantity or 0):g})"
        )
        return new_qty

    def register_optimistic_account_position_delta(
        self,
        *,
        figi: str,
        side: str,
        quantity: float,
        order_id: str,
    ) -> None:
        """Deprecated alias: register fill watch (quantity ignored until FILL)."""
        _ = quantity
        self.register_order_fill_watch(order_id=order_id, figi=figi, side=side)

    def revert_optimistic_account_position(self, order_id: str) -> None:
        """Deprecated: reject/cancel no longer reverts book (fills already applied stay)."""
        self.clear_order_fill_watch(order_id)

    async def _reconcile_open_positions_with_broker(self) -> None:
        """Закрывает фантомы в БД и импортирует брокерские позиции, которых нет в БД."""
        if not self.db:
            return
        stage4 = Stage4Positions(
            self.db, self.schema, self.broker, self.account_id,
            self.robot_id, self._write_log, cost_params=self.cost_params,
        )
        kept: List[Dict[str, Any]] = []
        closed_n = 0
        for pos in list(self.positions or []):
            figi_key = str(pos.get("figi") or "").upper().strip()
            is_long = str(pos.get("side", "")).lower() in {"buy", "long"}
            broker_qty = float(self.account_positions.get(figi_key, 0.0) or 0.0)
            has_broker = (broker_qty > 0) if is_long else (broker_qty < 0)
            if not has_broker:
                trade_id = pos.get("id")
                if trade_id is not None:
                    try:
                        px = float(
                            (self.cached_prices or {}).get(figi_key)
                            or pos.get("entry_price")
                            or 0
                        )
                        await stage4._close_trade(
                            int(trade_id),
                            exit_price=px,
                            reason="broker_sync_flat",
                            profit=0.0,
                            profit_percent=0.0,
                        )
                        closed_n += 1
                        self._write_log(
                            f"   🧹 [SYNC] БД-позиция {figi_key} ({pos.get('side')}) "
                            f"закрыта: на брокере qty={broker_qty:g}"
                        )
                    except Exception as exc:
                        self._write_log(f"   ⚠️ [SYNC] не удалось закрыть {figi_key} в БД: {exc}")
                        kept.append(pos)
                continue
            # Clamp DB qty to what broker actually holds.
            live_qty = abs(broker_qty)
            try:
                db_qty = float(pos.get("quantity") or 0)
            except Exception:
                db_qty = 0.0
            if live_qty > 0 and db_qty > live_qty + 1e-9:
                pos = dict(pos)
                pos["quantity"] = live_qty
                self._write_log(
                    f"   🔧 [SYNC] {figi_key}: qty БД {db_qty:g} → брокер {live_qty:g}"
                )
            kept.append(pos)
        self.positions = kept
        self.cached_positions = kept
        if closed_n:
            self._write_log(f"   ✅ [SYNC] Закрыто призрачных позиций в БД: {closed_n}")

        # Import broker-only positions (e.g. naked short after phantom long closed).
        to_import = broker_positions_missing_in_db(
            self.account_position_meta or {},
            self.positions,
            fallback_prices=self.cached_prices or {},
            robot_id=int(self.robot_id) if self.robot_id is not None else None,
        )
        if not to_import:
            return
        try:
            ids = await self.save_trades(self.db, self.schema, self.robot_id, to_import)
            for trade, trade_id in zip(to_import, ids):
                row = {
                    "id": trade_id,
                    "figi": trade["figi"],
                    "side": trade["side"],
                    "quantity": trade["quantity"],
                    "entry_price": trade["entry_price"],
                    "status": "open",
                }
                self.positions.append(row)
                self._write_log(
                    f"   📥 [SYNC] Импорт с брокера: {trade['figi']} "
                    f"{trade['side']} qty={trade['quantity']:g} @ {trade['entry_price']:g}"
                )
            self.cached_positions = list(self.positions)
            if ids:
                self._write_log(f"   ✅ [SYNC] Импортировано позиций с брокера: {len(ids)}")
        except Exception as exc:
            self._write_log(f"   ⚠️ [SYNC] импорт позиций с брокера не удался: {exc}")

    async def _halt_trading(self, reason: str) -> None:
        """Stop the live session after fatal broker errors (110007 / 110017)."""
        if self._trading_halted:
            return
        self._trading_halted = True
        self._trading_halt_reason = str(reason or "fatal_broker_error")
        halt_msg = (
            f"🛑 [HALT] {self._trading_halt_reason} — "
            f"новые заявки запрещены, сессия останавливается"
        )
        self._write_log(halt_msg)
        # Persist ERROR log + push Live UI alert (type=error → liveIssue banner).
        alert_text = f"HALT: {self._trading_halt_reason}"
        try:
            await self._publish_live_event({
                "type": "log",
                "level": "ERROR",
                "message": halt_msg,
                "robot_id": self.robot_id,
                "time": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
        try:
            notify_live_alert(self.robot_id, alert_text)
        except Exception:
            pass
        if self.db:
            try:
                query = trading_queries.build_update_robot_status_query().format(schema=self.schema)
                self.db.execute(
                    text(query),
                    {
                        "status": 2,
                        "now": datetime.now(timezone.utc),
                        "robot_id": self.robot_id,
                    },
                )
                self.db.commit()
            except Exception as exc:
                self._write_log(f"   ⚠️ [HALT] не удалось обновить status робота: {exc}")
        self.running = False

    async def _sync_broker_leverage(self) -> None:
        """Push configured leverage to ByBit when margin is enabled (leverage>0)."""
        if self._leverage_synced:
            return
        if normalize_broker_type(self.broker_type) != "bybit":
            self._leverage_synced = True
            return
        lev = configured_leverage(self.config if isinstance(self.config, dict) else {}, self.risk_params)
        margin = resolve_margin_params(self.config if isinstance(self.config, dict) else {})
        if lev <= 0 or not margin.get("enabled"):
            self._write_log(
                f"   ℹ️ leverage={lev:g} — маржинальная торговля выключена, setLeverage не вызываем"
            )
            self._leverage_synced = True
            return
        symbols = [str(x).upper() for x in (self.allowed_figis or []) if str(x).strip()]
        if not symbols:
            self._leverage_synced = True
            return
        ok = 0
        for symbol in symbols[:50]:
            try:
                await self.broker.set_leverage(symbol, lev)
                ok += 1
            except Exception as exc:
                self._write_log(f"   ⚠️ setLeverage {symbol} x{int(lev)}: {exc}")
        self._write_log(f"   ✅ setLeverage x{int(lev)} для {ok}/{len(symbols[:50])} символов")
        self._leverage_synced = True

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

    @staticmethod
    def _categorize_api_call(endpoint: str, request_data: Optional[Dict] = None) -> str:
        ep = (endpoint or "").lower()
        req = request_data or {}
        if "getcandles" in ep:
            return "candles_bootstrap"
        if "marketdatastream" in ep:
            if req.get("action") == "subscribe":
                return "market_stream_subscribe"
            if req.get("type") == "candle_closed":
                return "candles_stream_closed"
            return "market_stream_other"
        if "postorder" in ep or "orderservice" in ep:
            return "orders"
        if "getportfolio" in ep:
            return "portfolio"
        if "getaccounts" in ep:
            return "accounts"
        if "/" in endpoint:
            return endpoint.rsplit("/", 1)[-1]
        return endpoint or "unknown"

    def _reset_cycle_api_counts(self) -> None:
        self._cycle_api_counts = {}

    def _bump_api_call(self, category: str) -> None:
        self._cycle_api_counts[category] = self._cycle_api_counts.get(category, 0) + 1
        self._session_api_counts[category] = self._session_api_counts.get(category, 0) + 1

    @staticmethod
    def _format_api_calls_summary(counts: Dict[str, int]) -> str:
        if not counts:
            return "api_calls: (none)"
        parts = [f"{k}={v}" for k, v in sorted(counts.items())]
        return "api_calls: " + ", ".join(parts)

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
        self._bump_api_call(self._categorize_api_call(endpoint, request_data))
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
        prev_account_id = self.account_id
        self.config = config or {}
        cfg_account_id = (self.config.get("account_id") or "").strip() if isinstance(self.config, dict) else ""
        self.account_id = cfg_account_id or prev_account_id
        if isinstance(self.config, dict) and self.account_id:
            # Не даем refresh_config потерять найденный account_id между циклами.
            self.config["account_id"] = self.account_id
        # Broker is always derived from API token type when known (strict ByBit/T-Invest split).
        broker_from_cfg = enforce_broker_for_token(
            self.config if isinstance(self.config, dict) else {},
            token_type=self._token_type,
            mutate=True,
            require_token=False,
        )
        if broker_from_cfg == "bybit":
            from app.modules.robots.universe import strip_moex_eod_flatten_params

            symbols = list(self.config.get("allowed_symbols") or self.config.get("instruments") or [])
            self.allowed_figis = symbols
            sg = self.config.get("signal_generation") if isinstance(self.config.get("signal_generation"), dict) else {}
            self.strategy_name = str(sg.get("strategy") or self.config.get("strategy") or "reversion_to_ma")
            self.strategy_params = strip_moex_eod_flatten_params(
                dict(sg.get("params") or self.config.get("strategy_params") or {})
            )
            if isinstance(self.config, dict):
                self.config = {
                    **self.config,
                    "strategy_params": dict(self.strategy_params),
                }
                if isinstance(sg, dict):
                    self.config["signal_generation"] = {
                        **sg,
                        "params": dict(self.strategy_params),
                    }
            interval = self.strategy_params.get("interval")
            if interval:
                self.strategy_params["interval"] = str(interval)
            self.update_interval = int(sg.get("update_interval_seconds") or self.config.get("update_interval_seconds") or 10)
        else:
            self.allowed_figis = self.config.get("allowed_figis", [])
            self.strategy_name = self.config.get("strategy", "grain_seed")
            self.strategy_params = self.config.get("strategy_params", {})
            self.update_interval = self.config.get("update_interval_seconds", 10)
        br, tx = resolve_robot_cost_rates(self.config)
        costs_cfg = dict(self.config.get("costs") or {}) if isinstance(self.config.get("costs"), dict) else {}
        self.cost_params = {
            "broker_commission_rate": br,
            "ndfl_rate": tx,
            "maker_fee_rate": float(costs_cfg.get("maker_fee_rate")) if costs_cfg.get("maker_fee_rate") is not None else None,
            "taker_fee_rate": float(costs_cfg.get("taker_fee_rate")) if costs_cfg.get("taker_fee_rate") is not None else None,
            "backtest_execution": resolve_backtest_execution(self.config),
        }
        rp = dict(self.config.get("risk") or {})
        rp["broker_commission"] = br
        rp["ndfl"] = tx
        # ByBit/crypto: do not inherit MOEX session gates unless explicitly enabled.
        if normalize_broker_type(self.config.get("broker_type", "tinvest")) == "bybit":
            rp.setdefault("enforce_session_hours", False)
            rp.setdefault("trading_hours_start", "00:00")
            rp.setdefault("trading_hours_end", "23:59")
            rp.setdefault("allowed_weekdays", 127)
            rp.setdefault("min_hold_seconds", 120)
            rp.setdefault("min_tp_move_bps", 10.0)
            bybit_cfg = self.config.get("bybit") if isinstance(self.config.get("bybit"), dict) else {}
            category = str(bybit_cfg.get("instrument_category") or "linear").strip().lower()
            lev = configured_leverage(self.config, rp)
            margin = resolve_margin_params(self.config)
            rp["max_leverage"] = lev
            rp["instrument_category"] = category
            rp["margin_enabled"] = bool(margin.get("enabled")) or category == "spot"
            cu = self.config.get("crypto_universe") if isinstance(self.config.get("crypto_universe"), dict) else {}
            if cu.get("min_last_price") is not None:
                try:
                    rp["min_last_price"] = float(cu.get("min_last_price"))
                except Exception:
                    pass
            # Re-sync leverage if config changed while session is running.
            self._leverage_synced = False
        else:
            rp.setdefault("enforce_session_hours", True)
        self.risk_params = rp
        self.broker_type = broker_from_cfg
        filtered, dropped = filter_allowed_instruments(self.broker_type, self.allowed_figis or [])
        self.allowed_figis = filtered
        if dropped > 0:
            self._write_log(
                f"   ⚠️ Отфильтрованы инструменты не для {self.broker_type}: {dropped}",
            )

        self._write_log(f"📋 Конфигурация обновлена:")
        self._write_log(f"   Account ID: {self.account_id}")
        n_cfg = len(self.allowed_figis or [])
        if n_cfg <= 12:
            self._write_log(f"   FIGIs (config.allowed): {self.allowed_figis}")
        else:
            preview = list(self.allowed_figis or [])[:8]
            self._write_log(
                f"   FIGIs (config.allowed): {n_cfg} шт. "
                f"[{', '.join(str(x) for x in preview)}…]"
            )
        self._write_log(f"   Strategy: {self.strategy_name}")
        self._write_log(f"   Broker: {self.broker_type}")
        if self.broker_type == "bybit":
            maker = self.cost_params.get("maker_fee_rate")
            taker = self.cost_params.get("taker_fee_rate")
            self._write_log(
                f"   Издержки: maker {float(maker or br):.6f}, taker {float(taker or br):.6f}, "
                f"НДФЛ {tx:.4f}"
            )
            self._write_log(
                f"   Плечо: {float(self.risk_params.get('max_leverage') or 0):g} "
                f"(margin_enabled={bool(self.risk_params.get('margin_enabled'))})"
            )
        else:
            self._write_log(
                f"   Издержки: комиссия {self.cost_params['broker_commission_rate']:.6f}, "
                f"НДФЛ {self.cost_params['ndfl_rate']:.4f}"
            )
        self._write_log(f"   Update interval: {self.update_interval} сек")

        # BRD-ARCH-03 §7: пересоздаём RiskManager при каждом изменении конфигурации,
        # чтобы новые риск-параметры применились сразу. Не используем его для
        # grain_seed-ветки (там старая логика _apply_grain_seed_orchestration),
        # а используем для остальных стратегий (см. parity-задачу в §11).
        try:
            from app.modules.robots.trading.risk import RiskParams, RiskManager
            self._risk_manager = RiskManager(
                RiskParams.from_legacy_dict(self.risk_params),
                commission_rate=br,
                ndfl_rate=tx,
            )
        except Exception as e:
            self._write_log(f"   ⚠️ Не удалось инициализировать RiskManager: {e}")
            self._risk_manager = None

    def _missing_instruments_error(self) -> str:
        if self.broker_type == "bybit":
            return (
                "WS_4005_ANALOG: Robot has no instruments (allowed_symbols empty). "
                "Run crypto screening job or set allowed_symbols in config."
            )
        return "allowed_figis не указан в конфигурации"

    def _ensure_allowed_instruments_or_raise(self) -> None:
        if self.allowed_figis:
            return
        raise Exception(self._missing_instruments_error())

    async def _maybe_refresh_universe_scheduled(self) -> bool:
        """П1/П2 job'ы по config v2 (historical_screening + paper_selection)."""
        if self.broker_type == "bybit":
            from app.modules.robots.service import robot_service
            from app.modules.robots.universe import UNIVERSE_MODE_AUTO, normalize_crypto_universe_mode

            if normalize_crypto_universe_mode(self.config) != UNIVERSE_MODE_AUTO:
                return False
            cu = self.config.get("crypto_universe") if isinstance(self.config.get("crypto_universe"), dict) else {}
            if not bool(cu.get("enabled", True)):
                return False
            refresh = cu.get("refresh") if isinstance(cu.get("refresh"), dict) else {}
            every = int(refresh.get("every_minutes") or 0)
            if every <= 0:
                return False
            now = datetime.now(timezone.utc)
            if self._last_universe_sync_at is None and self.allowed_figis:
                # First live cycle already has symbols — do not block Stage5 on a full screen.
                self._last_universe_sync_at = now
                self._write_log(
                    f"⏭️ [CRYPTO-UNIVERSE] отложен первый screening "
                    f"(есть {len(self.allowed_figis)} symbols, next in {every}m)"
                )
                return False
            if self._last_universe_sync_at is not None:
                elapsed = (now - self._last_universe_sync_at).total_seconds()
                if elapsed < every * 60:
                    return False
            screen_timeout_sec = float(refresh.get("timeout_seconds") or 90)
            self._write_log(
                f"🔄 [CRYPTO-UNIVERSE] screening start (timeout={screen_timeout_sec:.0f}s)..."
            )
            try:
                res = await asyncio.wait_for(
                    robot_service.run_crypto_screening_job(
                        self.db,
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                    ),
                    timeout=screen_timeout_sec,
                )
                self._last_universe_sync_at = now
                accepted = int(res.get("accepted") or len(res.get("symbols") or []))
                if res.get("reused"):
                    self._write_log(
                        f"♻️ [CRYPTO-UNIVERSE] reused fresh screening symbols={accepted}"
                    )
                else:
                    self._write_log(f"✅ [CRYPTO-UNIVERSE] symbols={accepted}")
                row = self.db.execute(
                    text(f"SELECT config FROM {self.schema}.robots WHERE id = :rid"),
                    {"rid": self.robot_id},
                ).first()
                if row and row[0]:
                    self._update_config(row[0])
                return True
            except asyncio.TimeoutError:
                self._last_universe_sync_at = now
                self._write_log(
                    f"⚠️ [CRYPTO-UNIVERSE] screening timeout {screen_timeout_sec:.0f}s — "
                    f"продолжаем торговлю с текущими symbols"
                )
                return False
            except Exception as e:
                self._last_universe_sync_at = now
                self._write_log(f"⚠️ [CRYPTO-UNIVERSE] Ошибка планового job: {e}")
                return False

        from app.modules.robots.config.migration import ensure_config_v2
        from app.modules.robots.universe import UNIVERSE_MODE_FIXED, normalize_universe_mode
        from app.modules.robots.universe_jobs import run_scheduled_universe_jobs

        if not self.db:
            return False
        cfg = ensure_config_v2(self.config or {})
        if normalize_universe_mode(cfg) == UNIVERSE_MODE_FIXED:
            return False

        from app.modules.robots.service import robot_service

        try:
            result = await run_scheduled_universe_jobs(
                self.db,
                robot_service,
                robot_id=self.robot_id,
                user_id=self.user_id,
                config=cfg,
                last_historical_at=getattr(self, "_last_historical_screening_at", None),
                last_paper_at=self._last_universe_sync_at,
            )
        except Exception as e:
            self._write_log(f"⚠️ [UNIVERSE] Ошибка плановых job: {e}")
            return False

        ran = False
        now = datetime.now(timezone.utc)
        hist = result.get("historical")
        if hist and not hist.get("skipped"):
            self._last_historical_screening_at = now
            ran = True
            self._write_log(
                f"✅ [П1] candidate_pool: {hist.get('passed', 0)}/{hist.get('scanned', 0)} тикеров"
            )
            row = self.db.execute(
                text(f"SELECT config FROM {self.schema}.robots WHERE id = :rid"),
                {"rid": self.robot_id},
            ).first()
            if row and row[0]:
                self._update_config(row[0])

        paper = result.get("paper")
        if paper and not paper.get("skipped"):
            self._last_universe_sync_at = now
            ran = True
            figis = list(paper.get("allowed_figis") or [])
            self._write_log(
                f"✅ [П2] tradable_universe: {len(figis)} FIGI, "
                f"ACCEPT={len(paper.get('accepted_tickers') or [])}"
            )
            row = self.db.execute(
                text(f"SELECT config FROM {self.schema}.robots WHERE id = :rid"),
                {"rid": self.robot_id},
            ).first()
            if row and row[0]:
                self._update_config(row[0])

        if not ran:
            legacy_mins = int(cfg.get("universe_refresh_minutes") or 0)
            if legacy_mins > 0 and self._last_universe_sync_at is not None:
                elapsed = (now - self._last_universe_sync_at).total_seconds()
                if elapsed >= legacy_mins * 60:
                    self._write_log(f"🔄 [UNIVERSE] legacy sync ({legacy_mins} мин)...")
                    paper = await robot_service.sync_live_universe_from_pipeline(
                        self.db,
                        self.robot_id,
                        self.user_id,
                        force_refresh_snapshot=True,
                        force_recompute_universe=True,
                    )
                    self._last_universe_sync_at = now
                    ran = True
                    self._write_log(
                        f"✅ [UNIVERSE] {len(paper.get('allowed_figis') or [])} FIGI"
                    )
        return ran

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
                old_strategy_params = dict(self.strategy_params)

                self._update_config(new_config)
                self._ensure_allowed_instruments_or_raise()
                new_figis = set(self.allowed_figis)

                old_interval = old_strategy_params.get("interval")
                new_interval = self.strategy_params.get("interval")
                if self.websocket and (old_figis != new_figis or old_interval != new_interval):
                    if old_figis != new_figis:
                        self._write_log(f"   FIGI изменились: {old_figis} -> {new_figis}")
                    if old_interval != new_interval:
                        self._write_log(f"   Интервал свечей WS: {old_interval} -> {new_interval}")
                    stream_iv = self.strategy_params.get("interval") or "CANDLE_INTERVAL_10_MIN"
                    await self.websocket.subscribe(
                        list(self.allowed_figis), candle_interval=stream_iv
                    )
                if old_figis != new_figis or old_strategy_params != self.strategy_params:
                    await indicator_service.unregister_robot(self.robot_id)
                    await indicator_service.register_robot(self.robot_id, self.broker, self.allowed_figis, self.strategy_params)
                if old_figis != new_figis:
                    added = sorted(new_figis - old_figis)
                    if added:
                        self._write_log(f"📊 [Свечи] Re-bootstrap для новых FIGI: {added}")
                        await indicator_service.bootstrap_candles_at_startup(
                            self.robot_id,
                            self.broker,
                            added,
                            self.strategy_params,
                            log_func=self._write_log,
                            api_log_func=self._log_api_call,
                        )

            if await self._maybe_refresh_universe_scheduled():
                result2 = self.db.execute(
                    text(trading_queries.build_get_robot_config_query().format(schema=self.schema)),
                    {"robot_id": self.robot_id},
                ).first()
                if result2 and result2[0]:
                    old_figis = set(self.allowed_figis)
                    old_strategy_params = dict(self.strategy_params)
                    self._update_config(result2[0])
                    self._ensure_allowed_instruments_or_raise()
                    new_figis = set(self.allowed_figis)
                    old_interval = old_strategy_params.get("interval")
                    new_interval = self.strategy_params.get("interval")
                    if self.websocket and (old_figis != new_figis or old_interval != new_interval):
                        if old_figis != new_figis:
                            self._write_log(f"   FIGI после universe sync: {old_figis} -> {new_figis}")
                        stream_iv = self.strategy_params.get("interval") or "CANDLE_INTERVAL_10_MIN"
                        await self.websocket.subscribe(
                            list(self.allowed_figis), candle_interval=stream_iv
                        )
                    if old_figis != new_figis or old_strategy_params != self.strategy_params:
                        await indicator_service.unregister_robot(self.robot_id)
                        await indicator_service.register_robot(
                            self.robot_id, self.broker, self.allowed_figis, self.strategy_params
                        )
                    if old_figis != new_figis:
                        added = sorted(new_figis - old_figis)
                        if added:
                            self._write_log(f"📊 [Свечи] Re-bootstrap после universe sync: {added}")
                            await indicator_service.bootstrap_candles_at_startup(
                                self.robot_id,
                                self.broker,
                                added,
                                self.strategy_params,
                                log_func=self._write_log,
                                api_log_func=self._log_api_call,
                            )

            self.db.commit()

        except Exception as e:
            self._write_log(f"   ❌ Ошибка обновления конфига: {e}")
            if self.db:
                self.db.rollback()

    # ============================================================
    # WebSocket поток
    # ============================================================

    def _format_ws_candle_log(self, figi: str, candle: Dict[str, Any]) -> Optional[str]:
        """OHLC закрытой свечи из WS (min/max = low/high бара)."""
        o = self.parse_price(candle.get("open"))
        h = self.parse_price(candle.get("high"))
        low = self.parse_price(candle.get("low"))
        c = self.parse_price(candle.get("close"))
        if o is None and h is None and low is None and c is None:
            return None
        parts = []
        if o is not None:
            parts.append(f"O={o:.4f}")
        if h is not None:
            parts.append(f"H={h:.4f}")
        if low is not None:
            parts.append(f"L={low:.4f}")
        if c is not None:
            parts.append(f"C={c:.4f}")
        body = " ".join(parts)
        range_part = ""
        if low is not None and h is not None:
            range_part = f" (min={low:.4f} max={h:.4f})"
        time_part = candle.get("time") or ""
        time_suffix = f" t={time_part}" if time_part else ""
        return f"🕯️ [WS] {figi} {body}{range_part}{time_suffix}"

    async def _log_ws_uptime(self, *, force: bool = False) -> None:
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._ws_last_uptime_log_at is not None
            and (now - self._ws_last_uptime_log_at).total_seconds() < _WS_UPTIME_LOG_INTERVAL_SEC
        ):
            return

        parts: List[str] = []
        if self._ws_connected_at is not None:
            session_sec = (now - self._ws_connected_at).total_seconds()
            parts.append(f"робот {session_sec:.0f}с")
        global_sec = await global_websocket_manager.get_uptime_seconds(
            self.user_id, self.token, self.broker_type
        )
        if global_sec is not None:
            parts.append(f"глобальный WS {global_sec:.0f}с")
        if parts:
            self._write_log(f"⏱️ [WS] Соединение открыто: {', '.join(parts)}")
        self._ws_last_uptime_log_at = now

    def _log_ws_disconnect_duration(self) -> None:
        if self._ws_connected_at is None:
            return
        sec = (datetime.now(timezone.utc) - self._ws_connected_at).total_seconds()
        self._write_log(f"⏱️ [WS] Соединение закрыто, работало {sec:.0f}с")
        self._ws_connected_at = None
        self._ws_last_uptime_log_at = None

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
                self._ws_connected_at = datetime.now(timezone.utc)
                self._ws_last_uptime_log_at = None
                self._write_log("✅ [WS] WebSocket подключен")
                await self._log_ws_uptime(force=True)

                stream_interval = (
                    self.strategy_params.get("interval")
                    or "CANDLE_INTERVAL_10_MIN"
                )
                sub_res = await self.websocket.subscribe(self.allowed_figis, candle_interval=stream_interval)
                await self._log_api_call(
                    endpoint="tinkoff.public.invest.api.contract.v1.MarketDataStreamService/MarketDataStream",
                    request_data={
                        "action": "subscribe",
                        "figis": list(self.allowed_figis),
                        "candle_interval": stream_interval,
                    },
                    response_data={"statuses": sub_res},
                    response_status=200,
                )

                consecutive_errors = 0
                empty_event_polls = 0
                while self.running and self.websocket_connected:
                    try:
                        events = await self.websocket.receive_events(duration_seconds=2)

                        if not events:
                            empty_event_polls += 1
                            if empty_event_polls >= 15:
                                self._write_log(
                                    "⚠️ [WS] Нет market events 30 сек — принудительная переподписка..."
                                )
                                resub_ok = await self.broker.force_resubscribe_websocket(
                                    self.user_id
                                )
                                if resub_ok:
                                    self._write_log("✅ [WS] Переподписка на lastPrice/candles отправлена")
                                else:
                                    self._write_log(
                                        "❌ [WS] Переподписка не выполнена (нет соединения или подписчиков)"
                                    )
                                empty_event_polls = 0
                        else:
                            empty_event_polls = 0

                        if events:
                            for ev in events:
                                ev_type = ev.get("type")
                                figi = ev.get("figi")
                                if not figi:
                                    continue

                                if ev_type == "price":
                                    price = ev.get("price")
                                    if price is not None:
                                        self.cached_prices[figi] = float(price)
                                        await self._put_to_queue_with_limit(
                                            self.price_queue,
                                            {
                                                "type": "price",
                                                "figi": figi,
                                                "price": float(price),
                                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                            },
                                        )
                                        self._queue_live_price_for_ui(str(figi), float(price))
                                        self.stats["prices_received"] += 1

                                elif ev_type == "candle_closed":
                                    candle = ev.get("candle") or {}
                                    price = ev.get("price")
                                    if price is not None:
                                        self.cached_prices[figi] = float(price)
                                        self._queue_live_price_for_ui(str(figi), float(price))

                                    candle_log = self._format_ws_candle_log(figi, candle)
                                    if candle_log:
                                        self._write_log(candle_log)

                                    await indicator_service.on_closed_candle(
                                        self.robot_id,
                                        self.broker,
                                        figi,
                                        candle,
                                        self.strategy_params,
                                        api_log_func=self._log_api_call,
                                    )

                                    await self._put_to_queue_with_limit(
                                        self.price_queue,
                                        {
                                            "type": "candle_closed",
                                            "figi": figi,
                                            "candle": candle,
                                            "price": price,
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                        },
                                    )
                                    self.stats["prices_received"] += 1

                            self._write_log(
                                f"📡 [WS] Events={len(events)} (очередь: {self.price_queue.qsize()})"
                            )
                            await self._log_ws_uptime()

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
                self._log_ws_disconnect_duration()
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

    def _is_robot_enabled_in_db(self) -> bool:
        """True while robots.status == 1. Missing row / DB error → keep running (fail-open)."""
        if not self.db or not self.robot_id:
            return True
        try:
            query = trading_queries.build_get_robot_status_query().format(schema=self.schema)
            row = self.db.execute(text(query), {"robot_id": self.robot_id}).first()
            if not row:
                return False
            return int(row[0] or 0) == 1
        except Exception as exc:
            self._write_log(f"   ⚠️ не удалось прочитать status робота: {exc}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return True

    def _request_stop_from_db_signal(self, reason: str) -> None:
        if not self.running:
            return
        self._write_log(f"🛑 [TRADE] Стоп по сигналу БД: {reason}")
        self.running = False

    async def _run_single_trading_cycle(self, cycle_count: int) -> None:
        """Один торговый цикл — делегат в trading.core (BRD-ARCH-04)."""
        from app.modules.robots.trading.core.trading_core import run_single_trading_cycle

        if not self._is_robot_enabled_in_db():
            self._request_stop_from_db_signal("robots.status != 1 (выключен)")
            return

        await run_single_trading_cycle(self, cycle_count)

    async def _trading_worker(self):
        """Торговый поток: генерирует сигналы и выставляет заявки"""
        self._write_log("💰 [TRADE] Запуск торгового потока")

        await self._update_portfolio()

        cycle_count = 0

        while self.running:
            try:
                if not self._is_robot_enabled_in_db():
                    self._request_stop_from_db_signal("robots.status != 1 (выключен)")
                    break

                cycle_count += 1
                await self._run_single_trading_cycle(cycle_count)
                if not self.running:
                    break
                if self._cycle_id:
                    api_summary = self._format_api_calls_summary(self._cycle_api_counts)
                    self._write_log(f"📡 [TRADE] {api_summary}")
                    await self.complete_run_cycle(
                        self.db,
                        self.schema,
                        self._cycle_id,
                        status="completed",
                        context={"api_calls": dict(self._cycle_api_counts)},
                    )
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
                if self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass
                if self._cycle_id:
                    await self.complete_run_cycle(
                        self.db,
                        self.schema,
                        self._cycle_id,
                        status="failed",
                        context={
                            "error": str(e),
                            "api_calls": dict(self._cycle_api_counts),
                        },
                    )
                    self._cycle_id = None
                await asyncio.sleep(5)

        self._write_log("🛑 [TRADE] Торговый поток остановлен")

    async def _get_latest_prices_from_queue(self) -> Dict[str, float]:
        """Забирает последние цены из очереди"""
        prices = {}

        while not self.price_queue.empty():
            try:
                item = self.price_queue.get_nowait()
                if item.get("type") in ("price", "candle_closed"):
                    figi = item.get("figi")
                    price = item.get("price")
                    if figi and price is not None:
                        prices[figi] = float(price)
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
        dedup_order_ids = list(dict.fromkeys([
            oid for oid in order_ids
            if oid and not is_synthetic_broker_order_id(oid)
        ]))
        if not dedup_order_ids:
            return

        execution = execution_service_for_session(self)

        for order_id in dedup_order_ids:
            state = await execution.poll_order_status(order_id)
            execution_status = state.get("status", "UNKNOWN")
            self._write_log(f"📋 [TRADE] Статус заявки: {order_id} -> {execution_status}")
            is_closing = order_id in self._pending_position_closures
            if self.db:
                await self.update_trade_status(
                    self.db, self.schema,
                    order_id,
                    execution_status,
                    executed_price=state.get("executed_price"),
                    filled_quantity=state.get("lots_executed"),
                    commission=state.get("commission"),
                    closing=is_closing,
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
                "status": LiveExecutionService.map_execution_status_to_trade_status(
                    str(execution_status), closing=is_closing
                ),
                "execution_status": execution_status,
                "filled_quantity": state.get("lots_executed"),
                "time": datetime.now(timezone.utc).isoformat(),
            })

            if execution_status in {
                "EXECUTION_REPORT_STATUS_FILL",
                "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
            }:
                side_hint = state.get("side")
                figi_hint = state.get("figi") or state.get("symbol")
                # Normalize ByBit side Buy/Sell → BUY/SELL
                if side_hint:
                    s = str(side_hint).upper()
                    if s in {"BUY", "ORDER_DIRECTION_BUY"}:
                        side_hint = "BUY"
                    elif s in {"SELL", "ORDER_DIRECTION_SELL"}:
                        side_hint = "SELL"
                filled_total = float(state.get("lots_executed") or 0)
                # First poll without a place-time watch (e.g. after broker refresh):
                # seed watermark to current cumExec so we do not double-apply into seeded book.
                oid_s = str(order_id)
                if oid_s not in self._order_fill_watches:
                    if side_hint and figi_hint:
                        self.register_order_fill_watch(
                            order_id=oid_s,
                            figi=str(figi_hint),
                            side=str(side_hint),
                        )
                        self._order_fill_watches[oid_s]["applied_qty"] = float(filled_total or 0)
                elif filled_total > 0:
                    self.apply_fill_to_account_positions(
                        order_id=oid_s,
                        filled_qty_total=filled_total,
                        figi=str(figi_hint) if figi_hint else None,
                        side=str(side_hint) if side_hint else None,
                    )

            if execution_status == "EXECUTION_REPORT_STATUS_FILL":
                pending_close = self._pending_position_closures.pop(order_id, None)
                if pending_close:
                    await self._finalize_position_close(pending_close)
                self.clear_order_fill_watch(str(order_id))
            elif execution_status in {
                "EXECUTION_REPORT_STATUS_CANCELLED",
                "EXECUTION_REPORT_STATUS_REJECTED",
            }:
                # Unfilled remainder never touched the book; clear watch only.
                self.clear_order_fill_watch(str(order_id))
                self._pending_position_closures.pop(order_id, None)
            if execution_status in {
                "EXECUTION_REPORT_STATUS_FILL",
                "EXECUTION_REPORT_STATUS_CANCELLED",
                "EXECUTION_REPORT_STATUS_REJECTED",
            }:
                self._clear_in_flight_order(order_id=str(order_id))

    def _clear_in_flight_order(self, *, order_id: Optional[str] = None, figi: Optional[str] = None) -> None:
        if order_id:
            oid = str(order_id)
            for key in [k for k, v in self._in_flight_orders.items() if str(v) == oid]:
                self._in_flight_orders.pop(key, None)
        if figi:
            self._in_flight_orders.pop(str(figi).upper(), None)

    def _hydrate_in_flight_orders_from_db(self) -> None:
        """Восстановить незакрытые заявки после рестарта сессии."""
        if not self.db:
            return
        query = f"""
            SELECT figi, order_id
            FROM {self.schema}.robot_trades
            WHERE robot_id = :robot_id
              AND order_id IS NOT NULL
              AND status IN ('open', 'pending', 'partial')
            ORDER BY created_at DESC
            LIMIT 200
        """
        try:
            rows = self.db.execute(text(query), {"robot_id": self.robot_id}).fetchall()
            restored: Dict[str, str] = {}
            for row in rows or []:
                figi = str(row[0] or "").upper().strip()
                oid = str(row[1] or "").strip()
                # Position seeds are not exchange orders — never block Stage5/6.
                if is_synthetic_broker_order_id(oid):
                    continue
                if figi and oid and figi not in restored:
                    restored[figi] = oid
            self._in_flight_orders = restored
            if restored:
                self._write_log(
                    f"⏳ [TRADE] Заявки в исполнении: {len(restored)} — {', '.join(sorted(restored.keys())[:12])}"
                    + ("…" if len(restored) > 12 else "")
                )
        except Exception as exc:
            self._write_log(f"⚠️ [TRADE] Не удалось восстановить in-flight заявки: {exc}")

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
            return [
                r[0] for r in rows
                if r and r[0] and not is_synthetic_broker_order_id(r[0])
            ]
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
        execution_log_started = False

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
            # Логируем каждый запуск сессии до любых ранних проверок.
            await self._create_execution_log()
            execution_log_started = self._execution_log_id is not None

            await self._ensure_account_id()
            if not self.account_id:
                raise Exception("account_id не указан в конфигурации")
            await self._enqueue_portfolio_sync()
            await self._refresh_account_positions()
            await self._sync_broker_leverage()
            self._ensure_allowed_instruments_or_raise()
            self._hydrate_in_flight_orders_from_db()

            await indicator_service.register_robot(self.robot_id, self.broker, self.allowed_figis, self.strategy_params)
            await indicator_service.bootstrap_candles_at_startup(
                self.robot_id,
                self.broker,
                self.allowed_figis,
                self.strategy_params,
                log_func=self._write_log,
                api_log_func=self._log_api_call,
            )

            websocket_task = asyncio.create_task(self._websocket_worker())
            trading_task = asyncio.create_task(self._trading_worker())

            await asyncio.gather(websocket_task, trading_task)

        except asyncio.CancelledError:
            self._write_log("⏹️ Сессия отменена")
            self.stats["errors"] += 1
        except Exception as e:
            self._write_log(f"❌ Критическая ошибка: {e}")
            import traceback
            self._write_log(traceback.format_exc())
            self.stats["errors"] += 1
        finally:
            self.running = False
            await indicator_service.unregister_robot(self.robot_id)
            await self.broker.close()
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.stats["execution_time"] = execution_time * 1000
            if execution_log_started:
                api_summary = self._format_api_calls_summary(self._session_api_counts)
                await self._complete_execution_log(
                    status=1 if self.stats["errors"] == 0 else 2,
                    message=(
                        f"Completed. Signals: {self.stats['signals_generated']}, "
                        f"Trades: {self.stats['orders_placed']}. {api_summary}"
                    ),
                    execution_time_ms=int(self.stats.get("execution_time", 0)),
                )
            self._api_logger = None
            if self._own_db and self.db:
                self.db.close()

        self._write_log("=" * 60)
        self._write_log(f"✅ СЕССИЯ ЗАВЕРШЕНА")
        self._write_log(f"   Время работы: {execution_time:.1f} сек")
        self._write_log(f"   📊 Статистика:")
        self._write_log(f"      Цен получено: {self.stats['prices_received']}")
        self._write_log(f"      Сигналов: {self.stats['signals_generated']}")
        self._write_log(f"      Заявок: {self.stats['orders_placed']}")
        self._write_log(f"      Ошибок: {self.stats['errors']}")
        self._write_log(f"      {self._format_api_calls_summary(self._session_api_counts)}")
        self._write_log("=" * 60)

        return {
            "status": "success" if self.stats["errors"] == 0 else "partial",
            "duration_seconds": execution_time,
            "stats": self.stats,
            "api_calls": dict(self._session_api_counts),
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
            now_utc=self._now(),
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

            # Register for FILL-based book update (no optimistic patch on place).
            if order_id:
                self.register_order_fill_watch(
                    order_id=str(order_id),
                    figi=figi,
                    side=close_side.upper(),
                )
                await self._put_to_queue_with_limit(
                    self.order_queue,
                    {
                        "type": "order_status",
                        "order_id": order_id,
                        "status": order_status,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            is_buy_close = close_side == "buy"
            costs_close = TradingCosts(px, qty, is_buy=is_buy_close, **cost_kw)
            commission = costs_close.calculate_commission()
            db_status = LiveExecutionService.map_execution_status_to_trade_status(str(order_status))

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

    async def _plan_exit_intents(self, prices: Dict[str, float]) -> List[OrderIntent]:
        """Stage4 decision-only: SL/TP → OrderIntent (no post_order)."""
        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для проверки стоп-лоссов")
            return []

        self._write_log("🔴 [TRADE] Планирование SL/TP exits...")
        try:
            guard = self.symbol_guard()
            stage4 = Stage4Positions(
                self.db, self.schema, self.broker, self.account_id,
                self.robot_id, self._write_log, cost_params=self.cost_params,
            )
            intents = await stage4.plan_stop_loss_take_profit(
                self.positions or [],
                prices,
                self.risk_params,
                pending_close_figis=guard.blocked_figis(),
                guard=guard,
                account_positions=self.account_positions,
            )
            if intents:
                self._write_log(f"   Exit intents: {len(intents)}")
            return intents
        except Exception as e:
            self._write_log(f"   ❌ Ошибка планирования стоп-лоссов: {e}")
            return []

    async def _check_stop_loss(self, prices: Dict[str, float]) -> List[OrderIntent]:
        """Backward-compatible alias for _plan_exit_intents."""
        return await self._plan_exit_intents(prices)

    def symbol_guard(self) -> SymbolGuard:
        return SymbolGuard(
            in_flight_orders=self._in_flight_orders,
            pending_position_closures=self._pending_position_closures,
            broker=self.broker,
            account_id=self.account_id or "",
            log_func=self._write_log,
        )

    async def _apply_live_funding_if_due(self, prices: Dict[str, float]) -> None:
        """ByBit funding accrual for open positions (aligns live with backtest)."""
        if self.broker_type != "bybit":
            return
        costs = self.config.get("costs") if isinstance(self.config.get("costs"), dict) else {}
        if not bool(costs.get("funding_rate_enabled")):
            return
        bybit_cfg = self.config.get("bybit") if isinstance(self.config.get("bybit"), dict) else {}
        category = str(bybit_cfg.get("instrument_category") or "linear").strip().lower()
        if category == "spot":
            return
        positions = list(self.positions or [])
        if not positions:
            return

        from app.modules.bybit.funding import fetch_funding_rate

        testnet = bool(bybit_cfg.get("testnet", True))
        now = self._now()
        for pos in positions:
            symbol = str(pos.get("figi") or pos.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            qty = float(pos.get("quantity") or 0)
            if qty <= 0:
                continue
            try:
                fr = await fetch_funding_rate(
                    symbol=symbol,
                    instrument_category=category,
                    testnet=testnet,
                )
            except Exception as ex:
                self._write_log(f"   ⚠️ funding rate fetch failed {symbol}: {ex}")
                continue
            nft = fr.next_funding_time
            if nft is None or now < nft:
                continue
            ft_key = nft.astimezone(timezone.utc).isoformat()
            dedupe_key = f"{symbol}:{ft_key}"
            if self._last_funding_applied.get(symbol) == ft_key:
                continue
            px = float(prices.get(symbol) or pos.get("entry_price") or 0)
            if px <= 0:
                continue
            notional = qty * px
            side = str(pos.get("side") or "buy").lower()
            direction = -1.0 if side in ("buy", "long") else 1.0
            rate = float(fr.funding_rate or 0)
            adjustment = notional * rate * direction
            self._last_funding_applied[symbol] = ft_key
            if self.portfolio:
                self.portfolio["total_value"] = float(self.portfolio.get("total_value", 0) or 0) + adjustment
                self.portfolio["free_funds"] = float(self.portfolio.get("free_funds", 0) or 0) + adjustment
            self._write_log(
                f"   💸 funding {symbol}: rate={rate:.6f} notional={notional:.2f} adj={adjustment:.2f}"
            )
            if self.db:
                await self.save_order_event(
                    self.db,
                    self.schema,
                    self.robot_id,
                    order_id=None,
                    status="applied",
                    event_type="funding",
                    payload={
                        "symbol": symbol,
                        "funding_rate": rate,
                        "notional": notional,
                        "cash_adjustment": adjustment,
                        "funding_time": ft_key,
                        "instrument_category": category,
                    },
                )
                await self.save_decision(
                    self.db,
                    self.schema,
                    self.robot_id,
                    stage="funding",
                    decision_type="funding_charge",
                    decision="applied",
                    reason_code=None,
                    payload={
                        "symbol": symbol,
                        "funding_rate": rate,
                        "cash_adjustment": adjustment,
                    },
                    execution_log_id=self._execution_log_id,
                    cycle_id=self._cycle_id,
                    figi=symbol,
                )

    async def _is_daily_loss_limit_breached(self) -> bool:
        if not self.db:
            return False
        max_daily_loss = float(self.risk_params.get("max_daily_loss", 0) or 0)
        if max_daily_loss <= 0:
            return False
        total_value = float((self.portfolio or {}).get("total_value", 0) or 0)
        if total_value <= 0:
            return False
        day_start = self._now().replace(hour=0, minute=0, second=0, microsecond=0)
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

    async def _resolve_stage5_figis(self) -> List[str]:
        """Stage5 universe = accepted today ∪ open positions (not full config.allowed_*)."""
        from app.modules.robots.trading.brokers.routing import (
            filter_allowed_instruments,
            normalize_broker_type,
        )
        from app.modules.robots.trading.stage5_universe import (
            collect_open_position_symbols,
            load_today_accepted_symbols,
            merge_stage5_figis,
        )

        broker = normalize_broker_type(self.broker_type or "tinvest")
        is_crypto = broker == "bybit"
        accepted: List[str] = []
        if self.db and self.robot_id:
            try:
                im = (
                    self.config.get("instrument_map")
                    if isinstance(self.config, dict) and isinstance(self.config.get("instrument_map"), dict)
                    else {}
                )
                figi_by_ticker = (
                    im.get("figi_by_ticker") if isinstance(im.get("figi_by_ticker"), dict) else {}
                )
                accepted = load_today_accepted_symbols(
                    self.db,
                    self.schema,
                    int(self.robot_id),
                    is_crypto=is_crypto,
                    figi_by_ticker=figi_by_ticker,
                )
            except Exception as exc:
                self._write_log(f"   ⚠️ [STAGE5] не удалось загрузить accepted сегодня: {exc}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        open_syms = collect_open_position_symbols(
            self.positions,
            self.account_position_meta,
        )
        merged = merge_stage5_figis(accepted, open_syms)
        filtered, _dropped = filter_allowed_instruments(broker, merged)
        config_n = len(self.allowed_figis or [])
        self._write_log(
            f"🎯 [STAGE5] universe={len(filtered)} "
            f"(accepted_today={len(accepted)}, positions={len(open_syms)}, "
            f"config_allowed={config_n})"
        )
        if filtered:
            preview = ", ".join(filtered[:12])
            self._write_log(
                f"   STAGE5 symbols: {preview}{'…' if len(filtered) > 12 else ''}"
            )
        elif config_n:
            self._write_log(
                "   ⚠️ [STAGE5] пустой периметр (нет accepted сегодня и позиций) — "
                "сигналы не считаем по config.allowed_*"
            )
        return filtered

    async def _generate_signals(self, prices: Dict[str, float]) -> List[Dict]:
        """Генерирует сигналы через Stage5Signals"""
        self._write_log("🎯 [TRADE] Генерация сигналов...")

        stage5 = Stage5Signals(self.broker, self._write_log)

        # Функция для логирования API вызовов
        async def log_api_call_wrapper(**kwargs):
            await self._log_api_call(**kwargs)

        figis = await self._resolve_stage5_figis()
        if not figis:
            return []

        signals = await stage5.generate_signals(
            figis=figis,
            strategy_name=self.strategy_name,
            strategy_params=self.strategy_params,
            risk_params=self.risk_params,
            portfolio_value=self.portfolio.get("total_value", 0) if self.portfolio else 0,
            free_funds=self.portfolio.get("free_funds", 0) if self.portfolio else 0,
            open_positions=self.positions or [],
            account_positions=self.account_positions,
            robot_id=self.robot_id,
            current_prices=prices,
            log_api_call_func=log_api_call_wrapper,
            token_id=self.token_id,
            user_id=self.user_id,
            pending_order_figis=self.symbol_guard().blocked_figis(),
        )

        return signals

    async def _execute_intents(self, intents: List[OrderIntent]) -> List[Dict]:
        """Единая точка place: LiveExecutionService.submit_intents."""
        if not intents:
            return []

        if not self.db:
            self._write_log("⚠️ [TRADE] Нет БД для сохранения заявок")
            return []

        if self._trading_halted:
            self._write_log(
                f"🛑 [TRADE] HALT активен ({self._trading_halt_reason}) — заявки не выставляем"
            )
            return []

        self._write_log(f"📊 [TRADE] Выставление заявок (intents={len(intents)})...")
        risk_params = dict(self.risk_params or {})
        if isinstance(self.portfolio, dict):
            risk_params["free_funds"] = float(self.portfolio.get("free_funds", 0) or 0)
        execution = execution_service_for_session(self)
        trades = await execution.submit_intents(intents, risk_params=risk_params)
        execution.sync_counters_from_stage()
        skipped = [t for t in trades if t.get("status") == "skipped"]
        if skipped:
            reasons: Dict[str, int] = {}
            for trade in skipped:
                reason = trade.get("error", "UNKNOWN")
                reasons[reason] = reasons.get(reason, 0) + 1
            self._write_log(f"⚠️ [TRADE] Пропущено сделок: {len(skipped)}; причины: {reasons}")

        for trade in trades:
            if trade.get("fatal_broker_error") or is_fatal_broker_error(trade.get("error")):
                await self._halt_trading(
                    f"fatal broker error on {trade.get('figi')}: {trade.get('error')}"
                )
                break
            oid = trade.get("order_id")
            status = str(trade.get("status") or "")
            if oid and status not in {"skipped", "failed"}:
                # Place does not mutate book — watch fills instead.
                self.register_order_fill_watch(
                    order_id=str(oid),
                    figi=str(trade.get("figi") or ""),
                    side=str(trade.get("side") or "").upper(),
                )
                await self._put_to_queue_with_limit(
                    self.order_queue,
                    {
                        "type": "order_status",
                        "order_id": trade["order_id"],
                        "status": trade.get("execution_status", trade["status"]),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

        return trades

    async def _execute_orders(self, signals: List[Dict]) -> List[Dict]:
        """Выставляет заявки из strategy signals (через OrderIntent)."""
        if not signals:
            return []
        intents = [OrderIntent.from_strategy_signal(s) for s in signals]
        return await self._execute_intents(intents)
