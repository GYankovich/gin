"""Async trading session for robots v2 (paper + live + scalper ticks)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.database import SessionLocal
from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.broker_factory import (
    create_broker_from_token,
    load_token_account_id,
    persist_token_account_id,
    resolve_account_id,
    resolve_ticker_instrument_map,
)
from app.modules.robots_v2.engine.cycle import run_trading_cycle
from app.modules.robots_v2.engine.audit import (
    AuditCycleBundle,
    AuditDecisionRow,
    audit_end_session,
    audit_persist_cycle,
    audit_start_session,
)
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.execution import ExecutionService, attach_ticker_warnings
from app.modules.robots_v2.engine.market_data import (
    fetch_prices_for_session,
    merge_ws_and_rest_prices,
    poll_interval_seconds,
)
from app.modules.robots_v2.engine.order_flow import OrderFlowAggregator
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.reconcile import reconcile_from_broker
from app.modules.robots_v2.engine.scan_helpers import build_session_skip_scan
from app.modules.robots_v2.engine.session_log import SessionActionLogger, log_external_api
from app.modules.robots_v2.engine.types import (
    CYCLE_STAGE_LABELS,
    SessionState,
    SessionStatus,
    cycle_stage_progress,
)
from app.modules.robots_v2.risk.adapter import enrich_positions_with_exit_prices
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.risk.eod import is_within_trading_session, should_eod_flatten, trade_date_msk
from app.modules.robots_v2.universe.service import universe_service
from app.modules.robots_v2.universe.token_context import load_token_context

logger = logging.getLogger(__name__)

SCALPER_TICK_MIN_INTERVAL_SEC = 0.5
SCALPER_WS_TICK_MIN_INTERVAL_SEC = 0.5
POSITIONS_WS_MIN_INTERVAL_SEC = 0.4
WS_SILENCE_RESUBSCRIBE_SEC = 30.0
WS_SILENCE_REST_FALLBACK_SEC = 45.0
EQUITY_CURVE_MAX_POINTS = 500
UNIVERSE_RETRY_SEC = 30.0
UNIVERSE_POLL_REFRESH_SEC = 300.0
UNIVERSE_FORCE_MIN_INTERVAL_SEC = 15.0
STOP_JOIN_SEC = 8.0
STOP_CANCEL_JOIN_SEC = 5.0
FINALIZE_AUDIT_SEC = 8.0


def _flatten_all_positions(ledger: PaperLedger, prices: dict[str, float]) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []
    for t, pos in list(ledger.positions.items()):
        px = prices.get(t, pos.avg_entry_price)
        pnl = ledger.apply_fill(
            ticker=t,
            side="SELL" if pos.is_long else "BUY",
            quantity=pos.quantity,
            price=px,
            reduce_only=True,
        )
        fills.append({"ticker": t, "kind": "flatten", "pnl": pnl, "price": px})
    return fills


class TradingSessionV2:
    def __init__(
        self,
        *,
        robot_id: int,
        user_id: int,
        token_id: int,
        config: dict[str, Any],
        virtual_capital: float,
        stop_mode: str = "soft",
    ) -> None:
        self.robot_id = robot_id
        self.user_id = user_id
        self.token_id = token_id
        self.raw_config = config
        self.virtual_capital = virtual_capital
        self.stop_mode = stop_mode
        self.state = SessionState.BOOTSTRAP
        self.cycle_number = 0
        self.universe: list[str] = []
        self.ledger: PaperLedger | None = None
        self.risk: RiskEngine | None = None
        self.execution: ExecutionService | None = None
        self.order_flow = OrderFlowAggregator(window_sec=30)
        self.candle_history: dict[str, list[Candle]] = {}
        self.last_prices: dict[str, float] = {}
        self.last_prices_at: datetime | None = None
        self.last_cycle_at: datetime | None = None
        self.last_decisions: list[dict[str, Any]] = []
        self.ws_healthy = True
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._scalper_task: asyncio.Task | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws_queue: asyncio.Queue | None = None
        self._broker = None
        self._instrument_map: dict[str, str] = {}
        self._ticker_by_instrument: dict[str, str] = {}
        self._parsed: TradingRobotConfigV4 | None = None
        self._eod_done = False
        self._allow_short = False
        self._market = "moex"
        self._cycle_lock = asyncio.Lock()
        self._last_scalper_ws_tick_at: float = 0.0
        self._pos_pub_mono: float = 0.0
        self._last_reconcile_at: float = 0.0
        self._reconcile_ok = True
        self._bootstrap_ready = False
        self._mode = "paper"
        self._equity_curve: deque[dict[str, Any]] = deque(maxlen=EQUITY_CURVE_MAX_POINTS)
        self._action_log = SessionActionLogger(robot_id)
        self._status_message: str | None = None
        self._cycle_stage: str = "bootstrap"
        self._cycle_progress: float = 0.05
        self._cycle_detail: str | None = None
        self._cycle_skip_reason: str | None = None
        self._last_triggered_by: str | None = None
        self._last_ticker_scan: list[dict[str, Any]] = []
        self._last_ticker_scan_at: datetime | None = None
        self._audit_session_id: UUID | None = None
        self._account_id: str | None = None
        self._universe_resolve_pending = False
        self._universe_using_fallback = False
        self._universe_last_retry_at: float = 0.0
        self._universe_last_success_at: float = 0.0
        self._universe_force_at: float = 0.0
        self._universe_trade_date: date | None = None
        self._universe_refreshed_at: datetime | None = None
        self._last_universe_rejected: list[Any] = []
        self._universe_progress_last_at: float = 0.0

    def _universe_progress(self, phase: str, current: int, total: int, ticker: str) -> None:
        """Throttled bootstrap progress while MOEX screener / ATR cache warms up."""
        now = time.monotonic()
        if phase == "atr_warmup" and total > 0:
            if current < total and (now - self._universe_progress_last_at) < 0.4 and current % 3 != 0:
                return
            self._universe_progress_last_at = now
            detail = f"atr_warmup {current}/{total} {ticker}".strip()
            progress = round(0.08 + 0.14 * (current / max(total, 1)), 3)
        elif phase == "snapshot":
            detail = "moex_snapshot"
            progress = 0.06
        elif phase == "screener_filters":
            detail = "screener_filters"
            progress = 0.07
        else:
            detail = phase
            progress = None
        try:
            asyncio.get_running_loop().create_task(
                self._set_stage("bootstrap", detail=detail, progress=progress),
            )
        except RuntimeError:
            pass

    def _fire_audit_persist(self, bundle: AuditCycleBundle | None) -> None:
        if bundle is None:
            return
        asyncio.create_task(audit_persist_cycle(bundle))

    async def _persist_skip_cycle(
        self,
        *,
        cycle_number: int,
        triggered_by: str,
        skip_reason: str,
        message: str,
        started_at: datetime,
        equity: float | None = None,
    ) -> None:
        if self._audit_session_id is None:
            return
        finished = datetime.now(timezone.utc)
        bundle = AuditCycleBundle(
            cycle_id=uuid4(),
            session_id=self._audit_session_id,
            robot_id=self.robot_id,
            cycle_number=cycle_number,
            triggered_by=triggered_by,
            started_at=started_at,
            finished_at=finished,
            status="skip",
            skip_reason=skip_reason,
            equity=equity,
            stats={},
            decisions=[
                AuditDecisionRow(
                    stage="schedule",
                    outcome="skip",
                    code=skip_reason,
                    message=message,
                ),
            ],
        )
        self._fire_audit_persist(bundle)

    def _set_ticker_scan(self, rows: list[dict[str, Any]], *, at: datetime | None = None) -> None:
        self._last_ticker_scan = rows
        self._last_ticker_scan_at = at or datetime.now(timezone.utc)

    def _update_last_prices(
        self,
        prices: dict[str, float] | None = None,
        *,
        ticker: str | None = None,
        price: float | None = None,
        at: datetime | None = None,
    ) -> None:
        changed = False
        if prices:
            self.last_prices.update(prices)
            changed = bool(prices)
        if ticker and price is not None and price > 0:
            self.last_prices[str(ticker).upper()] = float(price)
            changed = True
        if changed:
            self.last_prices_at = at or datetime.now(timezone.utc)

    async def _publish_positions_throttled(self) -> None:
        if not self.ledger or not self.ledger.positions:
            return
        now_mono = time.monotonic()
        if now_mono - self._pos_pub_mono < POSITIONS_WS_MIN_INTERVAL_SEC:
            return
        self._pos_pub_mono = now_mono
        await event_bus.publish(self.robot_id, "positions", self._cycle_positions_payload())

    def _write_log(self, message: str) -> None:
        self._action_log.info(message)

    async def _set_stage(
        self,
        stage: str,
        *,
        skip_reason: str | None = None,
        publish: bool = True,
        detail: str | None = None,
        progress: float | None = None,
    ) -> None:
        self._cycle_stage = stage
        self._cycle_progress = (
            float(progress)
            if progress is not None
            else cycle_stage_progress(stage, detail)
        )
        self._cycle_detail = detail
        self._cycle_skip_reason = skip_reason
        if not publish:
            return
        label = CYCLE_STAGE_LABELS.get(stage, stage)
        payload: dict[str, Any] = {
            "stage": stage,
            "label": label,
            "progress": self._cycle_progress,
            "cycleNumber": self.cycle_number,
            "triggeredBy": self._last_triggered_by,
        }
        if skip_reason:
            payload["skipReason"] = skip_reason
        if detail:
            payload["detail"] = detail
        await event_bus.publish(self.robot_id, "stage", payload)
    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"robots_v2_session_{self.robot_id}")

    async def stop(self, *, hard: bool = False) -> None:
        if hard:
            self.stop_mode = "hard"
            if self.risk:
                self.risk.halt("hard_stop")
        elif self.risk:
            self.risk.pause_entries()
        self.state = SessionState.STOPPING
        self._status_message = "Остановка сессии…"
        self._stop_event.set()
        self._write_log(f"STOP requested mode={'hard' if hard else 'soft'}")
        task = self._task
        if task is None or task.done():
            if self.state == SessionState.STOPPING:
                self.state = SessionState.TERMINATED
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=STOP_JOIN_SEC)
        except asyncio.TimeoutError:
            self._write_log("STOP timeout — cancelling session task")
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=STOP_CANCEL_JOIN_SEC)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if not task.done():
                    from app.modules.robots_v2.engine.session_manager import session_manager
                    session_manager.on_session_ended(self.robot_id)
        if self.state == SessionState.STOPPING:
            self.state = SessionState.TERMINATED
            self._status_message = None

    def _open_positions_snapshot(self) -> list[dict[str, Any]]:
        if not self.ledger:
            return []
        positions = self.ledger.open_positions_list(self.last_prices)
        if positions and self._parsed is not None:
            positions = enrich_positions_with_exit_prices(positions, self._parsed.risk)
        return attach_ticker_warnings(
            positions, self.execution, last_prices=self.last_prices,
        )

    def _cycle_positions_payload(self) -> dict[str, Any]:
        rows = self._open_positions_snapshot()
        return {
            "openPositions": rows,
            "positionsUpdatedAt": self.last_prices_at.isoformat() if self.last_prices_at else None,
            "positions": len(rows),
        }

    def status(self) -> SessionStatus:
        equity = self.virtual_capital
        cash = self.virtual_capital
        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        if self.ledger:
            equity = self.ledger.mark_equity(self.last_prices)
            cash = self.ledger.cash
            positions = self._open_positions_snapshot()
        if self.execution is not None:
            pos_by_ticker = {
                str(p.get("ticker") or p.get("figi") or "").upper(): p
                for p in (positions or [])
            }
            for ticker, resting in getattr(self.execution, "_resting", {}).items():
                t_u = str(ticker).upper()
                pos_row = pos_by_ticker.get(t_u) or {}
                entry_px = float(
                    pos_row.get("entry_price")
                    or pos_row.get("entryPrice")
                    or pos_row.get("avg_entry_price")
                    or 0
                )
                open_orders.append({
                    "ticker": ticker,
                    "side": resting.side,
                    "quantity": resting.quantity,
                    "price": float(getattr(resting, "limit_price", None) or getattr(resting, "price", 0) or 0),
                    "status": "resting",
                    "orderType": getattr(resting, "order_type", None) or "LIMIT",
                    "kind": resting.kind,
                    "reason": resting.reason,
                    "brokerOrderId": resting.broker_order_id,
                    "source": "broker" if resting.broker_order_id else "local",
                    "entryPrice": entry_px if entry_px > 0 else None,
                })
        return SessionStatus(
            robot_id=self.robot_id,
            session_state=self.state,
            mode=str((self.raw_config.get("core") or {}).get("mode", "paper")),
            cycle_number=self.cycle_number,
            equity=equity,
            cash=cash,
            open_positions=positions,
            universe=list(self.universe),
            last_cycle_at=self.last_cycle_at,
            last_prices_at=self.last_prices_at,
            ws_healthy=self.ws_healthy,
            message=getattr(self, "_status_message", None),
            decisions=self.last_decisions[-10:],
            equity_curve=list(self._equity_curve),
            cycle_stage=self._cycle_stage,
            cycle_progress=self._cycle_progress,
            cycle_detail=self._cycle_detail,
            cycle_skip_reason=self._cycle_skip_reason,
            last_triggered_by=self._last_triggered_by,
            last_ticker_scan=list(self._last_ticker_scan),
            last_ticker_scan_at=self._last_ticker_scan_at,
            open_orders=open_orders,
            bootstrap_ready=self._bootstrap_ready,
            universe_refreshed_at=self._universe_refreshed_at,
        )

    def _price_subscription_tickers(self) -> list[str]:
        """Universe + open ledger positions (screener may drop held names)."""
        out: list[str] = []
        seen: set[str] = set()
        for t in list(self.universe) + list((self.ledger.positions if self.ledger else {}) or {}):
            tu = str(t or "").upper()
            if tu and tu not in seen:
                seen.add(tu)
                out.append(tu)
        return out

    async def _ensure_instrument_map(self, tickers: list[str]) -> None:
        """Resolve missing FIGI/symbols so reconcile can adopt held names."""
        if not tickers or self._parsed is None:
            return
        missing = [
            t for t in tickers
            if str(self._instrument_map.get(t) or "").upper() in ("", t)
        ]
        if not missing:
            return
        try:
            from app.modules.robots_v2.universe.token_context import load_token_context

            db = SessionLocal()
            try:
                token_ctx = load_token_context(
                    db,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    instrument_type=self._parsed.core.instrument_type,
                )
            finally:
                db.close()
            resolved = await resolve_ticker_instrument_map(
                token_ctx, missing, robot_id=self.robot_id,
            )
            for tk, iid in (resolved or {}).items():
                t = str(tk).upper()
                v = str(iid or "").strip().upper()
                if t and v:
                    self._instrument_map[t] = v
            self._ticker_by_instrument = {
                str(v).upper(): str(k).upper() for k, v in self._instrument_map.items()
            }
            self._sync_execution_instrument_map()
        except Exception:
            logger.exception("ensure instrument map failed robot_id=%s", self.robot_id)

    def _sync_execution_instrument_map(self) -> None:
        """Keep live order router on the same FIGI map as the session (universe refresh)."""
        exec_svc = getattr(self, "execution", None)
        if exec_svc is None:
            return
        updater = getattr(exec_svc, "update_instrument_map", None)
        if callable(updater):
            updater(self._instrument_map)

    async def _fallback_universe_tickers(self) -> list[str]:
        """When screener/index returns 0, keep trading held names + config hints."""
        from app.core.config import settings as _settings
        from app.modules.robots_v2.engine.broker_positions import open_tickers_from_audit_fills

        tickers: set[str] = set()
        if self._parsed is not None:
            uni = self._parsed.universe
            if uni.mode == "fixed" and uni.fixed_list:
                tickers.update(str(t).upper() for t in uni.fixed_list if t)
            elif uni.mode == "index" and uni.index_code:
                tickers.add(str(uni.index_code).upper())

        meta = self.raw_config.get("metadata") if isinstance(self.raw_config.get("metadata"), dict) else {}
        snap = meta.get("universeSnapshot") or meta.get("universe_snapshot")
        if isinstance(snap, list):
            for item in snap:
                if isinstance(item, dict) and item.get("ticker"):
                    tickers.add(str(item["ticker"]).upper())
                elif isinstance(item, str) and item.strip():
                    tickers.add(item.strip().upper())

        db = SessionLocal()
        try:
            hints = open_tickers_from_audit_fills(
                db,
                robot_id=self.robot_id,
                schema=getattr(_settings, "DB_SCHEMA", None) or "public",
            )
            tickers.update(str(t).upper() for t in hints if t)
        except Exception:
            logger.exception("fallback audit tickers failed robot_id=%s", self.robot_id)
        finally:
            db.close()

        return sorted(t for t in tickers if t)

    def _needs_dynamic_universe(self) -> bool:
        if self._parsed is None:
            return False
        return self._parsed.universe.mode in ("screener", "index")

    def _universe_refresh_policy(self) -> str:
        if self._parsed is None or not self._needs_dynamic_universe():
            return "on_session"
        screener = self._parsed.universe.screener
        if screener is not None:
            return str(screener.refresh_policy or "daily")
        return "daily"

    def _mark_universe_resolved(self, *, now: datetime | None = None) -> None:
        self._universe_trade_date = trade_date_msk(now)
        self._universe_last_success_at = time.monotonic()
        self._universe_refreshed_at = now or datetime.now(timezone.utc)

    def _universe_refresh_reason(self, *, now: datetime | None = None) -> str | None:
        if not self._parsed or not self._needs_dynamic_universe():
            return None
        in_session = is_within_trading_session(self._parsed.core.schedule, now=now)
        if self._universe_resolve_pending and in_session:
            return "pending"
        today = trade_date_msk(now)
        # Sessions routinely span overnight EOD hold — rebuild on a new MSK
        # trade date even when refreshPolicy is on_session.
        if (
            in_session
            and self._universe_trade_date is not None
            and self._universe_trade_date != today
        ):
            return "daily"
        if (
            self._universe_refresh_policy() == "on_poll"
            and in_session
            and (time.monotonic() - self._universe_last_success_at) >= UNIVERSE_POLL_REFRESH_SEC
        ):
            return "poll"
        return None

    async def refresh_universe(self, *, reason: str = "force") -> dict[str, Any]:
        """Force-rebuild screener/index universe (HTTP). Holds the cycle lock."""
        if self._parsed is None or not self._needs_dynamic_universe():
            raise ValueError("UNIVERSE_REFRESH_UNSUPPORTED")
        if self.state not in (SessionState.RUNNING, SessionState.BOOTSTRAP):
            raise ValueError("UNIVERSE_REFRESH_NO_SESSION")
        now_mono = time.monotonic()
        if now_mono - self._universe_force_at < UNIVERSE_FORCE_MIN_INTERVAL_SEC:
            raise ValueError("UNIVERSE_REFRESH_RATE_LIMITED")
        self._universe_force_at = now_mono
        async with self._cycle_lock:
            return await self._apply_universe_refresh(reason)

    async def _maybe_refresh_universe(self) -> None:
        """Retry empty screener, rebuild on a new trade date, or on_poll."""
        if not self._parsed or self._stop_event.is_set():
            return
        reason = self._universe_refresh_reason()
        if not reason:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        min_gap = UNIVERSE_POLL_REFRESH_SEC if reason == "poll" else UNIVERSE_RETRY_SEC
        if now - self._universe_last_retry_at < min_gap:
            return
        self._universe_last_retry_at = now
        await self._apply_universe_refresh(reason)

    async def _apply_universe_refresh(self, reason: str) -> dict[str, Any]:
        assert self._parsed is not None
        tickers, resolved_map = await self._resolve_universe_once()
        if not tickers:
            self._write_log(
                f"WARN Universe refresh empty reason={reason} mode={self._parsed.universe.mode}"
            )
            await event_bus.publish(self.robot_id, "universe", {
                "reason": reason,
                "keptPrevious": True,
                "universe": list(self.universe),
                "added": [],
                "removed": [],
            })
            return {
                "robotId": self.robot_id,
                "universe": list(self.universe),
                "added": [],
                "removed": [],
                "reason": reason,
                "keptPrevious": True,
                "refreshedAt": (
                    self._universe_refreshed_at.isoformat()
                    if self._universe_refreshed_at
                    else None
                ),
            }
        return await self._commit_universe(tickers, resolved_map, reason)

    async def _commit_universe(
        self,
        tickers: list[str],
        resolved_map: dict[str, str],
        reason: str,
    ) -> dict[str, Any]:
        held: set[str] = set()
        if self.ledger:
            held = {str(t).upper() for t in self.ledger.positions.keys() if t}

        new_set = {str(t).upper() for t in tickers} | held
        old_set = {str(t).upper() for t in self.universe}
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set - held)

        self.universe = sorted(new_set)
        for ticker, fid in resolved_map.items():
            if ticker and fid:
                self._instrument_map[ticker.upper()] = str(fid)

        if added:
            await self._ensure_instrument_map(added)
        self._sync_execution_instrument_map()

        self._universe_resolve_pending = False
        self._universe_using_fallback = False
        self._status_message = None
        self._mark_universe_resolved()
        self._set_ticker_scan(build_session_skip_scan(
            self.universe, self.last_prices,
            code="UNIVERSE_REFRESH",
            message=f"Пул обновлён ({reason})",
            candle_history=self.candle_history,
        ), at=self._universe_refreshed_at)
        await self._resync_price_subscriptions()
        self._write_log(
            f"Universe refreshed reason={reason} n={len(self.universe)} "
            f"added={added[:8]} removed={removed[:8]}"
        )
        payload = {
            "robotId": self.robot_id,
            "reason": reason,
            "keptPrevious": False,
            "universe": list(self.universe),
            "added": added,
            "removed": removed,
            "refreshedAt": (
                self._universe_refreshed_at.isoformat()
                if self._universe_refreshed_at
                else None
            ),
            "tickerScan": self._last_ticker_scan,
        }
        await event_bus.publish(self.robot_id, "universe", payload)
        await event_bus.publish(self.robot_id, "health", {
            "level": "ok",
            "message": f"Universe resolved ({len(self.universe)} tickers)",
            "code": "UNIVERSE_RESOLVED",
            "reason": reason,
        })
        return payload

    async def _resync_price_subscriptions(self) -> None:
        if self._broker is None or self._ws_queue is None:
            return
        instruments = [
            self._instrument_map.get(t, t)
            for t in self._price_subscription_tickers()
        ]
        try:
            await self._broker.subscribe_prices(self.user_id, instruments, self._ws_queue)
            self._write_log(f"WS resubscribed after universe n={len(instruments)}")
        except Exception as exc:
            logger.exception("ws resubscribe after universe robot_id=%s", self.robot_id)
            self._write_log(f"WARN WS resubscribe after universe: {exc}")

    async def _resolve_universe_once(self) -> tuple[list[str], dict[str, str]]:
        """Single universe_service.resolve attempt."""
        assert self._parsed is not None
        db = SessionLocal()
        try:
            resolved = await universe_service.resolve(
                db,
                self.user_id,
                token_id=self.token_id,
                instrument_type=self._parsed.core.instrument_type,
                universe_raw=self._parsed.universe.model_dump(by_alias=True),
                robot_id=self.robot_id,
                on_progress=self._universe_progress,
            )
            tickers = [i.ticker for i in resolved.instruments]
            resolved_map = {
                i.ticker.upper(): (i.figi or i.symbol_id or i.ticker)
                for i in resolved.instruments
                if i.ticker
            }
            self._last_universe_rejected = list(resolved.rejected or [])
            return tickers, resolved_map
        finally:
            db.close()

    async def _sleep_until_universe_retry(self, sec: float) -> bool:
        """Wait up to sec seconds; return False if stop was requested."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sec)
            return False
        except asyncio.TimeoutError:
            return True

    async def _fail_empty_universe(self) -> None:
        sample = [
            f"{getattr(r, 'ticker', '?')}:{getattr(r, 'code', '')}:{getattr(r, 'message', '')}"
            for r in (self._last_universe_rejected or [])[:5]
        ]
        mode = self._parsed.universe.mode if self._parsed else "?"
        self.state = SessionState.ERROR
        self._status_message = "Empty universe — screener returned 0 symbols"
        self._write_log(f"ERROR Empty universe mode={mode} rejected_sample={sample}")
        await event_bus.publish(self.robot_id, "health", {
            "level": "error",
            "message": self._status_message,
            "rejectedSample": sample,
        })

    async def _resolve_universe_for_session(self) -> tuple[bool, dict[str, str]]:
        """
        Resolve universe at session start.
        During trading hours, retry screener/index until symbols are returned.
        If fallback tickers exist (open fills), bootstrap on them and keep retrying in-session.
        """
        assert self._parsed is not None
        retry_sec = UNIVERSE_RETRY_SEC
        attempt = 0
        resolved_map: dict[str, str] = {}

        while not self._stop_event.is_set():
            attempt += 1
            resolved = await self._await_or_stop(
                self._resolve_universe_once(),
                what="universe_resolve",
            )
            if resolved is None:
                return False, {}
            tickers, resolved_map = resolved
            if tickers:
                self.universe = tickers
                self._universe_resolve_pending = False
                self._universe_using_fallback = False
                self._status_message = None
                self._mark_universe_resolved()
                return True, resolved_map

            if not self._needs_dynamic_universe():
                break

            in_session = is_within_trading_session(self._parsed.core.schedule)
            fallback = await self._fallback_universe_tickers()
            if fallback:
                self.universe = fallback
                self._universe_resolve_pending = True
                self._universe_using_fallback = True
                self._write_log(
                    f"WARN Empty {self._parsed.universe.mode} — bootstrap on fallback "
                    f"n={len(fallback)} tickers={fallback[:12]}; retry during session"
                )
                await event_bus.publish(self.robot_id, "health", {
                    "level": "warn",
                    "message": f"Universe fallback ({len(fallback)} tickers), retrying screener",
                    "code": "UNIVERSE_FALLBACK",
                })
                return True, resolved_map

            if not in_session:
                break

            self._status_message = (
                f"Ожидание universe ({self._parsed.universe.mode}), попытка {attempt}"
            )
            self._write_log(
                f"WARN Empty universe attempt={attempt} — retry in {retry_sec:.0f}s"
            )
            await self._set_stage("bootstrap", detail=f"universe_retry_{attempt}")
            await event_bus.publish(self.robot_id, "health", {
                "level": "warn",
                "message": self._status_message,
                "code": "UNIVERSE_RETRY",
            })
            if not await self._sleep_until_universe_retry(retry_sec):
                return False, {}

        await self._fail_empty_universe()
        return False, {}

    async def _audit_extra_tickers(self) -> set[str]:
        from app.core.config import settings as _settings
        from app.modules.robots_v2.engine.broker_positions import open_tickers_from_audit_fills

        db = SessionLocal()
        try:
            hints = open_tickers_from_audit_fills(
                db,
                robot_id=self.robot_id,
                schema=getattr(_settings, "DB_SCHEMA", None) or "public",
            )
            return set(hints.keys())
        except Exception:
            logger.exception("audit open tickers failed robot_id=%s", self.robot_id)
            return set()
        finally:
            db.close()

    async def _run(self) -> None:
        try:
            self._write_log(
                f"SESSION START mode={self.raw_config.get('core', {}).get('mode')} "
                f"capital={self.virtual_capital} token_id={self.token_id}"
            )
            self._parsed = TradingRobotConfigV4.model_validate(self.raw_config)
            mode = self._parsed.core.mode
            self._mode = mode
            db = SessionLocal()
            try:
                token_ctx = load_token_context(
                    db,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    instrument_type=self._parsed.core.instrument_type,
                )
            finally:
                db.close()

            ok, resolved_map = await self._resolve_universe_for_session()
            if not ok or self._stop_event.is_set():
                return

            self._write_log(
                f"Universe resolved n={len(self.universe)} sample={self.universe[:8]} broker={token_ctx.broker}"
            )
            await self._set_stage("bootstrap", detail="universe_ok")
            self._market = token_ctx.market
            self._allow_short = self._parsed.core.instrument_type in ("perpetual", "coin_futures")
            commission = self._parsed.risk.broker_commission_pct / 100.0
            self.ledger = PaperLedger(
                cash=self.virtual_capital,
                commission_rate=commission,
                allow_short=self._allow_short,
            )
            self.risk = RiskEngine(self._parsed.risk, allow_short=self._allow_short)

            broker = None
            account_id = None
            if mode == "live":
                broker = create_broker_from_token(
                    token_ctx,
                    instrument_type=self._parsed.core.instrument_type,
                    robot_config=self.raw_config,
                    robot_id=self.robot_id,
                )
                if broker is None:
                    self.state = SessionState.ERROR
                    self._write_log("ERROR Live mode requires valid broker token")
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "error", "message": "Live mode requires valid broker token",
                    })
                    return
                preferred = str((self.raw_config.get("core") or {}).get("accountId") or "").strip() or None
                if not preferred:
                    preferred = load_token_account_id(self.token_id, self.user_id)
                started_acc = datetime.now(timezone.utc)
                account_id = await resolve_account_id(broker, preferred)
                if account_id:
                    persist_token_account_id(
                        user_id=self.user_id,
                        token_id=self.token_id,
                        account_id=account_id,
                    )
                if getattr(broker, "broker_type", "") != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=f"{getattr(broker, 'broker_type', 'broker')}.get_accounts",
                        request_data={"preferred": preferred},
                        response_data={"account_id": account_id},
                        response_status=200 if account_id else None,
                        error_message=None if account_id else "no accounts",
                        started_at=started_acc,
                    )
                if not account_id:
                    self.state = SessionState.ERROR
                    self._write_log("ERROR Could not resolve broker accountId")
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "error", "message": "Could not resolve broker accountId",
                    })
                    return
                self._write_log(f"Live broker={getattr(broker, 'broker_type', '?')} account_id={account_id}")
                try:
                    ok = await broker.connect_websocket(self.user_id)
                    self.ws_healthy = bool(ok)
                    self._write_log(f"WebSocket connect ok={ok}")
                except Exception:
                    logger.exception("ws connect failed robot_id=%s", self.robot_id)
                    self.ws_healthy = False
                    self._write_log("WebSocket connect FAILED")

            instrument_map = dict(resolved_map)
            meta = self.raw_config.get("metadata") if isinstance(self.raw_config.get("metadata"), dict) else {}
            if isinstance(meta.get("instrumentMap"), dict):
                instrument_map.update({str(k).upper(): str(v) for k, v in meta["instrumentMap"].items()})
            elif isinstance(self.raw_config.get("instrument_map"), dict):
                im = self.raw_config["instrument_map"]
                # v1 shape: { figi_by_ticker: {...} } or flat ticker→id
                if isinstance(im.get("figi_by_ticker"), dict):
                    instrument_map.update({str(k).upper(): str(v) for k, v in im["figi_by_ticker"].items()})
                else:
                    instrument_map.update({str(k).upper(): str(v) for k, v in im.items() if k != "ticker_by_figi"})

            # Resolve FIGI/symbols for paper too — needed for candle seed + live later.
            # Must overwrite universe placeholders (ticker→ticker); setdefault blocked real FIGIs.
            try:
                map_tickers = list(self.universe)
                # Include open audit fill tickers so bootstrap can map FIGIs for adopted positions
                try:
                    from app.core.config import settings as _settings_pre
                    from app.modules.robots_v2.engine.broker_positions import open_tickers_from_audit_fills

                    db_pre = SessionLocal()
                    try:
                        pre_hints = open_tickers_from_audit_fills(
                            db_pre,
                            robot_id=self.robot_id,
                            schema=getattr(_settings_pre, "DB_SCHEMA", None) or "public",
                        )
                    finally:
                        db_pre.close()
                    for t in pre_hints:
                        if t not in {x.upper() for x in map_tickers}:
                            map_tickers.append(t)
                except Exception:
                    pass
                resolved_ids = await resolve_ticker_instrument_map(
                    token_ctx, map_tickers, robot_id=self.robot_id,
                )
                for tk, iid in (resolved_ids or {}).items():
                    t = str(tk).upper()
                    v = str(iid or "").strip().upper()
                    if not t or not v:
                        continue
                    prev = str(instrument_map.get(t) or "").upper()
                    # Prefer broker id over ticker placeholder from universe
                    if not prev or prev == t or v != t:
                        instrument_map[t] = v
                figi_ok = sum(
                    1 for t in self.universe
                    if str(instrument_map.get(str(t).upper()) or "").upper()
                    not in ("", str(t).upper())
                )
                self._write_log(
                    f"Instrument map resolved figiOrSymbol={figi_ok}/{len(self.universe)} "
                    f"sample={list(instrument_map.items())[:3]}"
                )
            except Exception:
                logger.exception("instrument map resolve failed robot_id=%s", self.robot_id)
                self._write_log("WARN instrument map resolve failed")

            self._instrument_map = {str(k).upper(): str(v) for k, v in instrument_map.items()}
            self._ticker_by_instrument = {v.upper(): k for k, v in self._instrument_map.items()}
            self._broker = broker

            await self._set_stage("bootstrap", detail="seeding_candles")
            seeded = await self._await_or_stop(
                self._seed_candle_history(token_ctx),
                what="candle_seed",
            )
            if seeded is None and self._stop_event.is_set():
                return

            self.execution = ExecutionService(
                mode=mode,
                robot_id=self.robot_id,
                ledger=self.ledger,
                slippage_pct=self._parsed.risk.slippage_pct,
                broker=broker,
                account_id=account_id,
                instrument_map=self._instrument_map,
                user_id=self.user_id,
                token_id=self.token_id,
                action_log=self._action_log,
            )
            self._account_id = account_id
            self._audit_session_id = await audit_start_session(
                robot_id=self.robot_id,
                mode=mode,
                virtual_capital=self.virtual_capital,
                account_id=account_id,
            )

            session_equity = self.virtual_capital
            if mode == "live" and broker is not None and account_id and self.ledger is not None:
                from app.core.config import settings as _settings
                from app.modules.robots_v2.engine.broker_positions import (
                    apply_opened_at_hints,
                    open_tickers_from_audit_fills,
                )

                await self._set_stage("bootstrap", detail="reconcile")
                open_hints: dict[str, Any] = {}
                db_hints = SessionLocal()
                try:
                    open_hints = open_tickers_from_audit_fills(
                        db_hints,
                        robot_id=self.robot_id,
                        schema=getattr(_settings, "DB_SCHEMA", None) or "public",
                    )
                finally:
                    db_hints.close()
                extra = set(open_hints.keys())
                if extra:
                    self._write_log(
                        f"Adopt candidates from audit fills: {sorted(extra)}"
                    )

                rec = await reconcile_from_broker(
                    robot_id=self.robot_id,
                    broker=broker,
                    account_id=account_id,
                    ledger=self.ledger,
                    instrument_map=self._instrument_map,
                    universe=self.universe,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    extra_tickers=extra or None,
                )
                if not rec.ok:
                    self.state = SessionState.ERROR
                    self._write_log(f"ERROR Bootstrap reconcile failed: {rec.error}")
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "error",
                        "message": f"Bootstrap reconcile failed: {rec.error}",
                    })
                    return
                apply_opened_at_hints(self.ledger.positions, open_hints)
                session_equity = self.ledger.mark_equity(self.last_prices)
                if self.risk is not None:
                    self.risk.rebind_capital(session_equity)
                held = sorted(self.ledger.positions.keys())
                self._write_log(
                    f"Bootstrap reconcile ok cash={rec.cash:.2f} positions={rec.positions} "
                    f"held={held} adopted={rec.adopted} "
                    f"equity={session_equity:.2f} (from_broker)"
                )
                if self.execution is not None:
                    await self._set_stage("bootstrap", detail="orders")
                    sync_fills = await self.execution.sync_orders_from_broker(force=True)
                    open_n = len(getattr(self.execution, "_resting", {}) or {})
                    self._write_log(
                        f"Bootstrap order sync open={open_n} "
                        f"events={len(sync_fills)}"
                    )
                self._last_reconcile_at = asyncio.get_running_loop().time()
                self._reconcile_ok = True

            self.risk.begin_session(session_equity)

            # Scalper order-flow window from params
            if self._parsed.strategy.archetype == "scalper":
                win = int(self._parsed.strategy.params.get("minVolumeWindow") or 30)
                self.order_flow = OrderFlowAggregator(window_sec=win)

            # Cycle 0: full data sync (prices + broker) before any trading loops.
            sync_ok = await self._await_bootstrap_sync()
            if not sync_ok or self._stop_event.is_set():
                if self.state != SessionState.ERROR and not self._stop_event.is_set():
                    self.state = SessionState.ERROR
                    self._status_message = "Bootstrap sync failed"
                return

            self.state = SessionState.RUNNING
            self._write_log(
                f"RUNNING archetype={self._parsed.strategy.archetype} "
                f"poll={self._parsed.core.schedule.poll_interval} wsHealthy={self.ws_healthy}"
            )
            await event_bus.publish(self.robot_id, "health", {
                "level": "ok",
                "state": "RUNNING",
                "mode": mode,
                "wsHealthy": self.ws_healthy,
                "bootstrapReady": True,
            })

            poll_sec = poll_interval_seconds(self._parsed.core.schedule.poll_interval)
            is_scalper = self._parsed.strategy.archetype == "scalper"
            if is_scalper and mode == "live" and broker is not None:
                self._ws_task = asyncio.create_task(
                    self._ws_price_loop(),
                    name=f"robots_v2_ws_{self.robot_id}",
                )
            elif is_scalper:
                self._scalper_task = asyncio.create_task(
                    self._scalper_loop(),
                    name=f"robots_v2_scalper_{self.robot_id}",
                )

            while not self._stop_event.is_set():
                # Spec: momentum/reversion entries only on bar_close; poll loop IS the
                # timeframe bar wake for non-scalper archetypes.
                arch = self._parsed.strategy.archetype if self._parsed else ""
                wake = "bar_close" if arch in ("momentum", "reversion") else "poll"
                await self._poll_cycle(triggered_by=wake)
                if self.risk and self.risk.session_state.halt_session:
                    break
                # Outside MOEX hours keep a short heartbeat so monitor/WS don't look frozen
                sleep_sec = float(poll_sec)
                if self._parsed and not is_within_trading_session(self._parsed.core.schedule):
                    sleep_sec = min(sleep_sec, 30.0)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
                except asyncio.TimeoutError:
                    continue

            for task in (self._scalper_task, self._ws_task):
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            if self.stop_mode == "hard" and self.ledger and self.execution:
                self._write_log(f"HARD_STOP flatten positions={len(self.ledger.positions)}")
                for t, pos in list(self.ledger.positions.items()):
                    px = self.last_prices.get(t, pos.avg_entry_price)
                    from app.modules.robots.trading.contracts import OrderIntent
                    intent = OrderIntent(
                        kind="flatten",
                        figi=t,
                        side="SELL" if pos.is_long else "BUY",
                        quantity=float(pos.quantity),
                        price=px,
                        reduce_only=True,
                        reason="hard_stop",
                    )
                    await self.execution.execute_intent(intent, last_price=px)

            if broker is not None:
                try:
                    if self._ws_queue is not None:
                        ids = list(self._instrument_map.values()) or list(self.universe)
                        await broker.unsubscribe_prices(self.user_id, ids, self._ws_queue)
                    await broker.close_websocket(self.user_id)
                except Exception:
                    pass

            self.state = SessionState.TERMINATED
            self._write_log("SESSION TERMINATED")
            await event_bus.publish(self.robot_id, "health", {"level": "ok", "state": "TERMINATED"})
        except asyncio.CancelledError:
            self._write_log("SESSION CANCELLED")
            if self.state != SessionState.ERROR:
                self.state = SessionState.TERMINATED
            raise
        except Exception as exc:
            logger.exception("robots_v2 session failed robot_id=%s", self.robot_id)
            self.state = SessionState.ERROR
            self._action_log.exception(f"SESSION ERROR: {exc}")
            self._status_message = str(exc)[:300]
            await event_bus.publish(self.robot_id, "health", {"level": "error", "message": str(exc)})
        finally:
            stop_reason = "hard_stop" if self.stop_mode == "hard" else "soft_stop"
            if self.state == SessionState.ERROR:
                stop_reason = "error"
            elif self._stop_event.is_set() and self.state != SessionState.ERROR:
                self.state = SessionState.TERMINATED
            try:
                await asyncio.wait_for(
                    self._finalize_orders_audit(stop_reason=stop_reason),
                    timeout=FINALIZE_AUDIT_SEC,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as exc:
                logger.warning("finalize on stop failed robot_id=%s: %s", self.robot_id, exc)
            try:
                await asyncio.wait_for(
                    audit_end_session(self._audit_session_id, stop_reason=stop_reason),
                    timeout=5.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            from app.modules.robots_v2.engine.session_manager import session_manager
            session_manager.on_session_ended(self.robot_id)

    async def _await_or_stop(self, awaitable: Any, *, what: str) -> Any:
        """Wait for a bootstrap step, or abort immediately when stop is requested."""
        if self._stop_event.is_set():
            return None
        task = asyncio.ensure_future(awaitable)
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            done, _pending = await asyncio.wait(
                {task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            task.cancel()
            stop_task.cancel()
            raise
        stop_task.cancel()
        if self._stop_event.is_set() and task not in done:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            self._write_log(f"STOP aborted {what}")
            return None
        return task.result()

    async def _finalize_orders_audit(self, *, stop_reason: str) -> None:
        """Sync broker orders on shutdown and close stale audit resting rows."""
        if self.execution is None or self._mode != "live":
            return
        try:
            from app.modules.robots_v2.engine.audit import audit_reconcile_resting_orders

            sync_results = await self.execution.sync_orders_from_broker(force=True)
            open_ids = {
                str(ro.broker_order_id)
                for ro in getattr(self.execution, "_resting", {}).values()
                if getattr(ro, "broker_order_id", None)
            }
            n = await audit_reconcile_resting_orders(
                robot_id=self.robot_id,
                sync_results=sync_results,
                open_broker_order_ids=open_ids,
                stop_reason=f"{stop_reason}_sync",
            )
            if n:
                self._write_log(f"Audit order reconcile updated={n} open_broker={len(open_ids)}")
        except Exception as exc:
            logger.exception("finalize orders audit failed robot_id=%s", self.robot_id)
            self._write_log(f"WARN audit order reconcile failed: {exc}")

    async def _await_bootstrap_sync(self, *, max_attempts: int = 6, retry_sec: float = 5.0) -> bool:
        """Retry full sync-only cycle until ready or stop/error."""
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            await self._set_stage("bootstrap_sync", detail=f"attempt={attempt}")
            self._write_log(f"BOOTSTRAP_SYNC start attempt={attempt}")
            try:
                ok = await asyncio.wait_for(self._bootstrap_sync_once(), timeout=90.0)
            except asyncio.TimeoutError:
                ok = False
                self._write_log(f"ERROR BOOTSTRAP_SYNC timeout attempt={attempt}")
                await event_bus.publish(self.robot_id, "health", {
                    "level": "error",
                    "message": f"Bootstrap sync timeout (attempt {attempt})",
                    "code": "BOOTSTRAP_SYNC_TIMEOUT",
                })
            except Exception as exc:
                logger.exception("bootstrap sync failed robot_id=%s", self.robot_id)
                ok = False
                self._write_log(f"ERROR BOOTSTRAP_SYNC: {exc}")
                await event_bus.publish(self.robot_id, "health", {
                    "level": "error",
                    "message": f"Bootstrap sync failed: {exc}",
                    "code": "BOOTSTRAP_SYNC_FAILED",
                })
            if ok:
                self._bootstrap_ready = True
                self._write_log(
                    f"BOOTSTRAP_SYNC ok attempt={attempt} "
                    f"positions={len(self.ledger.positions) if self.ledger else 0} "
                    f"prices={len(self.last_prices)}"
                )
                await event_bus.publish(self.robot_id, "health", {
                    "level": "ok",
                    "message": "Bootstrap sync complete",
                    "code": "BOOTSTRAP_SYNC_OK",
                    "attempt": attempt,
                })
                return True
            if attempt >= max_attempts:
                self._write_log(f"ERROR BOOTSTRAP_SYNC exhausted attempts={attempt}")
                await event_bus.publish(self.robot_id, "health", {
                    "level": "error",
                    "message": f"Bootstrap sync failed after {attempt} attempts",
                    "code": "BOOTSTRAP_SYNC_FAILED",
                })
                return False
            self._write_log(f"BOOTSTRAP_SYNC retry in {retry_sec:.0f}s attempt={attempt}/{max_attempts}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=retry_sec)
            except asyncio.TimeoutError:
                continue
        return False

    async def _bootstrap_sync_once(self) -> bool:
        """
        Cycle 0: refresh prices + broker positions/orders. No SL/TP, no strategy, no entries.
        """
        if self._parsed is None or self.ledger is None or self.execution is None:
            return False

        started = datetime.now(timezone.utc)
        self._last_triggered_by = "bootstrap_sync"
        await self._set_stage("bootstrap_sync", detail="prices")

        extra = await self._audit_extra_tickers()
        extra |= {str(t).upper() for t in self.ledger.positions}
        tickers = list({
            *(str(t).upper() for t in self.universe if t),
            *extra,
        })
        await self._ensure_instrument_map(tickers)

        db = SessionLocal()
        try:
            prices = await fetch_prices_for_session(
                db,
                market=self._market,
                tickers=tickers,
                token_id=self.token_id,
                user_id=self.user_id,
                instrument_type=self._parsed.core.instrument_type,
                robot_id=self.robot_id,
            )
        finally:
            db.close()

        if prices:
            self._update_last_prices(prices)

        # Paper: prices alone are enough to unlock trading loops.
        if self._mode != "live" or self._broker is None or not self.execution.account_id:
            self.cycle_number += 1
            eq = self.ledger.mark_equity(self.last_prices)
            await self._persist_skip_cycle(
                cycle_number=self.cycle_number,
                triggered_by="bootstrap_sync",
                skip_reason="BOOTSTRAP_SYNC",
                message="Bootstrap sync (paper) — торговля ещё не запускалась",
                started_at=started,
                equity=eq,
            )
            self.last_cycle_at = datetime.now(timezone.utc)
            await self._set_stage("done", detail="bootstrap_sync_paper")
            # Unlock even without prices (e.g. off-hours); trading cycles will NO_PRICES-skip.
            return True

        await self._set_stage("bootstrap_sync", detail="reconcile")
        rec = await reconcile_from_broker(
            robot_id=self.robot_id,
            broker=self._broker,
            account_id=self.execution.account_id,
            ledger=self.ledger,
            instrument_map=self._instrument_map,
            universe=self.universe,
            user_id=self.user_id,
            token_id=self.token_id,
            extra_tickers=extra or None,
        )
        self._last_reconcile_at = asyncio.get_running_loop().time()
        self._reconcile_ok = rec.ok
        if not rec.ok:
            self._write_log(f"BOOTSTRAP_SYNC reconcile failed: {rec.error}")
            return False

        # Held names may appear only after reconcile — refresh their marks.
        held = [str(t).upper() for t in self.ledger.positions]
        need_px = [t for t in held if t not in self.last_prices]
        if need_px:
            await self._ensure_instrument_map(need_px)
            db = SessionLocal()
            try:
                more = await fetch_prices_for_session(
                    db,
                    market=self._market,
                    tickers=need_px,
                    token_id=self.token_id,
                    user_id=self.user_id,
                    instrument_type=self._parsed.core.instrument_type,
                    robot_id=self.robot_id,
                )
            finally:
                db.close()
            if more:
                self._update_last_prices(more)

        await self._set_stage("bootstrap_sync", detail="orders")
        sync_fills = await self.execution.sync_orders_from_broker(force=True)
        open_n = len(getattr(self.execution, "_resting", {}) or {})

        self.cycle_number += 1
        eq = self.ledger.mark_equity(self.last_prices)
        if self.risk is not None:
            self.risk.rebind_capital(eq)
            # Keep session day-start aligned with broker equity after sync.
            if self._mode == "live":
                self.risk.begin_session(eq)
                self.virtual_capital = eq
        held_now = sorted(self.ledger.positions.keys())
        msg = (
            f"Bootstrap sync — cash={rec.cash:.2f} positions={held_now} "
            f"resting={open_n} syncEvents={len(sync_fills)} equity={eq:.2f}"
        )
        await self._persist_skip_cycle(
            cycle_number=self.cycle_number,
            triggered_by="bootstrap_sync",
            skip_reason="BOOTSTRAP_SYNC",
            message=msg,
            started_at=started,
            equity=eq,
        )
        self.last_decisions = [{
            "code": "BOOTSTRAP_SYNC",
            "message": msg,
            "allow": False,
        }]
        self.last_cycle_at = datetime.now(timezone.utc)
        self._write_log(
            f"CYCLE #{self.cycle_number} by=bootstrap_sync equity={eq:.2f} "
            f"positions={len(held_now)} resting={open_n}"
        )
        await event_bus.publish(self.robot_id, "cycle", {
            "cycleNumber": self.cycle_number,
            "equity": eq,
            "signals": 0,
            "mode": self._mode,
            "triggeredBy": "bootstrap_sync",
            "stage": "done",
            "skipReason": "BOOTSTRAP_SYNC",
            **self._cycle_positions_payload(),
        })
        await self._set_stage("done", detail="bootstrap_sync")
        return True

    async def _scalper_loop(self) -> None:
        """Price-tick wake for paper scalper (REST-polled prices, rate-limited)."""
        while not self._stop_event.is_set():
            try:
                await self._poll_cycle(triggered_by="price_tick")
            except Exception:
                logger.exception("scalper tick failed robot_id=%s", self.robot_id)
                self._write_log("ERROR scalper tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=SCALPER_TICK_MIN_INTERVAL_SEC)
            except asyncio.TimeoutError:
                continue

    async def _ws_price_loop(self) -> None:
        """Subscribe broker lastPrice/kline stream → order-flow + scalper ticks."""
        broker = self._broker
        if broker is None:
            return
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._ws_queue = queue
        instruments = [
            self._instrument_map.get(t, t)
            for t in self._price_subscription_tickers()
        ]
        try:
            await broker.subscribe_prices(self.user_id, instruments, queue)
            self.ws_healthy = True
            self._write_log(f"WS subscribed instruments={len(instruments)}")
            await event_bus.publish(self.robot_id, "health", {
                "level": "ok", "wsHealthy": True, "subscribed": len(instruments),
            })
        except Exception as exc:
            logger.exception("ws subscribe failed robot_id=%s", self.robot_id)
            self.ws_healthy = False
            self._write_log(f"ERROR ws subscribe: {exc}")
            await event_bus.publish(self.robot_id, "health", {
                "level": "warn", "wsHealthy": False, "message": str(exc)[:300],
            })
            # Fallback to REST scalper loop
            await self._scalper_loop()
            return

        loop = asyncio.get_running_loop()
        last_event_at = loop.time()
        rest_fallback_armed = False
        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                now_mono = loop.time()
                silence = now_mono - last_event_at
                if silence >= WS_SILENCE_RESUBSCRIBE_SEC:
                    self._write_log(f"WARN WS silence {silence:.0f}s — force resubscribe")
                    try:
                        ok = await broker.force_resubscribe_websocket(self.user_id)
                        self._write_log(f"WS resubscribe ok={ok}")
                        if ok:
                            last_event_at = loop.time()
                    except Exception as exc:
                        self._write_log(f"ERROR WS resubscribe: {exc}")
                        self.ws_healthy = False
                if silence >= WS_SILENCE_REST_FALLBACK_SEC and not rest_fallback_armed:
                    rest_fallback_armed = True
                    self.ws_healthy = False
                    self._write_log("WARN WS silence — REST scalper fallback armed")
                    await event_bus.publish(self.robot_id, "health", {
                        "level": "warn",
                        "wsHealthy": False,
                        "message": f"no market events {int(silence)}s — REST fallback",
                    })
                    if self._scalper_task is None or self._scalper_task.done():
                        self._scalper_task = asyncio.create_task(
                            self._scalper_loop(),
                            name=f"robots_v2_scalper_fallback_{self.robot_id}",
                        )
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ws queue read failed robot_id=%s", self.robot_id)
                self.ws_healthy = False
                self._write_log("ERROR ws queue read failed")
                continue

            last_event_at = loop.time()
            if rest_fallback_armed:
                rest_fallback_armed = False
                self.ws_healthy = True
                self._write_log("WS events resumed — clearing REST fallback flag")
                if self._scalper_task and not self._scalper_task.done():
                    self._scalper_task.cancel()
                    try:
                        await self._scalper_task
                    except asyncio.CancelledError:
                        pass
                    self._scalper_task = None
                await event_bus.publish(self.robot_id, "health", {
                    "level": "ok", "wsHealthy": True, "message": "ws events resumed",
                })

            if not isinstance(msg, dict):
                continue
            msg_type = str(msg.get("type") or "")
            figi = str(msg.get("figi") or msg.get("symbol") or "").upper()
            price_raw = msg.get("price")
            if price_raw is None and isinstance(msg.get("candle"), dict):
                price_raw = msg["candle"].get("close")
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                continue
            if not figi or price <= 0:
                continue

            ticker = self._ticker_by_instrument.get(figi, figi)
            now = datetime.now(timezone.utc)

            if msg_type == "trade":
                side = str(msg.get("side") or "buy")
                vol = float(msg.get("volume") or msg.get("size") or 0) or 1.0
                turnover = msg.get("turnover")
                try:
                    turnover_f = float(turnover) if turnover is not None else None
                except (TypeError, ValueError):
                    turnover_f = None
                self.order_flow.on_trade(
                    ticker, price=price, side=side, volume=vol, now=now, turnover=turnover_f,
                )
                self._update_last_prices(ticker=ticker, price=price, at=now)
            else:
                # price / candle_closed — inferred side unless real trades already active
                candle = msg.get("candle") if isinstance(msg.get("candle"), dict) else None
                turnover = None
                if candle is not None:
                    try:
                        turnover = float(candle.get("turnover") or 0) or None
                    except (TypeError, ValueError):
                        turnover = None
                if turnover and turnover > 0:
                    # Closed candle with turnover: attribute as aggressive side by close vs open
                    side = "buy"
                    try:
                        o = float(candle.get("open") or price)
                        if price < o:
                            side = "sell"
                    except (TypeError, ValueError):
                        pass
                    self.order_flow.on_trade(
                        ticker, price=price, side=side, volume=1.0, now=now, turnover=turnover,
                    )
                else:
                    self.order_flow.on_price(ticker, price, volume=1.0, now=now)
                self._update_last_prices(ticker=ticker, price=price, at=now)

            await self._publish_positions_throttled()

            now_mono = loop.time()
            if now_mono - self._last_scalper_ws_tick_at < SCALPER_WS_TICK_MIN_INTERVAL_SEC:
                continue
            self._last_scalper_ws_tick_at = now_mono
            try:
                await self._poll_cycle(triggered_by="price_tick")
            except Exception:
                logger.exception("ws scalper tick failed robot_id=%s", self.robot_id)
                self._write_log("ERROR ws scalper tick failed")

    async def _seed_candle_history(self, token_ctx: Any) -> None:
        """Warm momentum/reversion/grid with cache + broker REST history in one shot."""
        if self._parsed is None or not self.universe:
            return
        try:
            from app.modules.robots_v2.engine.candle_seed import seed_candle_history, warmup_bars_needed

            need = warmup_bars_needed(self._parsed)
            seeded = await seed_candle_history(
                config=self._parsed,
                universe=self.universe,
                token_ctx=token_ctx,
                instrument_map=self._instrument_map,
                log=self._action_log,
                robot_id=self.robot_id,
            )
            for ticker, candles in (seeded or {}).items():
                if candles:
                    self.candle_history[str(ticker).upper()] = list(candles)
            ready = sum(
                1 for t in self.universe
                if len(self.candle_history.get(str(t).upper()) or []) >= need
            )
            self._write_log(
                f"Candle seed done ready={ready}/{len(self.universe)} need={need} "
                f"tickersWithBars={sum(1 for t in self.universe if self.candle_history.get(str(t).upper()))}"
            )
        except Exception as exc:
            self._write_log(f"WARN candle seed failed: {exc}")

    async def _poll_cycle(self, *, triggered_by: str) -> None:
        async with self._cycle_lock:
            if self._parsed is None or self.ledger is None or self.risk is None or self.execution is None:
                return
            if self._stop_event.is_set() or self.state not in (SessionState.RUNNING, SessionState.BOOTSTRAP):
                return
            # Trading cycles only after bootstrap sync completed.
            if not self._bootstrap_ready and triggered_by != "bootstrap_sync":
                return

            await self._maybe_refresh_universe()

            self._last_triggered_by = triggered_by
            await self._set_stage("prices")

            price_tickers = list(self.universe)
            if self.ledger:
                for t in self.ledger.positions:
                    tu = str(t).upper()
                    if tu and tu not in {x.upper() for x in price_tickers}:
                        price_tickers.append(tu)

            # Scalper ticks: trade on live WS; REST only fills names the stream
            # does not have. Poll cycles still let REST overwrite (SL/TP).
            seed_from_ws = triggered_by == "price_tick" and bool(self.last_prices)
            held = [str(t).upper() for t in (self.ledger.positions if self.ledger else {})]
            missing = [
                t for t in price_tickers
                if t not in self.last_prices
            ]
            refresh = list({*missing, *held})
            fetched: dict[str, float] = {}
            if refresh or not self.last_prices:
                db = SessionLocal()
                try:
                    fetched = await fetch_prices_for_session(
                        db,
                        market=self._market,
                        tickers=refresh if refresh else price_tickers,
                        token_id=self.token_id,
                        user_id=self.user_id,
                        instrument_type=self._parsed.core.instrument_type,
                        robot_id=self.robot_id,
                    )
                finally:
                    db.close()
            prices, gap_fill = merge_ws_and_rest_prices(
                last_prices=self.last_prices,
                rest_prices=fetched,
                tickers=price_tickers,
                seed_from_ws=seed_from_ws,
            )
            if gap_fill:
                self._update_last_prices(gap_fill)

            for t in price_tickers:
                if t not in prices and t in self.last_prices:
                    prices[t] = self.last_prices[t]
            if not prices:
                now_skip = datetime.now(timezone.utc)
                self.cycle_number += 1
                eq = self.ledger.mark_equity(self.last_prices) if self.ledger else self.virtual_capital
                await self._persist_skip_cycle(
                    cycle_number=self.cycle_number,
                    triggered_by=triggered_by,
                    skip_reason="NO_PRICES",
                    message="Нет цен — стратегия не оценивалась",
                    started_at=now_skip,
                    equity=eq,
                )
                self._set_ticker_scan(build_session_skip_scan(
                    self.universe, self.last_prices,
                    code="NO_PRICES",
                    message="Нет цен — стратегия не оценивалась",
                    candle_history=self.candle_history,
                ), at=now_skip)
                await self._set_stage("skipped", skip_reason="NO_PRICES", detail="empty price map")
                return
            # Include held tickers (screener may have dropped them) — SL/TP needs their marks.
            price_keys = list(self.universe)
            if self.ledger:
                for t in self.ledger.positions:
                    tu = str(t).upper()
                    if tu and tu not in {x.upper() for x in price_keys}:
                        price_keys.append(tu)
            for t in price_keys:
                if t not in prices and t in self.last_prices:
                    prices[t] = self.last_prices[t]
            prices = {t: prices[t] for t in price_keys if t in prices}
            if not prices:
                now_skip = datetime.now(timezone.utc)
                self.cycle_number += 1
                eq = self.ledger.mark_equity(self.last_prices) if self.ledger else self.virtual_capital
                await self._persist_skip_cycle(
                    cycle_number=self.cycle_number,
                    triggered_by=triggered_by,
                    skip_reason="NO_PRICES",
                    message="Нет цен по universe — стратегия не оценивалась",
                    started_at=now_skip,
                    equity=eq,
                )
                self._set_ticker_scan(build_session_skip_scan(
                    self.universe, self.last_prices,
                    code="NO_PRICES",
                    message="Нет цен по universe — стратегия не оценивалась",
                    candle_history=self.candle_history,
                ), at=now_skip)
                await self._set_stage("skipped", skip_reason="NO_PRICES")
                return
            now = datetime.now(timezone.utc)
            cycle_started_at = now

            # ADR-11: live broker is source of truth (throttled on scalper ticks)
            if self._mode == "live" and self._broker is not None and self.execution and self.execution.account_id:
                await self._set_stage("reconcile")
                loop = asyncio.get_running_loop()
                now_mono = loop.time()
                should_reconcile = (
                    triggered_by in ("poll", "bar_close", "bootstrap_sync")
                    or (now_mono - self._last_reconcile_at) >= 5.0
                )
                if should_reconcile:
                    extra = await self._audit_extra_tickers()
                    if self.ledger:
                        extra |= {str(t).upper() for t in self.ledger.positions}
                    await self._ensure_instrument_map(sorted(extra | {str(t).upper() for t in self.universe}))
                    rec = await reconcile_from_broker(
                        robot_id=self.robot_id,
                        broker=self._broker,
                        account_id=self.execution.account_id,
                        ledger=self.ledger,
                        instrument_map=self._instrument_map,
                        universe=self.universe,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        extra_tickers=extra or None,
                    )
                    self._last_reconcile_at = now_mono
                    self._reconcile_ok = rec.ok
                    if not rec.ok:
                        self._write_log(f"RECONCILE FAILED: {rec.error}")
                        await event_bus.publish(self.robot_id, "health", {
                            "level": "error",
                            "message": f"reconcile failed: {rec.error}",
                            "code": "RECONCILE_FAILED",
                        })
                        self.last_cycle_at = now
                        self.last_decisions = [{
                            "code": "RECONCILE_FAILED",
                            "message": str(rec.error or "reconcile failed"),
                            "allow": False,
                        }]
                        eq = self.ledger.mark_equity(prices) if self.ledger else self.virtual_capital
                        self.cycle_number += 1
                        await self._persist_skip_cycle(
                            cycle_number=self.cycle_number,
                            triggered_by=triggered_by,
                            skip_reason="RECONCILE_FAILED",
                            message=str(rec.error or "reconcile failed"),
                            started_at=cycle_started_at,
                            equity=eq,
                        )
                        self._set_ticker_scan(build_session_skip_scan(
                            self.universe, prices,
                            code="RECONCILE_FAILED",
                            message="Сверка с брокером не удалась — стратегия не оценивалась",
                            candle_history=self.candle_history,
                        ), at=now)
                        await self._set_stage("skipped", skip_reason="RECONCILE_FAILED")
                        return  # PreFlight: block cycle when broker sync impossible
                    if rec.diffs:
                        self._write_log(
                            f"RECONCILE diffs={len(rec.diffs)} cash={rec.cash:.2f} positions={rec.positions}"
                        )
            # Avoid double-counting order-flow when WS already ingested the tick.
            # Poll REST snapshots must not inject a fake print (PLZL 1020 vs tape ~1001).
            if triggered_by != "price_tick" or self._ws_task is None:
                for t, px in prices.items():
                    if triggered_by == "poll" and t in self.last_prices:
                        continue
                    self.order_flow.on_price(t, px, volume=1.0, now=now)

            from app.modules.robots_v2.engine.candle_seed import warmup_bars_needed

            need_warmup = warmup_bars_needed(self._parsed)
            for t, px in prices.items():
                hist = self.candle_history.setdefault(t, [])
                tf = self._parsed.strategy.timeframe or "5m"
                # Seeded history: only refresh the last bar on ticks.
                # Live warmup (seed failed): grow one bar per bar_close until need met.
                if not hist:
                    hist.append(Candle(
                        interval=tf,
                        time=now,
                        open=px, high=px, low=px, close=px, volume=0, secid=t,
                    ))
                elif len(hist) >= need_warmup:
                    last = hist[-1]
                    try:
                        last.close = float(px)
                        last.high = max(float(last.high or px), float(px))
                        last.low = min(float(last.low or px), float(px))
                    except (TypeError, ValueError):
                        pass
                elif triggered_by == "bar_close":
                    hist.append(Candle(
                        interval=tf,
                        time=now,
                        open=px, high=px, low=px, close=px, volume=0, secid=t,
                    ))
                else:
                    last = hist[-1]
                    try:
                        last.close = float(px)
                        last.high = max(float(last.high or px), float(px))
                        last.low = min(float(last.low or px), float(px))
                    except (TypeError, ValueError):
                        pass
                if len(hist) > 200:
                    self.candle_history[t] = hist[-200:]

            self.cycle_number += 1
            await self._set_stage("schedule")

            in_eod = should_eod_flatten(
                risk=self._parsed.risk,
                schedule=self._parsed.core.schedule,
                instrument_type=self._parsed.core.instrument_type,
            )
            if self._eod_done and not in_eod and is_within_trading_session(self._parsed.core.schedule):
                self._eod_done = False
                self.risk.resume_entries()
                self._write_log("EOD window cleared — entries resumed")

            if in_eod:
                if not self._eod_done:
                    flat_fills = _flatten_all_positions(self.ledger, prices)
                    self.risk.pause_entries()
                    self._eod_done = True
                    self._write_log(f"EOD_FLATTEN fills={len(flat_fills)} entries paused")
                    self.last_decisions = [{
                        "code": "EOD_FLATTEN",
                        "message": "EOD flatten window — positions closed, entries paused",
                        "allow": False,
                    }]
                    await event_bus.publish(self.robot_id, "decision", {
                        "code": "EOD_FLATTEN",
                        "fills": len(flat_fills),
                    })
                eq = self.ledger.mark_equity(prices) if self.ledger else self.virtual_capital
                self.last_cycle_at = now
                self._equity_curve.append({
                    "time": now.isoformat(),
                    "equity": round(eq, 2),
                    "cycle": self.cycle_number,
                })
                self._write_log(
                    f"CYCLE #{self.cycle_number} by={triggered_by} equity={eq:.2f} EOD_HOLD"
                )
                await self._persist_skip_cycle(
                    cycle_number=self.cycle_number,
                    triggered_by=triggered_by,
                    skip_reason="EOD_HOLD",
                    message="EOD hold — новые входы приостановлены",
                    started_at=cycle_started_at,
                    equity=eq,
                )
                skip_scan = build_session_skip_scan(
                    self.universe, prices,
                    code="EOD_HOLD",
                    message="EOD hold — новые входы приостановлены",
                    candle_history=self.candle_history,
                )
                self._set_ticker_scan(skip_scan, at=now)
                await event_bus.publish(self.robot_id, "cycle", {
                    "cycleNumber": self.cycle_number,
                    "equity": eq,
                    "signals": 0,
                    "mode": self._mode,
                    "eodHold": True,
                    "triggeredBy": triggered_by,
                    "stage": "skipped",
                    "skipReason": "EOD_HOLD",
                    "tickerScan": skip_scan,
                    **self._cycle_positions_payload(),
                })
                await self._set_stage("skipped", skip_reason="EOD_HOLD")
                return

            if not is_within_trading_session(self._parsed.core.schedule):
                eq = self.ledger.mark_equity(prices) if self.ledger else self.virtual_capital
                self.last_cycle_at = now
                self._equity_curve.append({
                    "time": now.isoformat(),
                    "equity": round(eq, 2),
                    "cycle": self.cycle_number,
                })
                self._write_log(
                    f"CYCLE #{self.cycle_number} by={triggered_by} equity={eq:.2f} OUTSIDE_SESSION"
                )
                await self._persist_skip_cycle(
                    cycle_number=self.cycle_number,
                    triggered_by=triggered_by,
                    skip_reason="OUTSIDE_SESSION",
                    message="Outside trading schedule — strategy not evaluated",
                    started_at=cycle_started_at,
                    equity=eq,
                )
                self.last_decisions = [{
                    "code": "OUTSIDE_SESSION",
                    "message": "Outside trading schedule — strategy not evaluated",
                    "allow": False,
                }]
                skip_scan = build_session_skip_scan(
                    self.universe, prices,
                    code="OUTSIDE_SESSION",
                    message="Вне торговой сессии — стратегия не оценивалась",
                    candle_history=self.candle_history,
                )
                self._set_ticker_scan(skip_scan, at=now)
                await event_bus.publish(self.robot_id, "cycle", {
                    "cycleNumber": self.cycle_number,
                    "equity": eq,
                    "signals": 0,
                    "mode": self._mode,
                    "outsideSession": True,
                    "triggeredBy": triggered_by,
                    "stage": "skipped",
                    "skipReason": "OUTSIDE_SESSION",
                    "tickerScan": skip_scan,
                    **self._cycle_positions_payload(),
                })
                await self._set_stage("skipped", skip_reason="OUTSIDE_SESSION")
                return

            flow = None
            if self._parsed.strategy.archetype == "scalper":
                flow = self.order_flow.snapshots(self.universe, now=now)

            # Keep trading adopted broker positions even if screener dropped them
            cycle_universe = list(self.universe)
            if self.ledger:
                for t in self.ledger.positions:
                    tu = str(t).upper()
                    if tu and tu not in {x.upper() for x in cycle_universe}:
                        cycle_universe.append(tu)

            # Scalper entries only on price_tick; poll still runs exits via cycle
            result = await run_trading_cycle(
                robot_id=self.robot_id,
                user_id=self.user_id,
                config=self._parsed,
                universe=cycle_universe,
                ledger=self.ledger,
                risk=self.risk,
                prices=prices,
                mark_prices=dict(self.last_prices),
                candle_history=self.candle_history,
                session_id=self.robot_id,
                cycle_number=self.cycle_number,
                triggered_by=triggered_by,
                allow_short=self._allow_short,
                execution=self.execution,
                order_flow=flow,
                ws_healthy=self.ws_healthy,
                action_log=self._action_log,
                on_stage=self._set_stage,
                audit_session_id=self._audit_session_id,
                cycle_started_at=cycle_started_at,
            )
            self._fire_audit_persist(result.get("auditBundle"))
            self.last_decisions = result.get("decisions") or []
            self._set_ticker_scan(result.get("tickerScan") or [], at=now)
            self.last_cycle_at = now
            fills_n = len(result.get("fills") or [])
            eq = self.ledger.mark_equity(prices)
            # Live: resync shadow ledger from broker after fills so SL/TP & equity stay sane
            if (
                self._mode == "live"
                and self._broker is not None
                and self.execution
                and self.execution.account_id
                and fills_n > 0
            ):
                rec = await reconcile_from_broker(
                    robot_id=self.robot_id,
                    broker=self._broker,
                    account_id=self.execution.account_id,
                    ledger=self.ledger,
                    instrument_map=self._instrument_map,
                    universe=self.universe,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    extra_tickers=set(self.ledger.positions.keys()) if self.ledger else None,
                )
                self._last_reconcile_at = asyncio.get_running_loop().time()
                self._reconcile_ok = rec.ok
                if rec.ok:
                    eq = self.ledger.mark_equity(prices)
                elif rec.error:
                    self._write_log(f"WARN post-cycle reconcile: {rec.error}")
            self._equity_curve.append({
                "time": now.isoformat(),
                "equity": round(eq, 2),
                "cycle": self.cycle_number,
            })
            sig_n = int(result.get("signals") or 0)
            self._write_log(
                f"CYCLE #{self.cycle_number} by={triggered_by} equity={eq:.2f} "
                f"signals={sig_n} fills={fills_n} positions={len(self.ledger.positions)}"
            )
            if self.risk.session_state.halt_session:
                self._write_log("HALT session — risk hard stop")
            elif not self.risk.session_state.accept_new_entries:
                self._write_log("ENTRIES paused by risk")
            await self._set_stage("done")
            await self._set_stage("idle", publish=False)
