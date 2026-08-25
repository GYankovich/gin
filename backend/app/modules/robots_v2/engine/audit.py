"""Persistent audit store for robots v2 trading sessions."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class AuditSignalRow:
    ticker: str
    side: str
    kind: str
    reason: str = ""
    price: float | None = None
    entry_price: float | None = None
    delta_pct: float | None = None


@dataclass
class AuditDecisionRow:
    stage: str
    outcome: str
    code: str
    message: str = ""
    ticker: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditExecutionRow:
    ticker: str
    side: str
    kind: str
    quantity: int
    price: float
    status: str
    mode: str
    pnl: float = 0.0
    broker_order_id: str | None = None
    reject_reason: str | None = None
    order_type: str = "MARKET"


@dataclass
class AuditCycleBundle:
    cycle_id: UUID
    session_id: UUID
    robot_id: int
    cycle_number: int
    triggered_by: str
    started_at: datetime
    finished_at: datetime
    status: str = "ok"
    skip_reason: str | None = None
    equity: float | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    signals: list[AuditSignalRow] = field(default_factory=list)
    decisions: list[AuditDecisionRow] = field(default_factory=list)
    executions: list[AuditExecutionRow] = field(default_factory=list)


def _schema() -> str:
    return getattr(settings, "DB_SCHEMA", None) or "public"


def _json(v: Any) -> str:
    return json.dumps(v or {}, ensure_ascii=False, default=str)


class AuditStore:
    """Sync DB writer — call via asyncio.to_thread from the session loop."""

    def __init__(self, db: Session | None = None) -> None:
        self._own_db = db is None
        self._db = db or SessionLocal()
        self._schema = _schema()

    def close(self) -> None:
        if self._own_db:
            self._db.close()

    def start_session(
        self,
        *,
        robot_id: int,
        mode: str,
        virtual_capital: float | None,
        account_id: str | None,
        started_at: datetime | None = None,
    ) -> UUID:
        sid = uuid4()
        ts = started_at or datetime.now(timezone.utc)
        self._db.execute(
            text(f"""
                INSERT INTO {self._schema}.robots_v2_sessions
                    (id, robot_id, mode, virtual_capital, account_id, started_at)
                VALUES
                    (:id, :robot_id, :mode, :virtual_capital, :account_id, :started_at)
            """),
            {
                "id": sid,
                "robot_id": robot_id,
                "mode": mode,
                "virtual_capital": virtual_capital,
                "account_id": account_id,
                "started_at": ts,
            },
        )
        self._db.commit()
        return sid

    def end_session(
        self,
        session_id: UUID,
        *,
        stop_reason: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        self._db.execute(
            text(f"""
                UPDATE {self._schema}.robots_v2_sessions
                SET ended_at = :ended_at, stop_reason = :stop_reason
                WHERE id = :id
            """),
            {
                "id": session_id,
                "ended_at": ended_at or datetime.now(timezone.utc),
                "stop_reason": stop_reason,
            },
        )
        self._db.commit()

    def reconcile_resting_orders(
        self,
        *,
        robot_id: int,
        executions: list[AuditExecutionRow],
        open_broker_order_ids: set[str],
        stop_reason: str = "session_stop_sync",
    ) -> int:
        """Close stale audit resting rows; apply terminal states from final broker sync."""
        sch = self._schema
        now = datetime.now(timezone.utc)
        updated = 0

        for ex in executions:
            if not ex.broker_order_id:
                continue
            if ex.status not in ("filled", "cancelled", "canceled", "rejected"):
                continue
            terminal = "cancelled" if ex.status in ("cancelled", "canceled") else ex.status
            upd = self._db.execute(
                text(f"""
                    UPDATE {sch}.robots_v2_orders
                    SET status = :status,
                        price = COALESCE(:price, price),
                        quantity = :quantity,
                        reject_reason = :reject_reason
                    WHERE robot_id = :robot_id
                      AND broker_order_id = :broker_order_id
                      AND status IN ('resting', 'submitted')
                    RETURNING id
                """),
                {
                    "status": terminal,
                    "price": ex.price,
                    "quantity": ex.quantity,
                    "reject_reason": ex.reject_reason if terminal != "filled" else None,
                    "robot_id": robot_id,
                    "broker_order_id": ex.broker_order_id,
                },
            ).fetchone()
            if upd is None:
                continue
            updated += 1
            if ex.status == "filled" and ex.quantity > 0 and ex.price > 0:
                self._db.execute(
                    text(f"""
                        INSERT INTO {sch}.robots_v2_fills
                            (id, order_id, robot_id, ticker, side, quantity, price, pnl, commission, kind, filled_at)
                        SELECT :id, :order_id, :robot_id, :ticker, :side, :quantity, :price, :pnl, NULL, :kind, :filled_at
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {sch}.robots_v2_fills f WHERE f.order_id = :order_id
                        )
                    """),
                    {
                        "id": uuid4(),
                        "order_id": upd[0],
                        "robot_id": robot_id,
                        "ticker": ex.ticker.upper(),
                        "side": ex.side.upper(),
                        "quantity": ex.quantity,
                        "price": ex.price,
                        "pnl": ex.pnl,
                        "kind": ex.kind,
                        "filled_at": now,
                    },
                )

        open_ids = [str(x).strip() for x in open_broker_order_ids if str(x).strip()]
        stale_params: dict[str, Any] = {
            "robot_id": robot_id,
            "reason": stop_reason,
        }
        if open_ids:
            stale_sql = f"""
                UPDATE {sch}.robots_v2_orders
                SET status = 'cancelled', reject_reason = :reason
                WHERE robot_id = :robot_id
                  AND status IN ('resting', 'submitted')
                  AND (broker_order_id IS NULL OR NOT (broker_order_id = ANY(:open_ids)))
                RETURNING id
            """
            stale_params["open_ids"] = open_ids
        else:
            stale_sql = f"""
                UPDATE {sch}.robots_v2_orders
                SET status = 'cancelled', reject_reason = :reason
                WHERE robot_id = :robot_id
                  AND status IN ('resting', 'submitted')
                RETURNING id
            """
        stale_rows = self._db.execute(text(stale_sql), stale_params).fetchall()
        updated += len(stale_rows)
        self._db.commit()
        return updated

    def persist_cycle(self, bundle: AuditCycleBundle) -> None:
        sch = self._schema
        self._db.execute(
            text(f"""
                INSERT INTO {sch}.robots_v2_cycles
                    (id, session_id, robot_id, cycle_number, triggered_by,
                     started_at, finished_at, status, skip_reason, equity, stats)
                VALUES
                    (:id, :session_id, :robot_id, :cycle_number, :triggered_by,
                     :started_at, :finished_at, :status, :skip_reason, :equity, CAST(:stats AS jsonb))
            """),
            {
                "id": bundle.cycle_id,
                "session_id": bundle.session_id,
                "robot_id": bundle.robot_id,
                "cycle_number": bundle.cycle_number,
                "triggered_by": bundle.triggered_by,
                "started_at": bundle.started_at,
                "finished_at": bundle.finished_at,
                "status": bundle.status,
                "skip_reason": bundle.skip_reason,
                "equity": bundle.equity,
                "stats": _json(bundle.stats),
            },
        )

        for sig in bundle.signals:
            self._db.execute(
                text(f"""
                    INSERT INTO {sch}.robots_v2_signals
                        (id, cycle_id, robot_id, ticker, side, kind, reason, price, entry_price, delta_pct, created_at)
                    VALUES
                        (:id, :cycle_id, :robot_id, :ticker, :side, :kind, :reason, :price, :entry_price, :delta_pct,
                         :created_at)
                """),
                {
                    "id": uuid4(),
                    "cycle_id": bundle.cycle_id,
                    "robot_id": bundle.robot_id,
                    "ticker": sig.ticker.upper(),
                    "side": sig.side.upper(),
                    "kind": sig.kind,
                    "reason": sig.reason,
                    "price": sig.price,
                    "entry_price": sig.entry_price,
                    "delta_pct": sig.delta_pct,
                    "created_at": bundle.finished_at,
                },
            )

        for dec in bundle.decisions:
            self._db.execute(
                text(f"""
                    INSERT INTO {sch}.robots_v2_decisions
                        (id, cycle_id, robot_id, stage, outcome, code, message, ticker, context, created_at)
                    VALUES
                        (:id, :cycle_id, :robot_id, :stage, :outcome, :code, :message, :ticker,
                         CAST(:context AS jsonb), :created_at)
                """),
                {
                    "id": uuid4(),
                    "cycle_id": bundle.cycle_id,
                    "robot_id": bundle.robot_id,
                    "stage": dec.stage,
                    "outcome": dec.outcome,
                    "code": dec.code,
                    "message": dec.message,
                    "ticker": dec.ticker.upper() if dec.ticker else None,
                    "context": _json(dec.context),
                    "created_at": bundle.finished_at,
                },
            )

        for ex in bundle.executions:
            order_id = uuid4()
            order_type = str(ex.order_type or "MARKET").upper()
            if order_type not in ("MARKET", "LIMIT"):
                order_type = "MARKET"

            # If a resting LIMIT later fills/cancels, upgrade the existing audit row.
            updated_existing = False
            if ex.broker_order_id and ex.status in ("filled", "cancelled", "canceled", "rejected"):
                terminal = "cancelled" if ex.status in ("cancelled", "canceled") else ex.status
                upd = self._db.execute(
                    text(f"""
                        UPDATE {sch}.robots_v2_orders
                        SET status = :status,
                            price = COALESCE(:price, price),
                            quantity = :quantity,
                            reject_reason = :reject_reason
                        WHERE robot_id = :robot_id
                          AND broker_order_id = :broker_order_id
                          AND status IN ('resting', 'submitted')
                        RETURNING id
                    """),
                    {
                        "status": terminal,
                        "price": ex.price,
                        "quantity": ex.quantity,
                        "reject_reason": ex.reject_reason if terminal != "filled" else None,
                        "robot_id": bundle.robot_id,
                        "broker_order_id": ex.broker_order_id,
                    },
                ).fetchone()
                if upd is not None:
                    order_id = upd[0]
                    updated_existing = True

            if not updated_existing:
                self._db.execute(
                    text(f"""
                        INSERT INTO {sch}.robots_v2_orders
                            (id, cycle_id, robot_id, ticker, side, kind, quantity, price, status, mode,
                             broker_order_id, reject_reason, submitted_at, order_type)
                        VALUES
                            (:id, :cycle_id, :robot_id, :ticker, :side, :kind, :quantity, :price, :status, :mode,
                             :broker_order_id, :reject_reason, :submitted_at, :order_type)
                    """),
                    {
                        "id": order_id,
                        "cycle_id": bundle.cycle_id,
                        "robot_id": bundle.robot_id,
                        "ticker": ex.ticker.upper(),
                        "side": ex.side.upper(),
                        "kind": ex.kind,
                        "quantity": ex.quantity,
                        "price": ex.price,
                        "status": ex.status,
                        "mode": ex.mode,
                        "broker_order_id": ex.broker_order_id,
                        "reject_reason": ex.reject_reason,
                        "submitted_at": bundle.finished_at,
                        "order_type": order_type,
                    },
                )
            if ex.status == "filled" and ex.quantity > 0 and ex.price > 0:
                self._db.execute(
                    text(f"""
                        INSERT INTO {sch}.robots_v2_fills
                            (id, order_id, robot_id, ticker, side, quantity, price, pnl, commission, kind, filled_at)
                        VALUES
                            (:id, :order_id, :robot_id, :ticker, :side, :quantity, :price, :pnl, :commission,
                             :kind, :filled_at)
                    """),
                    {
                        "id": uuid4(),
                        "order_id": order_id,
                        "robot_id": bundle.robot_id,
                        "ticker": ex.ticker.upper(),
                        "side": ex.side.upper(),
                        "quantity": ex.quantity,
                        "price": ex.price,
                        "pnl": ex.pnl,
                        "commission": None,
                        "kind": ex.kind,
                        "filled_at": bundle.finished_at,
                    },
                )

        self._db.commit()


def signal_row_from_eval(
    signal: Any,
    *,
    prices: dict[str, float],
    positions: dict[str, Any],
    order_flow: dict[str, Any] | None,
) -> AuditSignalRow:
    """Build audit signal row with entry price (open position) and order-flow delta."""
    ticker = str(getattr(signal, "secid", None) or "").upper()
    flow = (order_flow or {}).get(ticker)
    delta_pct: float | None = None
    if flow is not None:
        raw = getattr(flow, "delta_pct", None)
        if raw is None and isinstance(flow, dict):
            raw = flow.get("deltaPct", flow.get("delta_pct"))
        if raw is not None:
            delta_pct = float(raw)

    entry_price: float | None = None
    pos = positions.get(ticker)
    if pos is not None:
        qty = float(getattr(pos, "quantity", 0) or 0)
        if qty > 0:
            entry_price = float(getattr(pos, "avg_entry_price", 0) or 0) or None

    sig_px = getattr(signal, "price_at_signal", None)
    price = float(sig_px or prices.get(ticker, 0) or 0) or None

    return AuditSignalRow(
        ticker=ticker,
        side=str(getattr(signal, "side", None) or ""),
        kind="signal",
        reason=str(getattr(signal, "reason", None) or ""),
        price=price,
        entry_price=entry_price,
        delta_pct=delta_pct,
    )


def decision_row_from_dict(raw: dict[str, Any], *, stage: str = "risk") -> AuditDecisionRow:
    allow = raw.get("allow")
    if allow is False:
        outcome = "deny"
    elif raw.get("code") == "NO_SIGNAL":
        outcome = "skip"
    else:
        outcome = "allow"
    ticker = raw.get("ticker")
    ctx = {k: v for k, v in raw.items() if k not in ("code", "message", "allow", "ticker")}
    return AuditDecisionRow(
        stage=stage,
        outcome=outcome,
        code=str(raw.get("code") or "UNKNOWN"),
        message=str(raw.get("message") or ""),
        ticker=str(ticker).upper() if ticker else None,
        context=ctx,
    )


def execution_row_from_result(result: Any, *, kind: str | None = None) -> AuditExecutionRow:
    k = kind or getattr(result, "kind", None) or "entry"
    status = str(getattr(result, "status", None) or "rejected")
    reason = getattr(result, "reason", None)
    meta = getattr(result, "meta", None) or {}
    order_type = str(
        meta.get("orderType")
        or meta.get("order_type")
        or getattr(result, "order_type", None)
        or ("LIMIT" if status == "resting" else "MARKET")
    ).upper()
    if order_type not in ("MARKET", "LIMIT"):
        order_type = "MARKET"
    reject = None
    if status in ("rejected", "cancelled", "canceled"):
        reject = str(reason or status)
    return AuditExecutionRow(
        ticker=str(getattr(result, "ticker", None) or "").upper(),
        side=str(getattr(result, "side", None) or "").upper(),
        kind=k,
        quantity=int(getattr(result, "quantity", None) or 0),
        price=float(getattr(result, "price", None) or 0),
        status=status,
        mode=str(getattr(result, "mode", None) or "paper"),
        pnl=float(getattr(result, "pnl", None) or 0),
        broker_order_id=getattr(result, "broker_order_id", None),
        reject_reason=reject,
        order_type=order_type,
    )


async def audit_start_session(**kwargs: Any) -> UUID | None:
    try:
        def _run() -> UUID:
            store = AuditStore()
            try:
                return store.start_session(**kwargs)
            finally:
                store.close()

        return await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("audit start_session failed robot=%s: %s", kwargs.get("robot_id"), exc)
        return None


async def audit_end_session(session_id: UUID | None, *, stop_reason: str | None = None) -> None:
    if session_id is None:
        return
    try:
        def _run() -> None:
            store = AuditStore()
            try:
                store.end_session(session_id, stop_reason=stop_reason)
            finally:
                store.close()

        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("audit end_session failed session=%s: %s", session_id, exc)


async def audit_reconcile_resting_orders(
    *,
    robot_id: int,
    sync_results: list[Any],
    open_broker_order_ids: set[str],
    stop_reason: str = "session_stop_sync",
) -> int:
    """Finalize audit order rows when a live session stops."""
    rows = [
        execution_row_from_result(r, kind=getattr(r, "kind", None) or "exit_sl_tp")
        for r in sync_results
    ]

    def _run() -> int:
        store = AuditStore()
        try:
            return store.reconcile_resting_orders(
                robot_id=robot_id,
                executions=rows,
                open_broker_order_ids=open_broker_order_ids,
                stop_reason=stop_reason,
            )
        finally:
            store.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("audit reconcile_resting_orders failed robot=%s: %s", robot_id, exc)
        return 0


async def audit_persist_cycle(bundle: AuditCycleBundle) -> None:
    try:
        def _run() -> None:
            store = AuditStore()
            try:
                store.persist_cycle(bundle)
            finally:
                store.close()

        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning(
            "audit persist_cycle failed robot=%s cycle=%s: %s",
            bundle.robot_id,
            bundle.cycle_number,
            exc,
        )
