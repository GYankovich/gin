# app/modules/robots/service.py
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime, timezone, timedelta, date, time
import json
import threading
import time as time_mod
import httpx
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.modules.bybit.http_client import BybitApiError
from app.modules.tinvest.token_service import token_service
from app.modules.tinvest.service import tinvest_service
from app.core.config import settings
from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.logging_config import get_logger
from app.modules.moex.http_gate import moex_http_acquire
from app.modules.moex.securities_listing_archive import load_listing_board_row_map
from app.modules.recommendations.backtest_analytics import (
    bybit_metrics,
    exit_reason_metrics,
    general_metrics,
    moex_metrics,
    universe_metrics
)
from . import queries, schemas
from app.modules.dictionary import queries as dict_queries

logger = get_logger(__name__)

_MOEX_RETRYABLE_HTTP_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ProtocolError
)

_HB_CANCEL_LOCK = threading.Lock()
_HB_CANCEL_FLAGS: Dict[int, bool] = {}


def signal_history_backtest_cancel(run_id: int) -> None:
    """Мгновенный сигнал воркеру (не ждёт опроса БД)."""
    with _HB_CANCEL_LOCK:
        _HB_CANCEL_FLAGS[int(run_id)] = True


def is_history_backtest_cancelled(run_id: int) -> bool:
    with _HB_CANCEL_LOCK:
        return bool(_HB_CANCEL_FLAGS.get(int(run_id)))


def clear_history_backtest_cancel(run_id: int) -> None:
    with _HB_CANCEL_LOCK:
        _HB_CANCEL_FLAGS.pop(int(run_id), None)


def _clear_backtest_run_tracking(run_id: int) -> None:
    clear_history_backtest_cancel(run_id)
    from app.modules.robots.backtest_progress import clear_backtest_progress_runtime

    clear_backtest_progress_runtime(run_id)


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


async def _resolve_robot_account_id(broker: Any, account_id: Optional[str]) -> Optional[str]:
    """Подбор account_id из списка счетов брокера (как в trading session)."""
    preferred_statuses = {"open", "account_status_open"}
    preferred_types = {"broker", "account_type_tinkoff", "tinkoff", "unified"}

    def _norm(v: Any) -> str:
        return str(v or "").strip()

    try:
        accounts = await broker.get_accounts()
    except Exception:
        accounts = []

    known_ids = {_norm(a.get("id")) for a in accounts if _norm(a.get("id"))}
    aid = _norm(account_id)

    # Legacy ByBit id → prefer matching UNIFIED account from facade list.
    if aid.upper() == "BYBIT_UNIFIED" and accounts:
        for acc in accounts:
            acc_id = _norm(acc.get("id"))
            acc_type = _norm(acc.get("type")).upper()
            if acc_type == "UNIFIED" or acc_id.endswith(":UNIFIED"):
                return acc_id

    if aid and (not known_ids or aid in known_ids):
        return aid
    if not accounts:
        return aid or None

    chosen = None
    for acc in accounts:
        status = _norm(acc.get("status")).lower()
        acc_type = _norm(acc.get("type")).lower()
        if status in preferred_statuses and acc_type in preferred_types:
            chosen = acc
            break
    if not chosen:
        for acc in accounts:
            acc_type = _norm(acc.get("type")).upper()
            acc_id = _norm(acc.get("id"))
            if acc_type == "UNIFIED" or acc_id.endswith(":UNIFIED"):
                chosen = acc
                break
    if not chosen:
        for acc in accounts:
            status = _norm(acc.get("status")).lower()
            if status in preferred_statuses:
                chosen = acc
                break
    if not chosen:
        chosen = accounts[0]
    candidate = _norm((chosen or {}).get("id"))
    return candidate or None


def _position_row_key(pos: Dict[str, Any]) -> str:
    figi = str(pos.get("figi") or "").strip().upper()
    if figi:
        return figi
    uid = str(pos.get("instrument_uid") or pos.get("position_uid") or "").strip()
    if uid:
        return uid
    ticker = str(pos.get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    return ""


def _instrument_type_label_map(db: Session) -> Dict[str, str]:
    """PORTFOLIO_POSITIONS.INSTRUMENT_TYPE → {string_value → name}."""
    out: Dict[str, str] = {}
    try:
        rows = db.execute(
            text(
                f"""
                SELECT string_value, name
                FROM dictionary
                WHERE table_name = 'PORTFOLIO_POSITIONS'
                  AND column_name = 'INSTRUMENT_TYPE'
                  AND hide_from_ui = 0
                """
            )
        ).fetchall()
    except Exception as exc:
        logger.debug("instrument type labels load failed: %s", exc)
        return out
    for string_value, name in rows:
        key = str(string_value or "").strip().lower()
        label = str(name or "").strip()
        if key and label:
            out[key] = label
    return out


def _normalize_portfolio_positions(
    raw: List[Dict[str, Any]],
    *,
    type_names: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    labels = type_names or {}
    out: List[Dict[str, Any]] = []
    for pos in raw or []:
        row_key = _position_row_key(pos)
        if not row_key:
            continue
        qty = _to_float_qty(pos.get("quantity"))
        ticker = str(pos.get("ticker") or "").strip()
        figi = str(pos.get("figi") or "").strip().upper() or row_key
        side = str(pos.get("side") or "").strip()
        if not side:
            side = "Sell" if qty < 0 else "Buy" if qty > 0 else ""
        instrument_type = str(pos.get("instrument_type") or "").strip()
        type_key = instrument_type.lower()
        out.append(
            {
                "id": row_key,
                "figi": figi,
                "ticker": ticker or figi,
                "instrument_type": instrument_type,
                "type_name": labels.get(type_key) or instrument_type or None,
                "quantity": qty,
                "side": side or None,
                "average_position_price": pos.get("average_position_price"),
                "current_price": pos.get("current_price"),
                "expected_yield": pos.get("expected_yield"),
                "blocked": bool(pos.get("blocked")),
            }
        )
    # Only non-zero holdings that exist on the broker account.
    out = [p for p in out if abs(float(p.get("quantity") or 0)) > 1e-12]
    out.sort(key=lambda p: (str(p.get("ticker") or ""), str(p.get("figi") or "")))
    return out


def _is_synthetic_broker_order_id(order_id: Any) -> bool:
    """True for non-exchange ids like broker_import:XLMUSDT:buy (position seeds)."""
    oid = str(order_id or "").strip().lower()
    return oid.startswith("broker_import:")


def _is_db_working_order(row: Dict[str, Any]) -> bool:
    """Resting / partial order (not yet filled / cancelled)."""
    oid = str(row.get("order_id") or "").strip()
    if _is_synthetic_broker_order_id(oid):
        return False
    st = str(row.get("status") or "").strip().lower()
    if st in {"pending", "new", "partial"}:
        return True
    if st in {"filled", "cancelled", "canceled", "rejected", "closed", "failed"}:
        return False
    if st != "open":
        return False
    # Legacy: unfilled "open" treated as resting.
    try:
        filled = float(row.get("filled_qty") if row.get("filled_qty") is not None else 0)
    except Exception:
        filled = 0.0
    return bool(oid) and filled <= 1e-12 and not str(oid).startswith("pending:")


def _split_db_orders(
    rows: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split portfolio_orders into active working vs history."""
    open_orders: List[Dict[str, Any]] = []
    order_history: List[Dict[str, Any]] = []
    for row in rows or []:
        if _is_synthetic_broker_order_id(row.get("order_id")):
            continue
        if _is_db_working_order(row):
            open_orders.append(row)
        else:
            order_history.append(row)
    return open_orders, order_history


def _map_broker_order_status_to_db(status: str, *, closing: bool = False) -> str:
    """Map ByBit raw / EXECUTION_REPORT_* statuses to robot_trades.status."""
    from app.modules.robots.trading.stages.stage6_orders import Stage6Orders

    raw = str(status or "").strip()
    if not raw:
        return "pending"
    if raw.startswith("EXECUTION_REPORT_"):
        return Stage6Orders.map_execution_status_to_trade_status(raw, closing=closing)
    key = raw.lower().replace(" ", "").replace("_", "")
    bybit_map = {
        "new": "pending",
        "created": "pending",
        "untriggered": "pending",
        "triggered": "pending",
        "active": "pending",
        "partiallyfilled": "partial",
        "partialfill": "partial",
        "filled": "open" if not closing else "closed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "deactivated": "cancelled",
        "rejected": "rejected",
    }
    if key in bybit_map:
        return bybit_map[key]
    # Already a DB status?
    if key in {"pending", "new", "partial", "open", "closed", "cancelled", "canceled", "rejected", "failed", "skipped"}:
        return "cancelled" if key == "canceled" else key
    return "pending"


def _broker_row_order_date(row: Dict[str, Any]) -> Optional[datetime]:
    from app.modules.portfolio.order_registry import parse_broker_order_date

    return parse_broker_order_date(
        row.get("created_at")
        or row.get("createdTime")
        or row.get("order_date")
        or row.get("updatedTime")
    )


def _broker_row_side(row: Dict[str, Any]) -> str:
    side = str(row.get("side") or "").strip().lower()
    if side in {"buy", "order_direction_buy"}:
        return "buy"
    if side in {"sell", "order_direction_sell"}:
        return "sell"
    return side or "buy"


def _broker_row_floats(row: Dict[str, Any]) -> tuple[float, float, Optional[float], Optional[float]]:
    try:
        qty = float(row.get("quantity") if row.get("quantity") is not None else row.get("qty") or 0)
    except Exception:
        qty = 0.0
    try:
        price = float(row.get("price") or 0)
    except Exception:
        price = 0.0
    filled = row.get("filled_qty")
    if filled is None:
        filled = row.get("cumExecQty")
    if filled is None:
        filled = row.get("lotsExecuted")
    try:
        filled_f = float(filled) if filled is not None else None
    except Exception:
        filled_f = None
    avg = row.get("avg_price")
    if avg is None:
        avg = row.get("avgPrice")
    if avg is None:
        avg = row.get("executedOrderPrice")
    try:
        avg_f = float(avg) if avg is not None else None
    except Exception:
        avg_f = None
    return qty, price, filled_f, avg_f


def _update_trade_row_by_order_id(
    db: Session,
    *,
    robot_id: int,
    order_id: str,
    status: str,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    filled_qty: Optional[float] = None,
    avg_price: Optional[float] = None,
    now: Optional[datetime] = None
) -> bool:
    """Legacy update for robot_trades (synthetic broker_import heal only)."""
    ts = now or datetime.now(timezone.utc)
    try:
        db.execute(
            text(
                f"""
                UPDATE robot_trades
                SET status = :status,
                    quantity = COALESCE(:quantity, quantity),
                    price = COALESCE(:price, price),
                    total_amount = CASE
                        WHEN :quantity IS NOT NULL AND :price IS NOT NULL THEN :quantity * :price
                        WHEN :quantity IS NOT NULL THEN :quantity * COALESCE(price, 0)
                        WHEN :price IS NOT NULL THEN COALESCE(quantity, 0) * :price
                        ELSE total_amount
                    END,
                    filled_quantity = COALESCE(:filled_quantity, filled_quantity),
                    avg_fill_price = COALESCE(:avg_fill_price, avg_fill_price),
                    updated_at = :now
                WHERE robot_id = :robot_id
                  AND order_id = :order_id
                """
            ),
            {
                "status": status,
                "quantity": quantity,
                "price": price if price is not None and price > 0 else None,
                "filled_quantity": filled_qty,
                "avg_fill_price": avg_price,
                "now": ts,
                "robot_id": int(robot_id),
                "order_id": order_id,
            }
        )
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(
            "sync order update failed robot_id=%s order_id=%s: %s",
            robot_id,
            order_id,
            exc
        )
        return False


async def _upsert_broker_open_orders_into_db(
    db: Session,
    *,
    robot_id: int,
    broker: Any,
    account_id: str,
    portfolio_account_id: Optional[int] = None,
    user_id: Optional[int] = None,
    broker_prefix: str = "bybit"
) -> Dict[str, Any]:
    """Upsert broker open orders into portfolio_orders."""
    from app.modules.portfolio.order_registry import (
        SOURCE_EXTERNAL,
        resolve_portfolio_account_pk,
        upsert_broker_order
    )

    get_orders = getattr(broker, "get_orders", None)
    empty = {"imported": 0, "upserted": 0, "skipped": 0, "open_order_ids": set()}
    if not callable(get_orders) or not account_id:
        return empty

    pa_id = portfolio_account_id
    if pa_id is None and user_id is not None:
        pa_id = resolve_portfolio_account_pk(
            db, user_id=int(user_id), broker_account_id=str(account_id)
        )
    if not pa_id:
        logger.warning(
            "upsert open orders: no portfolio_account_id robot_id=%s account=%s",
            robot_id,
            account_id
        )
        return empty

    try:
        raw_open = await get_orders(str(account_id))
    except Exception as exc:
        logger.warning("upsert open orders failed robot_id=%s: %s", robot_id, exc)
        return empty
    if not isinstance(raw_open, list):
        return empty

    imported = 0
    upserted = 0
    skipped = 0
    open_order_ids: set[str] = set()
    dirty = False

    for row in raw_open:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("order_id") or row.get("orderId") or "").strip()
        figi = str(row.get("figi") or row.get("symbol") or "").strip().upper()
        if not oid or not figi:
            continue
        open_order_ids.add(oid)
        exec_status = str(
            row.get("executionReportStatus") or row.get("status") or "New"
        )
        qty, price, filled_f, avg_f = _broker_row_floats(row)
        side = _broker_row_side(row)
        result = upsert_broker_order(
            db,
            portfolio_account_id=int(pa_id),
            order_id=oid,
            figi=figi,
            side=side,
            quantity=qty,
            status=exec_status,
            price=price if price > 0 else None,
            filled_qty=filled_f,
            avg_price=avg_f,
            source=SOURCE_EXTERNAL,
            robot_id=int(robot_id),
            order_date=_broker_row_order_date(row),
            commit=False,
            promote_filled=True,
            broker_prefix=broker_prefix
        )
        if result == "inserted":
            imported += 1
            dirty = True
        elif result == "updated":
            upserted += 1
            dirty = True
        else:
            skipped += 1

    if dirty:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return {"imported": 0, "upserted": 0, "skipped": skipped, "open_order_ids": open_order_ids}
    return {
        "imported": int(imported),
        "upserted": int(upserted),
        "skipped": int(skipped),
        "open_order_ids": open_order_ids,
        "portfolio_account_id": int(pa_id),
    }


async def _sync_working_trade_statuses_from_broker(
    db: Session,
    *,
    robot_id: int,
    broker: Any,
    account_id: str,
    working_rows: List[Dict[str, Any]],
    open_order_ids: Optional[set[str]] = None,
    portfolio_account_id: Optional[int] = None,
    broker_prefix: str = "bybit"
) -> Dict[str, int]:
    """Poll broker for working portfolio_orders not in open set; missing → cancelled."""
    from app.modules.portfolio.order_registry import upsert_broker_order

    if not working_rows or not account_id or not portfolio_account_id:
        return {"updated": 0, "cancelled": 0}
    get_state = getattr(broker, "get_order_state", None)
    if not callable(get_state):
        return {"updated": 0, "cancelled": 0}

    open_ids = open_order_ids or set()
    updated = 0
    cancelled = 0
    dirty = False

    for row in working_rows:
        oid = str(row.get("order_id") or "").strip()
        if not oid or _is_synthetic_broker_order_id(oid) or oid.startswith("pending:"):
            continue
        if oid in open_ids:
            continue
        try:
            state = await get_state(str(account_id), oid)
        except Exception as exc:
            logger.debug(
                "sync order status skipped robot_id=%s order_id=%s: %s",
                robot_id,
                oid,
                exc
            )
            continue
        if not isinstance(state, dict):
            continue

        stages = state.get("stages")
        missing = isinstance(stages, list) and len(stages) == 0 and not state.get("symbol")
        if missing:
            exec_status = "Cancelled"
            filled_f = None
            avg_f = None
        else:
            exec_status = str(
                state.get("executionReportStatus") or state.get("status") or ""
            )
            if not exec_status:
                exec_status = "Cancelled"
                filled_f = None
                avg_f = None
            else:
                try:
                    filled_qty = state.get("lotsExecuted")
                    if filled_qty is None:
                        filled_qty = state.get("filled_qty")
                    filled_f = float(filled_qty) if filled_qty is not None else None
                except Exception:
                    filled_f = None
                try:
                    avg_px = state.get("executedOrderPrice")
                    if avg_px is None:
                        avg_px = state.get("avg_price")
                    avg_f = float(avg_px) if avg_px is not None else None
                except Exception:
                    avg_f = None

        figi = str(row.get("figi") or state.get("symbol") or "").strip().upper()
        side = str(row.get("side") or "buy")
        result = upsert_broker_order(
            db,
            portfolio_account_id=int(portfolio_account_id),
            order_id=oid,
            figi=figi or "UNKNOWN",
            side=side,
            quantity=float(row.get("quantity") or 0),
            status=exec_status,
            filled_qty=filled_f,
            avg_price=avg_f,
            source="external",
            robot_id=int(robot_id),
            commit=False,
            promote_filled=True,
            broker_prefix=broker_prefix
        )
        if result in {"inserted", "updated"}:
            dirty = True
            updated += 1
            st_u = str(exec_status).upper()
            if "CANCEL" in st_u:
                cancelled += 1

    if dirty:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return {"updated": 0, "cancelled": 0}
    return {"updated": int(updated), "cancelled": int(cancelled)}


async def _apply_broker_history_statuses_to_db(
    db: Session,
    *,
    robot_id: int,
    broker: Any,
    account_id: str,
    portfolio_account_id: Optional[int] = None,
    insert_missing: bool = False,
    broker_prefix: str = "bybit"
) -> int:
    """Update known portfolio_orders from history; optionally insert missing (updater)."""
    from app.modules.portfolio.order_registry import (
        SOURCE_EXTERNAL,
        load_portfolio_orders,
        upsert_broker_order
    )

    get_hist = getattr(broker, "get_order_history", None)
    if not callable(get_hist) or not account_id or not portfolio_account_id:
        return 0
    try:
        raw_hist = await get_hist(str(account_id), limit=50)
    except TypeError:
        try:
            raw_hist = await get_hist(str(account_id))
        except Exception as exc:
            logger.warning("history status sync failed robot_id=%s: %s", robot_id, exc)
            return 0
    except Exception as exc:
        logger.warning("history status sync failed robot_id=%s: %s", robot_id, exc)
        return 0
    if not isinstance(raw_hist, list) or not raw_hist:
        return 0

    known = {
        str(o.get("order_id") or "").strip()
        for o in load_portfolio_orders(db, portfolio_account_id=int(portfolio_account_id), limit=200)
        if str(o.get("order_id") or "").strip()
    }

    updated = 0
    dirty = False
    for row in raw_hist:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("order_id") or row.get("orderId") or "").strip()
        if not oid:
            continue
        if not insert_missing and oid not in known:
            continue
        exec_status = str(row.get("executionReportStatus") or row.get("status") or "")
        if not exec_status:
            continue
        figi = str(row.get("figi") or row.get("symbol") or "").strip().upper()
        if not figi:
            continue
        qty, price, filled_f, avg_f = _broker_row_floats(row)
        side = _broker_row_side(row)
        result = upsert_broker_order(
            db,
            portfolio_account_id=int(portfolio_account_id),
            order_id=oid,
            figi=figi,
            side=side,
            quantity=qty,
            status=exec_status,
            price=price if price > 0 else None,
            filled_qty=filled_f,
            avg_price=avg_f,
            source=SOURCE_EXTERNAL,
            robot_id=int(robot_id),
            order_date=_broker_row_order_date(row),
            commit=False,
            promote_filled=True,
            broker_prefix=broker_prefix
        )
        if result in {"inserted", "updated"}:
            updated += 1
            dirty = True

    if dirty:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return 0
    return int(updated)


async def _heal_synthetic_broker_imports(
    db: Session,
    *,
    robot_id: int,
    broker: Any,
    account_id: str
) -> Dict[str, int]:
    """Fix broker_import:* rows in robot_trades only (not portfolio_orders)."""
    from app.modules.robots.trading.broker_position_sync import extract_account_position_meta

    rows = [
        o for o in _load_robot_trade_orders(db, robot_id)
        if _is_synthetic_broker_order_id(o.get("order_id"))
    ]
    if not rows or not account_id:
        return {"healed_open": 0, "healed_closed": 0}

    get_pf = getattr(broker, "get_portfolio", None)
    meta: Dict[str, Dict[str, Any]] = {}
    if callable(get_pf):
        try:
            pf = await get_pf(str(account_id))
            positions = list((pf or {}).get("positions") or []) if isinstance(pf, dict) else []
            meta = extract_account_position_meta(positions)
        except Exception as exc:
            logger.warning(
                "heal synthetic imports: portfolio failed robot_id=%s: %s",
                robot_id,
                exc
            )

    healed_open = 0
    healed_closed = 0
    now = datetime.now(timezone.utc)
    dirty = False
    for row in rows:
        figi = str(row.get("figi") or "").strip().upper()
        side = str(row.get("side") or "").strip().lower()
        try:
            qty = float(row.get("quantity") or 0)
        except Exception:
            qty = 0.0
        broker_row = meta.get(figi) if figi else None
        has_pos = False
        if broker_row:
            bq = float(broker_row.get("qty") or 0)
            if side in {"buy", "long"}:
                has_pos = bq > 1e-12
            elif side in {"sell", "short"}:
                has_pos = bq < -1e-12
            else:
                has_pos = abs(bq) > 1e-12
        if has_pos:
            fill_qty = abs(float(broker_row.get("qty") or qty))
            avg = float(broker_row.get("avg_price") or row.get("price") or 0) or None
            ok = _update_trade_row_by_order_id(
                db,
                robot_id=int(robot_id),
                order_id=str(row.get("order_id")),
                status="open",
                quantity=fill_qty if fill_qty > 0 else None,
                filled_qty=fill_qty if fill_qty > 0 else qty,
                avg_price=avg,
                now=now
            )
            if ok:
                healed_open += 1
                dirty = True
        else:
            ok = _update_trade_row_by_order_id(
                db,
                robot_id=int(robot_id),
                order_id=str(row.get("order_id")),
                status="closed",
                filled_qty=qty if qty > 0 else None,
                now=now
            )
            if ok:
                healed_closed += 1
                dirty = True

    if dirty:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return {"healed_open": 0, "healed_closed": 0}
    return {"healed_open": int(healed_open), "healed_closed": int(healed_closed)}


async def _reconcile_robot_orders_with_broker(
    db: Session,
    *,
    robot_id: int,
    broker: Any,
    account_id: str,
    user_id: Optional[int] = None,
    insert_history: bool = False
) -> Dict[str, int]:
    """Two-way sync into portfolio_orders; heal seeds on robot_trades."""
    from app.modules.portfolio.order_registry import (
        load_portfolio_orders,
        resolve_portfolio_account_pk
    )
    from app.modules.robots.trading.brokers.routing import normalize_broker_type

    broker_prefix = "bybit"
    try:
        bt = normalize_broker_type(str(getattr(broker, "broker_type", None) or "bybit"))
        broker_prefix = "tinvest" if bt == "tinvest" else "bybit"
    except Exception:
        broker_prefix = "bybit"

    healed = await _heal_synthetic_broker_imports(
        db,
        robot_id=robot_id,
        broker=broker,
        account_id=account_id
    )

    pa_id: Optional[int] = None
    if user_id is not None:
        pa_id = resolve_portfolio_account_pk(
            db, user_id=int(user_id), broker_account_id=str(account_id)
        )

    upsert = await _upsert_broker_open_orders_into_db(
        db,
        robot_id=robot_id,
        broker=broker,
        account_id=account_id,
        portfolio_account_id=pa_id,
        user_id=user_id,
        broker_prefix=broker_prefix
    )
    if pa_id is None:
        pa_id = upsert.get("portfolio_account_id")
    open_ids = upsert.get("open_order_ids") or set()
    working: List[Dict[str, Any]] = []
    if pa_id:
        working = [
            o for o in load_portfolio_orders(db, portfolio_account_id=int(pa_id), limit=200)
            if _is_db_working_order(o) and str(o.get("order_id") or "").strip()
            and not str(o.get("order_id") or "").startswith("pending:")
        ]
    refreshed = await _sync_working_trade_statuses_from_broker(
        db,
        robot_id=robot_id,
        broker=broker,
        account_id=account_id,
        working_rows=working,
        open_order_ids=open_ids if isinstance(open_ids, set) else set(open_ids),
        portfolio_account_id=int(pa_id) if pa_id else None,
        broker_prefix=broker_prefix
    )
    hist_updated = await _apply_broker_history_statuses_to_db(
        db,
        robot_id=robot_id,
        broker=broker,
        account_id=account_id,
        portfolio_account_id=int(pa_id) if pa_id else None,
        insert_missing=bool(insert_history),
        broker_prefix=broker_prefix
    )
    updated = (
        int(upsert.get("upserted") or 0)
        + int(refreshed.get("updated") or 0)
        + int(hist_updated)
        + int(healed.get("healed_open") or 0)
        + int(healed.get("healed_closed") or 0)
    )
    return {
        "updated": updated,
        "imported": int(upsert.get("imported") or 0),
        "upserted": int(upsert.get("upserted") or 0),
        "cancelled": int(refreshed.get("cancelled") or 0),
        "history_updated": int(hist_updated),
        "healed_open": int(healed.get("healed_open") or 0),
        "healed_closed": int(healed.get("healed_closed") or 0),
        "portfolio_account_id": int(pa_id) if pa_id else None,
    }


def _load_robot_trade_orders(db: Session, robot_id: int) -> List[Dict[str, Any]]:
    """Legacy loader for robot_trades (heal synthetic seeds)."""
    orders_q = f"""
        SELECT id, figi, side, quantity, price, order_id, status, created_at,
               filled_quantity, avg_fill_price, updated_at
        FROM robot_trades
        WHERE robot_id = :robot_id
        ORDER BY created_at DESC
        LIMIT 100
    """
    orders_rows = db.execute(text(orders_q), {"robot_id": robot_id}).fetchall()
    return [
        {
            "id": int(r[0]),
            "figi": str(r[1]),
            "side": str(r[2]),
            "quantity": float(r[3] or 0),
            "price": float(r[4] or 0),
            "order_id": r[5],
            "status": str(r[6]),
            "created_at": r[7],
            "filled_qty": float(r[8]) if r[8] is not None else None,
            "avg_price": float(r[9]) if r[9] is not None else None,
            "updated_at": r[10],
        }
        for r in orders_rows
    ]


def _load_live_account_orders(
    db: Session,
    *,
    user_id: int,
    broker_account_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Live orders from portfolio_orders for the robot's broker account."""
    from app.modules.portfolio.order_registry import (
        load_portfolio_orders,
        resolve_portfolio_account_pk
    )

    if not broker_account_id:
        return []
    pa_id = resolve_portfolio_account_pk(
        db,
        user_id=int(user_id),
        broker_account_id=str(broker_account_id),
        create_if_missing=False
    )
    if not pa_id:
        return []
    return load_portfolio_orders(db, portfolio_account_id=int(pa_id), limit=100)


def _load_portfolio_positions_from_db(
        db: Session,
        user_id: int,
        external_account_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Последний сохранённый снимок портфеля (portfolio_updater / tinvest sync)."""
    if not external_account_id:
        return []
    q = f"""
        SELECT pp.figi, pp.ticker, pp.instrument_type, pp.quantity,
               pp.average_position_price, pp.current_price, pp.blocked, pp.instrument_uid
        FROM portfolio_positions pp
        JOIN portfolio_snapshots ps ON ps.id = pp.snapshot_id
        JOIN portfolio_accounts pa ON pa.id = ps.account_id
        WHERE pa.user_id = :user_id
          AND pa.account_id = :external_account_id
          AND ps.id = (
              SELECT ps2.id
              FROM portfolio_snapshots ps2
              JOIN portfolio_accounts pa2 ON pa2.id = ps2.account_id
              WHERE pa2.user_id = :user_id
                AND pa2.account_id = :external_account_id
              ORDER BY ps2.snapshot_date DESC, ps2.id DESC
              LIMIT 1
          )
        ORDER BY pp.ticker NULLS LAST, pp.figi NULLS LAST
    """
    rows = db.execute(
        text(q),
        {"user_id": int(user_id), "external_account_id": str(external_account_id)}
    ).fetchall()
    raw: List[Dict[str, Any]] = []
    for r in rows:
        raw.append(
            {
                "figi": r[0],
                "ticker": r[1],
                "instrument_type": r[2],
                "quantity": float(r[3] or 0),
                "average_position_price": {"decimal": float(r[4])} if r[4] is not None else None,
                "current_price": {"decimal": float(r[5])} if r[5] is not None else None,
                "blocked": bool(r[6]),
                "instrument_uid": r[7],
            }
        )
    return _normalize_portfolio_positions(raw, type_names=_instrument_type_label_map(db))


def _persist_robot_account_id(
        db: Session,
        robot_id: int,
        user_id: int,
        account_id: str
) -> None:
    # robots.config is JSON (not JSONB); cast both sides so COALESCE/jsonb_set type-check.
    db.execute(
        text(f"""
            UPDATE robots
            SET config = jsonb_set(
                    COALESCE(config::jsonb, '{{}}'::jsonb),
                    '{{account_id}}',
                    to_jsonb(CAST(:account_id AS text)),
                    true
                )::json,
                date_modification = :now,
                usermod = :user_id
            WHERE id = :robot_id
              AND user_id = :user_id
              AND (
                  config->>'account_id' IS NULL
                  OR btrim(config->>'account_id') = ''
              )
        """),
        {
            "robot_id": int(robot_id),
            "user_id": int(user_id),
            "account_id": str(account_id),
            "now": datetime.now(timezone.utc),
        }
    )
    db.commit()


def _api_tokens_has_status_column(db: Session) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = 'api_tokens'
              AND column_name = 'status'
            LIMIT 1
            """
        ),
        {"schema": settings.DB_SCHEMA}
    ).first()
    return bool(row)


def _expire_token_and_disable_robots(
        db: Session,
        *,
        token_id: int,
        user_id: int,
        error_message: str
) -> None:
    now = datetime.now(timezone.utc)
    params = {
        "token_id": int(token_id),
        "user_id": int(user_id),
        "now": now,
        "error_message": str(error_message or "")[:500],
    }
    if _api_tokens_has_status_column(db):
        db.execute(
            text(
                f"""
                UPDATE api_tokens
                SET status = 3, updated_at = :now
                WHERE id = :token_id AND user_id = :user_id
                """
            ),
            params
        )
    db.execute(
        text(
            f"""
            UPDATE robots
            SET status = 2,
                last_error = :error_message,
                last_error_at = :now,
                usermod = :user_id,
                date_modification = :now
            WHERE token_id = :token_id
              AND user_id = :user_id
              AND status != 0
            """
        ),
        params
    )
    db.commit()


def _is_bybit_auth_error(exc: Exception) -> bool:
    """Hard key death only — not missing local secret, FUND/COPY gaps (10005), or sign bugs (10004)."""
    if isinstance(exc, BybitApiError):
        if getattr(exc, "status_code", None) == 401:
            return True
        if getattr(exc, "ret_code", None) in {10003, 10007}:
            return True
    msg = str(exc or "").lower()
    # Do not treat "requires api_key/api_secret" as expired key — that is local misconfig.
    markers = (
        "invalid api key",
        "api key is invalid",
        "unauthorized",
        "retcode=10003",
        "retcode=10007"
    )
    return any(m in msg for m in markers)


_QUEUED_STALE_MINUTES = 5
_RUNNING_STALE_HOURS = 12
_PERSISTING_STALE_MINUTES = 90
_SCORING_STALE_MINUTES = 45
_LOADING_CANDLES_STALE_MINUTES = 30
_PREFETCH_CANDLES_STALE_MINUTES = 45
_PREFETCH_CRYPTO_STALE_MINUTES = 90
_CANDLE_LOAD_BATCH_SIZE = 40
# Подшаги внутри одного торгового дня при scoring (прогресс не «замирает» на тяжёлом дне).
_SCORING_PROGRESS_SUBSTEPS = 5


def _coerce_utc_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _maybe_reconcile_orphan_queued_run(db: Session, run_id: int) -> Optional[str]:
    """QUEUED без background_jobs — HTTP 202 без enqueue или сбой после commit."""
    from app.core.background_jobs.repository import find_background_job_for_backtest_run

    row = db.execute(
        text(
            f"""
            SELECT status, started_at
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    if not row:
        return None
    if str(row.get("status") or "").upper() != "QUEUED":
        return None
    started = _coerce_utc_dt(row.get("started_at"))
    if started is None:
        return None
    age_sec = (datetime.now(timezone.utc) - started).total_seconds()
    if age_sec < 90:
        return None
    if find_background_job_for_backtest_run(db, run_id):
        return None

    err_msg = (
        "orphan-queued: прогон в QUEUED, но задача в background_jobs отсутствует. "
        "Перезапустите бэктест или: python backend/scripts/requeue_backtest_run.py <run_id>"
    )
    db.execute(
        text(
            f"""
            UPDATE backtest_runs
            SET status = 'FAILED',
                finished_at = :ft,
                error_message = :msg
            WHERE id = :rid AND status = 'QUEUED'
            """
        ),
        {"rid": run_id, "ft": datetime.now(timezone.utc), "msg": err_msg[:2000]}
    )
    db.commit()
    _clear_backtest_run_tracking(run_id)
    logger.warning("reconciled orphan queued run_id=%s", run_id)
    return err_msg


def _maybe_reconcile_stale_backtest_run(db: Session, run_id: int) -> Optional[str]:
    """Помечает «зомби» QUEUED/RUNNING как FAILED (воркер потерян после рестарта и т.п.)."""
    from app.modules.robots.backtest_progress import scoring_progress_idle_seconds

    row = db.execute(
        text(
            f"""
            SELECT status, started_at, cancel_requested, run_phase, progress_percent
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    if not row:
        return None
    st = str(row.get("status") or "").upper()
    if st not in ("QUEUED", "RUNNING", "FETCHING"):
        return None
    try:
        from app.modules.robots.trading.backtest.persist_checkpoint import persist_checkpoint_exists

        if persist_checkpoint_exists(run_id):
            return None
    except Exception:
        pass
    started = _coerce_utc_dt(row.get("started_at"))
    if started is None:
        return None
    age_sec = (datetime.now(timezone.utc) - started).total_seconds()
    phase = str(row.get("run_phase") or "").strip().lower()
    progress = float(row.get("progress_percent") or 0)
    err_msg: Optional[str] = None
    if st == "QUEUED" and age_sec >= _QUEUED_STALE_MINUTES * 60:
        err_msg = (
            "queued-timeout: прогон не перешёл в RUNNING — вероятно потерян фоновый воркер "
            "(перезапуск backend после HTTP 202)"
        )
    elif (
        st in ("RUNNING", "FETCHING")
        and phase == "persisting"
        and age_sec >= _PERSISTING_STALE_MINUTES * 60
    ):
        err_msg = (
            f"persist-timeout: фаза сохранения дольше {_PERSISTING_STALE_MINUTES} мин "
            f"(progress={progress:.1f}%) — воркер завис или упал"
        )
    elif st in ("RUNNING", "FETCHING") and phase == "scoring":
        idle_sec = scoring_progress_idle_seconds(run_id)
        if idle_sec is not None and idle_sec >= _SCORING_STALE_MINUTES * 60:
            err_msg = (
                f"scoring-timeout: фаза «Отбор бумаг» без обновления прогресса "
                f"дольше {_SCORING_STALE_MINUTES} мин (progress={progress:.1f}%) — "
                "вероятно зависание MOEX/БД или перегрузка пула соединений"
            )
    elif st in ("RUNNING", "FETCHING") and phase == "prefetching_candles":
        idle_sec = scoring_progress_idle_seconds(run_id)
        if idle_sec is not None and idle_sec >= _PREFETCH_CANDLES_STALE_MINUTES * 60:
            err_msg = (
                f"prefetch-candles-timeout: фаза «Кэш свечей MOEX» без обновления прогресса "
                f"дольше {_PREFETCH_CANDLES_STALE_MINUTES} мин (progress={progress:.1f}%) — "
                "вероятно перегрузка MOEX или пул соединений"
            )
    elif st in ("RUNNING", "FETCHING") and phase == "prefetching_crypto_market":
        idle_sec = scoring_progress_idle_seconds(run_id)
        if idle_sec is not None and idle_sec >= _PREFETCH_CRYPTO_STALE_MINUTES * 60:
            err_msg = (
                f"prefetch-crypto-timeout: фаза «Кэш ByBit (D1 + funding)» без обновления прогресса "
                f"дольше {_PREFETCH_CRYPTO_STALE_MINUTES} мин (progress={progress:.1f}%) — "
                "вероятно перегрузка ByBit API или пул соединений"
            )
    elif st in ("RUNNING", "FETCHING") and phase == "loading_candles":
        idle_sec = scoring_progress_idle_seconds(run_id)
        if idle_sec is not None and idle_sec >= _LOADING_CANDLES_STALE_MINUTES * 60:
            err_msg = (
                f"loading-candles-timeout: фаза «Загрузка свечей» без обновления прогресса "
                f"дольше {_LOADING_CANDLES_STALE_MINUTES} мин (progress={progress:.1f}%) — "
                "вероятно тяжёлый SELECT или зависший prefetch"
            )
    elif st in ("RUNNING", "FETCHING") and age_sec >= _RUNNING_STALE_HOURS * 3600:
        err_msg = (
            f"stale-timeout: прогон в статусе {st} более {_RUNNING_STALE_HOURS} ч без завершения"
        )
    if not err_msg:
        return None
    if st == "QUEUED":
        from app.core.background_jobs.repository import (
            fail_background_job,
            find_background_job_for_backtest_run
        )

        job = find_background_job_for_backtest_run(db, run_id)
        if job and str(job.get("status") or "").lower() == "queued":
            fail_background_job(
                db,
                job["id"],
                err_msg[:4000],
                message="cancelled (queued-timeout)"
            )
    db.execute(
        text(
            f"""
            UPDATE backtest_runs
            SET status = 'FAILED',
                finished_at = :ft,
                error_message = :msg,
                run_phase = 'failed',
                progress_percent = COALESCE(progress_percent, 0)
            WHERE id = :rid
              AND status IN ('QUEUED', 'RUNNING', 'FETCHING')
            """
        ),
        {"rid": run_id, "ft": datetime.now(timezone.utc), "msg": err_msg[:2000]}
    )
    db.commit()
    _clear_backtest_run_tracking(run_id)
    logger.warning("reconciled stale backtest run_id=%s: %s", run_id, err_msg)
    return "FAILED"


def _maybe_reconcile_from_run_summary(
    db: Session,
    run_id: int,
    started_at: Optional[datetime]
) -> Optional[str]:
    """
    Синхронизировать terminal status из summary.json, если воркер упал при недоступной БД.

    close_backtest_run_log пишет summary.json локально даже когда UPDATE backtest_runs не прошёл.
    """
    from app.modules.robots.trading.backtest.run_file_logger import read_backtest_run_summary_on_disk

    summary = read_backtest_run_summary_on_disk(run_id, started_at=started_at)
    if not summary:
        return None
    terminal = str(summary.get("status") or "").upper()
    if terminal not in ("SUCCESS", "FAILED", "CANCELLED"):
        return None

    row = db.execute(
        text(
            f"""
            SELECT status
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    if not row:
        return None
    current = str(row.get("status") or "").upper()
    if current in ("SUCCESS", "FAILED", "CANCELLED"):
        return None

    err_raw = summary.get("error")
    err_msg = str(err_raw or f"log-summary-{terminal.lower()}")[:2000]
    finished_raw = summary.get("finished_at")
    finished_at = _coerce_utc_dt(finished_raw) or datetime.now(timezone.utc)
    run_phase = "failed" if terminal == "FAILED" else terminal.lower()

    db.execute(
        text(
            f"""
            UPDATE backtest_runs
            SET status = :st,
                finished_at = :ft,
                error_message = CASE WHEN :st = 'FAILED' THEN :msg ELSE error_message END,
                run_phase = :phase,
                progress_percent = CASE WHEN :st = 'SUCCESS' THEN 100.0 ELSE COALESCE(progress_percent, 0) END
            WHERE id = :rid
              AND status NOT IN ('SUCCESS', 'FAILED', 'CANCELLED')
            """
        ),
        {
            "rid": run_id,
            "st": terminal,
            "ft": finished_at,
            "msg": err_msg,
            "phase": run_phase,
        }
    )
    db.commit()
    _clear_backtest_run_tracking(run_id)
    try:
        from app.modules.robots.trading.backtest.run_file_logger import append_backtest_run_log_line
        import logging as _logging

        append_backtest_run_log_line(
            run_id,
            _logging.WARNING,
            "RECONCILE from summary.json status=%s (db was %s)",
            terminal,
            current,
            started_at=started_at
        )
    except Exception:
        pass
    logger.warning(
        "reconciled backtest run_id=%s from summary.json status=%s (db was %s)",
        run_id,
        terminal,
        current
    )
    return terminal


def _maybe_reconcile_zombie_failed_job(db: Session, run_id: int) -> Optional[str]:
    """
    RUNNING/FETCHING в БД, но фоновый job уже failed — пометить FAILED и дописать лог.
    """
    from app.modules.robots.trading.backtest.persist_checkpoint import persist_checkpoint_exists
    from app.modules.robots.trading.backtest.run_file_logger import close_backtest_run_log

    if persist_checkpoint_exists(run_id):
        return None

    row = db.execute(
        text(
            f"""
            SELECT status, run_phase, progress_percent, started_at
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    if not row:
        return None
    st = str(row.get("status") or "").upper()
    if st not in ("RUNNING", "FETCHING"):
        return None

    from app.core.background_jobs.repository import find_background_job_for_backtest_run

    job = find_background_job_for_backtest_run(db, run_id)
    if not job or str(job.get("status") or "").lower() != "failed":
        return None

    phase = str(row.get("run_phase") or "")
    progress = float(row.get("progress_percent") or 0)
    job_err = str(job.get("error") or "worker-job-failed")
    err_msg = (
        f"worker-lost: фоновый job failed при status={st} phase={phase} "
        f"progress={progress:.1f}% — {job_err}"
    )[:2000]
    started_at = _coerce_utc_dt(row.get("started_at"))

    db.execute(
        text(
            f"""
            UPDATE backtest_runs
            SET status = 'FAILED',
                finished_at = :ft,
                error_message = :msg,
                run_phase = 'failed'
            WHERE id = :rid
              AND status IN ('RUNNING', 'FETCHING')
            """
        ),
        {"rid": run_id, "ft": datetime.now(timezone.utc), "msg": err_msg}
    )
    db.commit()
    _clear_backtest_run_tracking(run_id)
    try:
        close_backtest_run_log(
            run_id,
            status="FAILED",
            summary={"progress_percent": progress, "run_phase": phase},
            error=err_msg,
            started_at=started_at
        )
    except Exception:
        pass
    logger.warning("reconciled zombie failed job run_id=%s: %s", run_id, err_msg[:200])
    return "FAILED"


def _maybe_reconcile_persist_checkpoint(
    db: Session,
    run_id: int,
    started_at: Optional[datetime]
) -> Optional[str]:
    """
    Дозаписать результаты бэктеста из persist_checkpoint.json после восстановления БД.
    """
    from app.modules.robots.trading.backtest.persist_checkpoint import (
        checkpoint_run_started_at,
        delete_persist_checkpoint,
        find_persist_checkpoint,
        read_persist_checkpoint
    )

    found = find_persist_checkpoint(run_id)
    checkpoint: Optional[Dict[str, Any]] = None
    cp_started = started_at
    if found:
        checkpoint, cp_started = found
    elif started_at is not None:
        checkpoint = read_persist_checkpoint(run_id, started_at=started_at)
    if not checkpoint:
        return None

    row = db.execute(
        text(
            f"""
            SELECT status
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    if not row:
        return None
    current = str(row.get("status") or "").upper()
    if current in ("SUCCESS", "FAILED", "CANCELLED"):
        delete_persist_checkpoint(run_id, cp_started)
        return None

    try:
        terminal = robot_service.finish_from_persist_checkpoint(
            db,
            run_id,
            checkpoint,
            cp_started or checkpoint_run_started_at(checkpoint)
        )
        return terminal
    except Exception:
        logger.exception("persist checkpoint reconcile failed run_id=%s", run_id)
        db.rollback()
        return None


def _mark_backtest_run_failed(
    db: Session,
    run_id: int,
    error_message: str,
    *,
    skip_if_cancelled: bool = True
) -> None:
    """Не удалять прогон при ошибке — UI опрашивает /runs/{id}/status и историю."""
    from app.core.database import SessionLocal

    fresh = SessionLocal()
    try:
        if skip_if_cancelled:
            row_st = fresh.execute(
                text(f"SELECT status FROM backtest_runs WHERE id=:run_id"),
                {"run_id": run_id}
            ).scalar()
            if str(row_st or "").upper() == "CANCELLED":
                return
        fresh.execute(
            text(
                f"""
                UPDATE backtest_runs
                SET status = 'FAILED',
                    finished_at = :ft,
                    error_message = :msg,
                    run_phase = 'failed',
                    progress_percent = COALESCE(progress_percent, 0)
                WHERE id = :run_id
                  AND status NOT IN ('SUCCESS', 'FAILED', 'CANCELLED')
                """
            ),
            {
                "run_id": run_id,
                "ft": datetime.now(timezone.utc),
                "msg": str(error_message or "backtest-failed")[:2000],
            }
        )
        fresh.commit()
    except Exception:
        fresh.rollback()
        logger.warning(
            "mark_backtest_run_failed: DB update failed run_id=%s (summary.json reconcile on status poll)",
            run_id
        )
    finally:
        fresh.close()


def _read_history_backtest_cancel_requested_fresh(bind, run_id: int) -> bool:
    """Флаг отмены из БД отдельным соединением (не через длинную сессию прогона).

    Иначе после POST …/cancel (отдельная сессия + COMMIT) рабочая сессия может долго
    не «видеть» обновление `cancel_requested` в зависимости от изоляции/пула.
    """
    with bind.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT COALESCE(cancel_requested, false) FROM backtest_runs WHERE id=:rid"
            ),
            {"rid": run_id}
        ).scalar()
        return bool(row)


def _is_backtest_run_cancelled(run_id: int, bind: Any = None) -> bool:
    """In-memory флаг (мгновенно после POST /cancel) + подтверждение из БД при необходимости."""
    if is_history_backtest_cancelled(run_id):
        return True
    if bind is None:
        return False
    try:
        return _read_history_backtest_cancel_requested_fresh(bind, run_id)
    except Exception:
        return False


def _parse_backtest_ts(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _strategy_display_title(name: Any) -> Optional[str]:
    """Человекочитаемое название стратегии по коду (grain_seed, …)."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    from app.modules.robots.trading.strategies import get_strategy_info

    info = get_strategy_info(key)
    if info:
        return str(info.get("title") or key)
    return key


def _parse_backtest_trade_date(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return v


def _compute_persist_phase_units_total(
        *,
        decisions_rows: List[Dict[str, Any]],
        bt_run_id: Optional[int],
        decisions_chunk_size: int = 1000,
        universe_chunk_size: int = 500
) -> int:
    """Шаги фазы persisting: core (equity/orders/signals) + чанки decisions + чанки universe + финализация."""
    decision_chunks = (
        (len(decisions_rows) + decisions_chunk_size - 1) // decisions_chunk_size
        if decisions_rows
        else 0
    )
    universe_chunks = (
        (len(decisions_rows) + universe_chunk_size - 1) // universe_chunk_size
        if bt_run_id and decisions_rows
        else 0
    )
    return max(1, 1 + decision_chunks + universe_chunks + 1)


def _bulk_persist_backtest_decisions(
        db: Session,
        *,
        run_id: int,
        decisions_rows: List[Dict[str, Any]],
        chunk_size: int = 1000,
        on_chunk_done: Optional[Callable[[], None]] = None
) -> None:
    if not decisions_rows:
        return
    from sqlalchemy import BigInteger, Date, String, Text, table, column
    from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

    decisions_tbl = table(
        "backtest_decisions",
        column("run_id", BigInteger),
        column("trade_date", Date),
        column("ticker", String),
        column("source", String),
        column("result", String),
        column("reason", Text),
        column("payload", JSONB),
        schema=settings.DB_SCHEMA
    )
    payload_rows: List[Dict[str, Any]] = []
    for dr in decisions_rows:
        payload_rows.append({
            "run_id": run_id,
            "trade_date": _parse_backtest_trade_date(dr.get("trade_date")),
            "ticker": dr.get("ticker"),
            "source": "PIPELINE",
            "result": dr.get("result"),
            "reason": dr.get("reason"),
            "payload": dr.get("payload") if isinstance(dr.get("payload"), dict) else (dr.get("payload") or {}),
        })
    for off in range(0, len(payload_rows), chunk_size):
        db.execute(pg_insert(decisions_tbl).values(payload_rows[off : off + chunk_size]))
        if on_chunk_done is not None:
            on_chunk_done()


def _bulk_persist_daily_universe(
        db: Session,
        *,
        bt_run_id: int,
        decisions_rows: List[Dict[str, Any]],
        chunk_size: int = 500,
        on_chunk_done: Optional[Callable[[], None]] = None
) -> None:
    if not bt_run_id or not decisions_rows:
        return
    from sqlalchemy import BigInteger, Date, String, Text, Float, table, column
    from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

    universe_tbl = table(
        "backtest_daily_universe",
        column("backtest_run_id", BigInteger),
        column("trade_date", Date),
        column("ticker", String),
        column("source", String),
        column("filter_result", String),
        column("reject_reason", Text),
        column("snapshot_id", BigInteger),
        column("price_at_filter", Float),
        column("volume_at_filter", Float),
        column("atr_value", Float),
        column("gap_percent", Float),
        column("applied_filters", JSONB),
        schema=None
    )
    rows: List[Dict[str, Any]] = []
    for dr in decisions_rows:
        eval_payload = dr.get("payload") if isinstance(dr.get("payload"), dict) else {}
        eval_obj = eval_payload.get("eval") if isinstance(eval_payload, dict) else {}
        rows.append({
            "backtest_run_id": bt_run_id,
            "trade_date": _parse_backtest_trade_date(dr.get("trade_date")),
            "ticker": dr.get("ticker"),
            "source": "PIPELINE",
            "filter_result": "ACCEPT" if str(dr.get("result") or "").upper() == "ACCEPT" else "REJECT",
            "reject_reason": dr.get("reason"),
            "snapshot_id": None,
            "price_at_filter": eval_obj.get("price_at_filter"),
            "volume_at_filter": eval_obj.get("volume_at_filter"),
            "atr_value": eval_obj.get("atr_percent"),
            "gap_percent": eval_obj.get("gap_percent"),
            "applied_filters": eval_payload,
        })
    excluded = pg_insert(universe_tbl).excluded
    for off in range(0, len(rows), chunk_size):
        batch = rows[off : off + chunk_size]
        stmt = pg_insert(universe_tbl).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["backtest_run_id", "trade_date", "ticker"],
            set_={
                "filter_result": excluded.filter_result,
                "reject_reason": excluded.reject_reason,
                "price_at_filter": excluded.price_at_filter,
                "volume_at_filter": excluded.volume_at_filter,
                "atr_value": excluded.atr_value,
                "gap_percent": excluded.gap_percent,
                "applied_filters": excluded.applied_filters,
            }
        )
        db.execute(stmt)
        if on_chunk_done is not None:
            on_chunk_done()


def _bulk_persist_backtest_rows(
        db: Session,
        *,
        run_id: int,
        res: Any,
        decisions_rows: List[Dict[str, Any]],
        slippage_pct: float = 0.0,
        on_core_done: Optional[Callable[[], None]] = None,
        on_decision_chunk_done: Optional[Callable[[], None]] = None
) -> None:
    """Пакетная запись equity/signals/orders/decisions (чанки по 500–1000)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.modules.robots.models import BacktestOrder, BacktestPortfolioSnapshot, BacktestSignal

    snap_rows: List[Dict[str, Any]] = []
    for p in getattr(res, "equity_curve", None) or []:
        ts = _parse_backtest_ts(p.get("time")) or datetime.now(timezone.utc)
        snap_rows.append({
            "run_id": run_id,
            "snapshot_time": ts,
            "cash_balance": p.get("equity", 0),
            "equity": p.get("equity", 0),
            "positions_payload": [],
        })
    if snap_rows:
        tbl = BacktestPortfolioSnapshot.__table__
        for off in range(0, len(snap_rows), 500):
            db.execute(pg_insert(tbl).values(snap_rows[off : off + 500]))

    order_rows: List[Dict[str, Any]] = []
    for t in getattr(res, "trades", None) or []:
        order_rows.append({
            "run_id": run_id,
            "signal_time": _parse_backtest_ts(t.get("bar_time")),
            "figi": t.get("figi"),
            "side": t.get("side"),
            "status": "FILLED",
            "quantity": t.get("quantity", 0),
            "requested_price": t.get("price"),
            "executed_price": t.get("price"),
            "slippage_pct": slippage_pct,
            "commission": t.get("commission"),
            "tax": None,
            "pnl_net": t.get("pnl_net"),
            "payload": json.dumps(t, ensure_ascii=False),
        })
    if order_rows:
        tbl = BacktestOrder.__table__
        for off in range(0, len(order_rows), 500):
            db.execute(pg_insert(tbl).values(order_rows[off : off + 500]))

    signal_rows: List[Dict[str, Any]] = []
    for s in getattr(res, "signals", None) or []:
        signal_rows.append({
            "run_id": run_id,
            "signal_time": _parse_backtest_ts(s.get("bar_time")),
            "figi": s.get("figi"),
            "signal_type": s.get("signal_type"),
            "price": s.get("price"),
            "was_executed": int(bool(s.get("was_executed"))),
            "payload": json.dumps(s, ensure_ascii=False),
        })
    if signal_rows:
        tbl = BacktestSignal.__table__
        for off in range(0, len(signal_rows), 1000):
            db.execute(pg_insert(tbl).values(signal_rows[off : off + 1000]))

    if on_core_done is not None:
        on_core_done()

    _bulk_persist_backtest_decisions(
        db,
        run_id=run_id,
        decisions_rows=decisions_rows,
        on_chunk_done=on_decision_chunk_done
    )


def _mark_backtest_run_cancelled_in_db(
        db: Session,
        run_id: int,
        *,
        trade_date: Optional[date] = None,
        trade_dates_remaining: Optional[int] = None
) -> None:
    """Проставить status=CANCELLED в backtest_runs (воркер / префетч)."""
    try:
        ts = datetime.now(timezone.utc)
        if trade_date is not None and trade_dates_remaining is not None:
            db.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET status = 'CANCELLED',
                        partial_result = true,
                        run_phase = 'cancelled',
                        finished_at = :ts,
                        trade_dates_remaining = :rem,
                        current_trade_date = :cd
                    WHERE id = :rid
                    """
                ),
                {"rid": run_id, "ts": ts, "rem": int(trade_dates_remaining), "cd": trade_date}
            )
        else:
            db.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET status = 'CANCELLED',
                        partial_result = true,
                        run_phase = 'cancelled',
                        finished_at = :ts
                    WHERE id = :rid
                    """
                ),
                {"rid": run_id, "ts": ts}
            )
        db.commit()
    except Exception:
        db.rollback()


class RobotService:
    """Сервис для управления торговыми роботами"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query: str, params: dict, fetch_one: bool = False):
        """Утилита для выполнения запросов"""
        result = self.db.execute(text(query), params)
        return result.first() if fetch_one else result

    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===

    @staticmethod
    def _flush_backtest_progress(
        bind: Any,
        run_id: int,
        run_phase: str,
        *,
        phase_units_done: int = 0,
        phase_units_total: int = 0,
        trade_dates_total: Optional[int] = None,
        trade_dates_remaining: Optional[int] = None,
        current_trade_date: Optional[date] = None,
        started_at: Optional[datetime] = None
    ) -> None:
        from app.modules.robots.backtest_progress import persist_backtest_progress

        try:
            persist_backtest_progress(
                bind,
                run_id,
                run_phase=run_phase,
                phase_units_done=phase_units_done,
                phase_units_total=phase_units_total,
                trade_dates_total=trade_dates_total,
                trade_dates_remaining=trade_dates_remaining,
                current_trade_date=current_trade_date,
                started_at=started_at
            )
        except Exception as ex:
            logger.debug("backtest progress flush failed run_id=%s: %s", run_id, ex)

    def finish_from_persist_checkpoint(
        self,
        db: Session,
        run_id: int,
        checkpoint: Dict[str, Any],
        started_at: datetime
    ) -> str:
        """Resume DB persist from on-disk checkpoint (status poll / script)."""
        from app.core.db_retry import run_db_with_retry
        from app.modules.robots.trading.backtest.persist_checkpoint import (
            backtest_result_from_dict,
            checkpoint_run_started_at,
            delete_persist_checkpoint
        )
        from app.modules.robots.trading.backtest.persist_phase import execute_backtest_persist_phase
        from app.modules.robots.trading.backtest.run_file_logger import (
            close_backtest_run_log,
            log_backtest_run_info
        )

        cp_started = started_at or checkpoint_run_started_at(checkpoint)
        res = backtest_result_from_dict(checkpoint["res"])
        result = dict(checkpoint.get("result") or {})
        decisions_rows = list(checkpoint.get("decisions_rows") or [])
        requested_from = checkpoint.get("requested_from_utc")
        requested_to = checkpoint.get("requested_to_utc")
        if isinstance(requested_from, str):
            requested_from = datetime.fromisoformat(requested_from.replace("Z", "+00:00"))
        if isinstance(requested_to, str):
            requested_to = datetime.fromisoformat(requested_to.replace("Z", "+00:00"))
        if requested_from and requested_from.tzinfo is None:
            requested_from = requested_from.replace(tzinfo=timezone.utc)
        if requested_to and requested_to.tzinfo is None:
            requested_to = requested_to.replace(tzinfo=timezone.utc)

        log_backtest_run_info(
            "RECONCILE persist from checkpoint run_id=%s",
            run_id,
            run_id=run_id
        )
        progress_bind = db.get_bind()

        def _persist() -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
            return execute_backtest_persist_phase(
                flush_progress=self._flush_backtest_progress,
                dt_date_utc=self._dt_date_utc,
                db=db,
                progress_bind=progress_bind,
                run_id=run_id,
                run_started_at=cp_started,
                td_total=int(checkpoint.get("td_total") or 0),
                skip_heavy_persist=bool(checkpoint.get("skip_heavy_persist")),
                bt_run_id=checkpoint.get("bt_run_id"),
                res=res,
                slippage_pct=float(checkpoint.get("slippage_pct") or 0),
                decisions_rows=decisions_rows,
                is_crypto_backtest=bool(checkpoint.get("is_crypto_backtest")),
                config=dict(checkpoint.get("config") or {}),
                result=result,
                robot_pk=checkpoint.get("robot_pk"),
                requested_from_utc=requested_from,
                requested_to_utc=requested_to,
                pipeline_user_cancelled=bool(checkpoint.get("pipeline_user_cancelled"))
            )

        backtest_log_status, backtest_log_summary, backtest_log_error = run_db_with_retry(
            db,
            _persist,
            max_attempts=8,
            delay_sec=3.0,
            max_delay_sec=30.0
        )
        delete_persist_checkpoint(run_id, cp_started)
        close_backtest_run_log(
            run_id,
            status=backtest_log_status,
            summary=backtest_log_summary,
            error=backtest_log_error,
            started_at=cp_started
        )
        _clear_backtest_run_tracking(run_id)
        logger.warning(
            "reconciled backtest run_id=%s from persist_checkpoint status=%s",
            run_id,
            backtest_log_status
        )
        return backtest_log_status

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_str(value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _safe_bool(value, default: bool = False) -> bool:
        """Безопасное преобразование в bool"""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value == 1
        return bool(value)

    @staticmethod
    def _safe_datetime(value, default=None):
        """Безопасное преобразование в datetime"""
        return value if value is not None else default

    @staticmethod
    def _safe_float_opt(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int_opt(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dt_date_utc(v: datetime) -> date:
        if v.tzinfo:
            return v.astimezone(timezone.utc).date()
        return v.date()

    @staticmethod
    def _history_backtest_moex_log(msg: str, *args: Any) -> None:
        from app.modules.robots.trading.data.providers.moex_snapshots import history_backtest_moex_log

        history_backtest_moex_log(msg, *args)

    def _log_moex_external_api_isolated(
        self,
        *,
        user_id: Optional[int],
        run_id: Optional[int],
        endpoint: str,
        request_data: Dict[str, Any],
        response_status: Optional[int],
        response_data: Optional[Dict[str, Any]],
        started_at: datetime,
        finished_at: datetime,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        from app.modules.robots.trading.data.providers.moex_snapshots import log_moex_external_api_isolated

        log_moex_external_api_isolated(
            user_id=user_id,
            run_id=run_id,
            endpoint=endpoint,
            request_data=request_data,
            response_status=response_status,
            response_data=response_data,
            started_at=started_at,
            finished_at=finished_at,
            success=success,
            error_message=error_message
        )

    def _row_to_log_dict(self, row) -> dict:
        """Преобразует строку результата в словарь лога"""
        if not row or len(row) < 6:
            return {}

        return {
            "id": self._safe_int(row[0]),
            "robot_id": self._safe_int(row[1]),
            "level": self._safe_str(row[2]),
            "message": self._safe_str(row[3]),
            "details": row[4] if row[4] else None,
            "created_at": self._safe_datetime(row[5]),
        }

    # === УПРАВЛЕНИЕ РОБОТАМИ ===

    async def get_robot_by_id(
            self,
            db: Session,
            robot_id: int,
            user_id: int
    ) -> dict:
        """Получение робота по ID (с проверкой владельца)"""
        self.db = db

        query = queries.build_get_robot_by_id_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(query),
            {"robot_id": robot_id, "user_id": user_id}
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Робот не найден"
            )

        robot_dict = {
            "id": result[0],
            "user_id": result[1],
            "token":{
                "id": result[2],
                "name":result[3],
                "status":result[4],
                "type":result[5],
                "typeName": result[6]
            },
            "name": result[7],
            "type": result[8],
            "typeName": result[9],
            "status": result[10],
            "statusName": result[11],
            "config": result[12] or {},
            "schedule": None,
            "last_started": result[13],
            "last_error": result[14],
            "last_error_at": result[15],
            "last_stopped": result[16],
            "usercre": result[17],
            "date_creation": result[18],
            "usermod": result[19],
            "date_modification": result[20]
        }

        schedule_sql = f"""
            SELECT
                id, schedule_type, interval_seconds, start_time, end_time,
                weekdays, is_active, priority, description
            FROM robot_schedules
            WHERE robot_id = :robot_id
              AND COALESCE(is_active, 1) = 1
            ORDER BY priority DESC, date_creation DESC
            LIMIT 1
        """
        schedule_row = db.execute(text(schedule_sql), {"robot_id": robot_id}).first()
        if schedule_row:
            robot_dict["schedule"] = {
                "id": int(schedule_row[0]),
                "schedule_type": schedule_row[1],
                "interval_seconds": schedule_row[2],
                "start_time": schedule_row[3],
                "end_time": schedule_row[4],
                "weekdays": schedule_row[5],
                "is_active": schedule_row[6],
                "priority": schedule_row[7],
                "description": schedule_row[8],
            }

        if int(robot_dict.get("type") or 0) == 2:
            robot_dict["config"] = self._normalize_trading_robot_config_for_api(
                robot_dict.get("config") or {}
            )

        return robot_dict

    @staticmethod
    def _normalize_trading_robot_config_for_api(config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = dict(config or {})
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        if (
            normalize_broker_type(str(cfg.get("broker_type") or "")) == "bybit"
            or str(cfg.get("schema_profile") or "") == "type2_bybit"
        ):
            return cfg
        from app.modules.robots.config.migration import ensure_config_v2

        return ensure_config_v2(cfg)

    async def migrate_trading_robots_config_v2(
        self,
        db: Session,
        user_id: int,
        robot_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Привести config всех роботов type=2 пользователя к схеме v2 (П1/П2/П3) и сохранить в БД."""
        from app.modules.robots.config.migration import migrate_robot_config_row

        self.db = db
        schema = settings.DB_SCHEMA
        if robot_id is not None:
            await self.get_robot_by_id(db, robot_id, user_id)
            rows = db.execute(
                text(
                    f"""
                    SELECT id, config FROM robots
                    WHERE id = :rid AND user_id = :uid AND type = 2
                    """
                ),
                {"rid": robot_id, "uid": user_id}
            ).mappings().all()
        else:
            rows = db.execute(
                text(
                    f"""
                    SELECT id, config FROM robots
                    WHERE user_id = :uid AND type = 2
                    ORDER BY id
                    """
                ),
                {"uid": user_id}
            ).mappings().all()

        items: List[Dict[str, Any]] = []
        updated = 0
        for row in rows:
            rid = int(row["id"])
            normalized, changed = migrate_robot_config_row(row["config"])
            items.append({
                "robot_id": rid,
                "config_version": int(normalized.get("config_version") or 0),
                "universe_mode": normalized.get("universe_mode"),
                "historical_enabled": (normalized.get("historical_screening") or {}).get("enabled"),
                "paper_input": (normalized.get("paper_selection") or {}).get("input"),
                "updated": changed,
            })
            if changed:
                db.execute(
                    text(
                        f"""
                        UPDATE robots
                        SET config = CAST(:cfg AS jsonb),
                            usermod = :uid,
                            date_modification = NOW()
                        WHERE id = :rid AND user_id = :uid
                        """
                    ),
                    {
                        "cfg": json.dumps(normalized, ensure_ascii=False),
                        "rid": rid,
                        "uid": user_id,
                    }
                )
                updated += 1
        db.commit()
        return {
            "total": len(items),
            "updated": updated,
            "items": items,
        }

    async def migrate_trading_robots_config_v3(
        self,
        db: Session,
        user_id: int,
        robot_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Привести config trading роботов к v3 (schema_profile + config_version=3)."""
        from app.modules.robots.config.migration import config_equals, migrate_v2_to_v3

        self.db = db
        schema = settings.DB_SCHEMA
        if robot_id is not None:
            await self.get_robot_by_id(db, robot_id, user_id)
            rows = db.execute(
                text(
                    f"""
                    SELECT id, type, config FROM robots
                    WHERE id = :rid AND user_id = :uid AND type = 2
                    """
                ),
                {"rid": robot_id, "uid": user_id}
            ).mappings().all()
        else:
            rows = db.execute(
                text(
                    f"""
                    SELECT id, type, config FROM robots
                    WHERE user_id = :uid AND type = 2
                    ORDER BY id
                    """
                ),
                {"uid": user_id}
            ).mappings().all()

        items: List[Dict[str, Any]] = []
        updated = 0
        for row in rows:
            rid = int(row["id"])
            normalized = migrate_v2_to_v3(
                dict(row["config"] or {}),
                robot_type=int(row.get("type") or 2)
            )
            changed = not config_equals(dict(row["config"] or {}), normalized)
            items.append({
                "robot_id": rid,
                "config_version": int(normalized.get("config_version") or 0),
                "schema_profile": normalized.get("schema_profile"),
                "broker_type": normalized.get("broker_type"),
                "updated": changed,
            })
            if changed:
                db.execute(
                    text(
                        f"""
                        UPDATE robots
                        SET config = CAST(:cfg AS jsonb),
                            usermod = :uid,
                            date_modification = NOW()
                        WHERE id = :rid AND user_id = :uid
                        """
                    ),
                    {
                        "cfg": json.dumps(normalized, ensure_ascii=False),
                        "rid": rid,
                        "uid": user_id,
                    }
                )
                updated += 1
        db.commit()
        return {
            "total": len(items),
            "updated": updated,
            "items": items,
        }

    @staticmethod
    def _default_trading_robot_config() -> Dict[str, Any]:
        """Базовый конфиг type=2 — v2 (П1/П2/П3) + legacy-зеркало."""
        from app.modules.robots.config.migration import ensure_config_v2

        base = ensure_config_v2(schemas.GrainSeedConfig().model_dump())
        base["pipeline"] = {
            "mode": "ALL",
            "filters": [
                {"type": "security_status", "eq": "A"},
                {"type": "trading_status", "eq": "T"},
                {"type": "volume", "min": 50_000_000},
                {"type": "num_trades", "min": 100},
                {"type": "gap", "max_percent": 2.5, "direction": "BOTH"},
                {"type": "spread", "max_percent": 0.15},
                {"type": "atr", "min_percent": 1.5, "period": 14},
                {"type": "turnover", "min_percent": 0.1},
                {"type": "gap_retention", "min_ratio": 0.5},
            ],
        }
        base["allowed_figis"] = []
        base["universe_mode"] = "dms_pipeline"
        base["fixed_tickers"] = []
        base["universe_refresh_minutes"] = 0
        return base

    def _merge_trading_robot_config(self, incoming: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        from app.modules.robots.config.migration import merge_config_v2
        from app.modules.robots.trading.brokers.routing import normalize_broker_type
        from app.modules.robots.universe import is_crypto_type2_config

        payload = dict(incoming or {})
        if payload and is_crypto_type2_config(payload):
            from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config

            validated = validate_robot_config(
                robot_type=2,
                raw=payload,
                broker_type=normalize_broker_type(str(payload.get("broker_type") or "bybit"))
            )
            cfg = dump_robot_config(validated)
            self._validate_robot_config(cfg)
            return cfg

        cfg = self._default_trading_robot_config()
        if not incoming:
            self._validate_robot_config(cfg)
            return cfg
        cfg = merge_config_v2(cfg, dict(incoming))
        if incoming.get("universe_mode") and not is_crypto_type2_config(cfg):
            from app.modules.robots.universe import normalize_universe_mode

            cfg["universe_mode"] = normalize_universe_mode(cfg)
        self._validate_robot_config(cfg)
        return cfg

    @staticmethod
    def _strip_msk_hhmm(value: Optional[str], fallback: str) -> str:
        raw = str(value or "").strip().replace(" MSK", "").replace("MSK", "").strip()
        if not raw:
            return fallback
        parts = raw.split(":")
        if len(parts) >= 2:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
        return fallback

    @staticmethod
    def _assert_broker_matches_token(config: Optional[Dict[str, Any]], token_type: int) -> None:
        from app.modules.robots.trading.brokers.routing import (
            BrokerTokenMismatchError,
            enforce_broker_for_token
        )

        if not isinstance(config, dict):
            return
        try:
            enforce_broker_for_token(config, token_type=int(token_type), mutate=True)
        except BrokerTokenMismatchError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            ) from exc

    @staticmethod
    def _sync_risk_schedule_fields(
        cfg: Dict[str, Any],
        *,
        trading_hours_start: str,
        trading_hours_end: str,
        allowed_weekdays: int
    ) -> None:
        risk = dict(cfg.get("risk") or {})
        start = trading_hours_start if "MSK" in trading_hours_start.upper() else f"{trading_hours_start} MSK"
        end = trading_hours_end if "MSK" in trading_hours_end.upper() else f"{trading_hours_end} MSK"
        risk["trading_hours_start"] = start
        risk["trading_hours_end"] = end
        risk["allowed_weekdays"] = int(allowed_weekdays)
        cfg["risk"] = risk

    async def _bootstrap_trading_robot(
            self,
            db: Session,
            *,
            robot_id: int,
            user_id: int,
            config: Dict[str, Any],
            poll_interval_hours: float,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int
    ) -> None:
        self._sync_risk_schedule_fields(
            config,
            trading_hours_start=trading_hours_start,
            trading_hours_end=trading_hours_end,
            allowed_weekdays=allowed_weekdays
        )
        db.execute(
            text(
                f"""
                UPDATE robots
                SET config = CAST(:config AS jsonb),
                    usermod = :user_id,
                    date_modification = :now
                WHERE id = :robot_id AND user_id = :user_id
                """
            ),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "config": json.dumps(config, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
            }
        )
        await self._replace_robot_schedule(
            db=db,
            robot_id=robot_id,
            user_id=user_id,
            poll_interval_hours=poll_interval_hours,
            trading_hours_start=trading_hours_start,
            trading_hours_end=trading_hours_end,
            allowed_weekdays=allowed_weekdays
        )

    async def _bootstrap_portfolio_robot(
            self,
            db: Session,
            *,
            robot_id: int,
            user_id: int,
            config: Dict[str, Any],
            poll_interval_hours: float,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int
    ) -> None:
        from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        raw_cfg = dict(config or {})
        broker_type = normalize_broker_type(str(raw_cfg.get("broker_type") or "tinvest"))
        validated = validate_robot_config(
            robot_type=1,
            raw=raw_cfg,
            broker_type=broker_type
        )
        normalized = dump_robot_config(validated)
        extra = {k: v for k, v in raw_cfg.items() if k not in set(normalized.keys())}
        cfg = {**normalized, **extra}
        db.execute(
            text(
                f"""
                UPDATE robots
                SET config = CAST(:config AS jsonb),
                    usermod = :user_id,
                    date_modification = :now
                WHERE id = :robot_id AND user_id = :user_id
                """
            ),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "config": json.dumps(cfg, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
            }
        )
        await self._replace_robot_schedule(
            db=db,
            robot_id=robot_id,
            user_id=user_id,
            poll_interval_hours=poll_interval_hours,
            trading_hours_start=trading_hours_start,
            trading_hours_end=trading_hours_end,
            allowed_weekdays=allowed_weekdays
        )

    async def run_historical_screening_job(
        self,
        db: Session,
        robot_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        from app.modules.robots.universe_jobs import rebuild_candidate_pool

        return await rebuild_candidate_pool(db, self, robot_id=robot_id, user_id=user_id)

    async def run_paper_selection_job(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        *,
        force_refresh_snapshot: bool = True,
        force_recompute_universe: bool = True
    ) -> Dict[str, Any]:
        from app.modules.robots.universe_jobs import rebuild_paper_selection

        return await rebuild_paper_selection(
            db,
            self,
            robot_id=robot_id,
            user_id=user_id,
            force_refresh_snapshot=force_refresh_snapshot,
            force_recompute_universe=force_recompute_universe
        )

    async def run_crypto_screening_job(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        *,
        force: bool = False
    ) -> Dict[str, Any]:
        from app.modules.robots.universe_jobs import rebuild_crypto_screening

        return await rebuild_crypto_screening(
            db, self, robot_id=robot_id, user_id=user_id, force=force
        )

    async def enqueue_crypto_screening_job(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        *,
        force: bool = True
    ) -> Dict[str, Any]:
        """Queue crypto screening on heavy lane; returns immediately."""
        from app.core.background_jobs.repository import (
            enqueue_background_job,
            find_latest_job_for_robot
        )
        from app.core.background_jobs.worker import LANE_HEAVY

        await self.get_robot_by_id(db, robot_id, user_id)
        ik = f"crypto_screening:{int(robot_id)}"
        active = find_latest_job_for_robot(
            db,
            job_type="crypto_screening",
            robot_id=int(robot_id),
            statuses=("queued", "running")
        )
        if active:
            return {
                "robot_id": int(robot_id),
                "status": "already_running" if str(active.get("status")) == "running" else "queued",
                "job_id": str(active.get("id")),
                "started_at": active.get("started_at") or active.get("created_at"),
                "message": "Crypto-screening уже выполняется",
                "symbols": [],
                "accepted": 0,
                "scanned": 0,
                "rejected": 0,
                "skipped": False,
                "reused": False,
            }

        job_id = enqueue_background_job(
            db,
            lane=LANE_HEAVY,
            job_type="crypto_screening",
            payload={
                "robot_id": int(robot_id),
                "user_id": int(user_id),
                "force": bool(force),
            },
            idempotency_key=ik,
            priority=5
        )
        db.commit()
        if job_id is None:
            # Race: another request inserted between check and insert
            active = find_latest_job_for_robot(
                db,
                job_type="crypto_screening",
                robot_id=int(robot_id),
                statuses=("queued", "running")
            )
            return {
                "robot_id": int(robot_id),
                "status": str((active or {}).get("status") or "queued"),
                "job_id": str((active or {}).get("id")) if active else None,
                "started_at": (active or {}).get("started_at") or (active or {}).get("created_at"),
                "message": "Crypto-screening уже в очереди",
                "symbols": [],
                "accepted": 0,
                "scanned": 0,
                "rejected": 0,
                "skipped": False,
                "reused": False,
            }
        return {
            "robot_id": int(robot_id),
            "status": "queued",
            "job_id": str(job_id),
            "started_at": datetime.now(timezone.utc),
            "message": "Crypto-screening поставлен в очередь",
            "symbols": [],
            "accepted": 0,
            "scanned": 0,
            "rejected": 0,
            "skipped": False,
            "reused": False,
        }

    async def get_crypto_screening_status(
        self,
        db: Session,
        robot_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """Active/last crypto_screening job + last universe refresh time."""
        from app.core.background_jobs.repository import find_latest_job_for_robot

        await self.get_robot_by_id(db, robot_id, user_id)

        latest = find_latest_job_for_robot(
            db, job_type="crypto_screening", robot_id=int(robot_id)
        )
        last_ok = find_latest_job_for_robot(
            db,
            job_type="crypto_screening",
            robot_id=int(robot_id),
            statuses=("success")
        )

        universe_updated_at = None
        try:
            row = db.execute(
                text(
                    f"""
                    SELECT MAX(created_at)
                    FROM crypto_universe_daily
                    WHERE robot_id = :rid
                    """
                ),
                {"rid": int(robot_id)}
            ).first()
            universe_updated_at = row[0] if row else None
        except Exception:
            universe_updated_at = None

        status = "idle"
        job_id = None
        started_at = None
        finished_at = None
        error = None
        message = None
        if latest:
            st = str(latest.get("status") or "").strip().lower()
            job_id = str(latest.get("id"))
            started_at = latest.get("started_at") or latest.get("created_at")
            finished_at = latest.get("finished_at")
            error = latest.get("error")
            message = latest.get("message")
            if st in {"queued", "running", "success", "failed"}:
                status = st
            else:
                status = st or "idle"

        last_completed_at = None
        if last_ok and last_ok.get("finished_at"):
            last_completed_at = last_ok.get("finished_at")
        elif universe_updated_at is not None:
            last_completed_at = universe_updated_at

        return {
            "robot_id": int(robot_id),
            "status": status,
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "error": str(error)[:500] if error else None,
            "message": message,
            "last_completed_at": last_completed_at,
            "universe_updated_at": universe_updated_at,
        }

    async def get_universe_active_counts(
        self,
        db: Session,
        *,
        robot_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """Число активных инструментов в universe за сегодня и вчера (для UI /testing)."""
        from datetime import date, timedelta

        robot = await self.get_robot_by_id(db, robot_id, user_id)
        config = dict(robot.get("config") or {})
        broker = str(config.get("broker_type") or "").lower()
        is_crypto = broker == "bybit" or isinstance(config.get("bybit"), dict) or isinstance(
            config.get("crypto_universe"), dict
        )

        today = date.today()
        yesterday = today - timedelta(days=1)
        counts: Dict[str, int] = {}

        if is_crypto:
            rows = db.execute(
                text(
                    f"""
                    SELECT trade_date::text, COUNT(DISTINCT symbol)::int AS cnt
                    FROM crypto_universe_daily
                    WHERE robot_id = :rid
                      AND trade_date IN (:today, :yesterday)
                      AND LOWER(COALESCE(filter_result, '')) = 'accepted'
                    GROUP BY trade_date
                    """
                ),
                {"rid": int(robot_id), "today": today, "yesterday": yesterday}
            ).fetchall()
            source = "crypto_universe_daily"
        else:
            rows = db.execute(
                text(
                    f"""
                    SELECT trade_date::text, COUNT(DISTINCT ticker)::int AS cnt
                    FROM daily_universe
                    WHERE robot_id = :rid
                      AND trade_date IN (:today, :yesterday)
                      AND UPPER(COALESCE(filter_result, '')) = 'ACCEPT'
                    GROUP BY trade_date
                    """
                ),
                {"rid": int(robot_id), "today": today, "yesterday": yesterday}
            ).fetchall()
            source = "daily_universe"

        for r in rows:
            counts[str(r[0])] = int(r[1] or 0)

        return {
            "robot_id": int(robot_id),
            "today": today.isoformat(),
            "today_active": counts.get(today.isoformat(), 0),
            "yesterday": yesterday.isoformat(),
            "yesterday_active": counts.get(yesterday.isoformat(), 0),
            "source": source,
        }

    async def list_universe_daily(
        self,
        db: Session,
        *,
        robot_id: int,
        user_id: int,
        trade_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Строки universe за день: MOEX daily_universe или crypto_universe_daily."""
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        config = dict(robot.get("config") or {})
        broker = str(config.get("broker_type") or "").lower()
        is_crypto = broker == "bybit" or isinstance(config.get("bybit"), dict) or isinstance(
            config.get("crypto_universe"), dict
        )
        td = trade_date or date.today()

        if is_crypto:
            rows = db.execute(
                text(
                    f"""
                    SELECT id, robot_id, trade_date, symbol, source, filter_result, reject_reason,
                           turnover_24h, last_price, spread_percent, created_at
                    FROM crypto_universe_daily
                    WHERE robot_id = :rid AND trade_date = :td
                    ORDER BY created_at DESC
                    LIMIT 1000
                    """
                ),
                {"rid": int(robot_id), "td": td}
            ).fetchall()
            items = [
                {
                    "id": int(r[0]),
                    "robot_id": int(r[1]),
                    "trade_date": r[2],
                    "ticker": str(r[3]),
                    "source": str(r[4] or "crypto_screening"),
                    "filter_result": r[5],
                    "reject_reason": r[6],
                    "snapshot_id": None,
                    "price_at_filter": float(r[8]) if r[8] is not None else None,
                    "volume_at_filter": int(r[7]) if r[7] is not None else None,
                    "atr_value": None,
                    "gap_percent": float(r[9]) if r[9] is not None else None,
                    "applied_filters": None,
                    "created_at": r[10],
                }
                for r in rows
            ]
            return {"total": len(items), "items": items, "source": "crypto_universe_daily"}

        from app.modules.dms.service import dms_service

        data = await dms_service.list_daily_universe(db, user_id, robot_id=robot_id, trade_date=td)
        return {**data, "source": "daily_universe"}

    async def sync_live_universe_from_pipeline(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            *,
            force_refresh_snapshot: bool = False,
            force_recompute_universe: bool = False
    ) -> Dict[str, Any]:
        """Universe за сегодня → allowed_figis по режиму config.universe_mode."""
        from app.modules.dms.service import dms_service
        from app.modules.market_data.service import resolve_figi_and_ticker
        from app.modules.robots.universe import (
            UNIVERSE_MODE_FIXED,
            is_crypto_type2_config,
            normalize_crypto_universe_mode,
            normalize_universe_mode,
            resolve_crypto_symbols,
            resolve_fixed_tickers
        )

        robot = await self.get_robot_by_id(db, robot_id, user_id)
        config = dict(robot.get("config") or {})

        if is_crypto_type2_config(config):
            symbols = resolve_crypto_symbols(config)
            universe_mode = normalize_crypto_universe_mode(config)
            return {
                "allowed_figis": symbols,
                "allowed_symbols": symbols,
                "accepted_tickers": symbols,
                "snapshot_id": None,
                "analyzer_written_rows": 0,
                "recomputed": False,
                "universe_mode": universe_mode,
                "message": "crypto robot — DMS pipeline не используется",
            }

        universe_mode = normalize_universe_mode(config)
        if int(robot.get("type") or 0) != 2:
            figis = list(config.get("allowed_figis") or [])
            return {
                "allowed_figis": figis,
                "accepted_tickers": [],
                "snapshot_id": None,
                "analyzer_written_rows": 0,
                "recomputed": False,
                "universe_mode": universe_mode,
                "message": "not a trading robot",
            }

        if universe_mode == UNIVERSE_MODE_FIXED and not resolve_fixed_tickers(config):
            return {
                "allowed_figis": list(config.get("allowed_figis") or []),
                "accepted_tickers": [],
                "snapshot_id": None,
                "analyzer_written_rows": 0,
                "recomputed": False,
                "universe_mode": universe_mode,
                "message": "fixed_tickers пуст — укажите тикеры в настройках робота",
            }

        board = str(config.get("board") or "TQBR")
        init_result = await dms_service.initialize_trading_day(
            db,
            user_id=user_id,
            robot_id=robot_id,
            board=board,
            force_refresh_snapshot=force_refresh_snapshot or force_recompute_universe,
            force_recompute_universe=force_recompute_universe
        )
        today = datetime.now(timezone.utc).date()
        rows = db.execute(
            text(
                f"""
                SELECT ticker
                FROM daily_universe
                WHERE robot_id = :robot_id
                  AND trade_date = :trade_date
                  AND filter_result = 'ACCEPT'
                ORDER BY ticker
                """
            ),
            {"robot_id": robot_id, "trade_date": today}
        ).fetchall()
        tickers = [str(r[0]).upper() for r in rows if r and r[0]]
        if not tickers:
            return {
                "allowed_figis": list(config.get("allowed_figis") or []),
                "accepted_tickers": [],
                "snapshot_id": init_result.get("snapshot_id"),
                "analyzer_written_rows": int(init_result.get("analyzer_written_rows") or 0),
                "recomputed": bool(init_result.get("recomputed")),
                "universe_mode": universe_mode,
                "message": init_result.get("message") or "no ACCEPT tickers in daily_universe",
            }

        figis, ticker_by_figi, figi_by_ticker = await self._tickers_to_figis_for_robot(
            db, robot, tickers, user_id
        )

        cfg = dict(robot.get("config") or {})
        if figis:
            cfg["allowed_figis"] = sorted(set(figis))
            cfg["universe_mode"] = universe_mode
            cfg["instrument_map"] = {
                "ticker_by_figi": ticker_by_figi,
                "figi_by_ticker": figi_by_ticker,
            }
            db.execute(
                text(
                    f"""
                    UPDATE robots
                    SET config = CAST(:config AS jsonb),
                        date_modification = :now,
                        usermod = :user_id
                    WHERE id = :robot_id
                    """
                ),
                {
                    "robot_id": robot_id,
                    "user_id": user_id,
                    "config": json.dumps(cfg, ensure_ascii=False),
                    "now": datetime.now(timezone.utc),
                }
            )
            db.commit()
            logger.info("synced allowed_figis robot_id=%s count=%s mode=%s", robot_id, len(figis), universe_mode)
        else:
            logger.warning(
                "universe sync produced 0 figis robot_id=%s mode=%s; keeping existing allowed_figis",
                robot_id,
                universe_mode
            )
        return {
            "allowed_figis": sorted(set(figis)) if figis else list(cfg.get("allowed_figis") or []),
            "accepted_tickers": tickers,
            "snapshot_id": init_result.get("snapshot_id"),
            "analyzer_written_rows": int(init_result.get("analyzer_written_rows") or 0),
            "recomputed": bool(init_result.get("recomputed")),
            "universe_mode": universe_mode,
            "message": init_result.get("message") or ("no ACCEPT tickers in daily_universe" if not figis else None),
        }

    async def _ensure_trading_universe_on_enable(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            cfg: Dict[str, Any]
    ) -> None:
        """Подготовить universe перед включением type=2: MOEX → DMS, crypto → screening."""
        from app.modules.robots.universe import (
            UNIVERSE_MODE_FIXED,
            is_crypto_type2_config,
            normalize_crypto_universe_mode,
            normalize_universe_mode,
            resolve_crypto_symbols,
            resolve_fixed_tickers
        )

        if is_crypto_type2_config(cfg):
            if resolve_crypto_symbols(cfg):
                return
            mode = normalize_crypto_universe_mode(cfg)
            if mode == UNIVERSE_MODE_FIXED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Укажите символы ByBit (universe_mode=fixed, allowed_symbols)"
                )
            try:
                sync_res = await self.run_crypto_screening_job(db, robot_id, user_id)
            except HTTPException:
                raise
            except Exception as ex:
                logger.warning("crypto screening on enable failed robot_id=%s: %s", robot_id, ex)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Не удалось подобрать crypto universe: {ex}"
                ) from ex
            if sync_res.get("skipped") and not sync_res.get("reused"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=sync_res.get("message") or "Crypto screening пропущен"
                )
            symbols = list(sync_res.get("symbols") or [])
            if not symbols:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=sync_res.get("message") or "Crypto screening не вернул символы — ослабьте фильтры"
                )
            return

        mode = normalize_universe_mode(cfg)
        if list(cfg.get("allowed_figis") or []):
            return
        if mode == UNIVERSE_MODE_FIXED and not resolve_fixed_tickers(cfg):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите тикеры (universe_mode=fixed, fixed_tickers)"
            )
        try:
            sync_res = await self.sync_live_universe_from_pipeline(db, robot_id, user_id)
            if not list(sync_res.get("allowed_figis") or []):
                raise ValueError(sync_res.get("message") or "universe sync не вернул FIGI")
        except HTTPException:
            raise
        except Exception as ex:
            logger.warning("sync_live_universe on enable failed robot_id=%s: %s", robot_id, ex)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось подобрать universe: {ex}"
            ) from ex

    async def _tickers_to_figis_for_robot(
            self,
            db: Session,
            robot: Dict[str, Any],
            tickers: List[str],
            user_id: int
    ) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        from app.modules.market_data.service import resolve_figi_and_ticker

        token_row = robot.get("token") or {}
        token_str: Optional[str] = None
        token_id = token_row.get("id")
        if token_id:
            td = await token_service.get_token_by_id(db, int(token_id), user_id)
            token_str = (td or {}).get("token")

        figis: List[str] = []
        ticker_by_figi: Dict[str, str] = {}
        figi_by_ticker: Dict[str, str] = {}
        broker = str((robot.get("config") or {}).get("broker_type") or "tinvest").lower()
        for tk in tickers:
            if broker == "tinvest" and token_str:
                try:
                    fg, _, _ = await resolve_figi_and_ticker("", tk, "tinvest", token_str)
                    if fg:
                        fg_u = str(fg).upper()
                        tk_u = str(tk).upper()
                        figis.append(fg_u)
                        ticker_by_figi[fg_u] = tk_u
                        figi_by_ticker[tk_u] = fg_u
                        continue
                except Exception:
                    logger.warning("figi resolve failed ticker=%s robot_id=%s", tk, robot.get("id"))
                logger.info(
                    "skip non-figi ticker for tinvest universe ticker=%s robot_id=%s",
                    tk,
                    robot.get("id")
                )
                continue
            tk_u = str(tk).upper()
            figis.append(tk_u)
            ticker_by_figi[tk_u] = tk_u
            figi_by_ticker[tk_u] = tk_u
        return figis, ticker_by_figi, figi_by_ticker

    async def create_robot(
            self,
            db: Session,
            user_id: int,
            robot_data: schemas.RobotCreate
    ) -> dict:
        """Создание нового робота"""
        self.db = db

        # Проверяем уникальность имени
        check_name_query = queries.build_check_robot_name_exists_query(schema=settings.DB_SCHEMA)
        existing = db.execute(
            text(check_name_query),
            {"user_id": user_id, "name": robot_data.name}
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Робот с таким именем уже существует"
            )

        # Проверяем существование и активность токена
        check_token_query = queries.build_check_token_query(schema=settings.DB_SCHEMA)
        token = db.execute(
            text(check_token_query),
            {"token_id": robot_data.token_id, "user_id": user_id}
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Токен не найден или не активен"
            )
        token_type = int(token[1])

        if robot_data.config is not None:
            self._assert_broker_matches_token(robot_data.config, token_type)

        # Получаем тип робота из справочника
        robot_types = dict_queries.get_dictionary_data(
            db=db,
            table_name="ROBOT",
            column_name="TYPE",
            num_value=robot_data.type
        )

        if not robot_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неверный тип робота: {robot_data.type}"
            )


        # Логика статуса:
        status_value = 2  # По умолчанию остановлен

        now = datetime.now(timezone.utc)

        # Создаем робота
        insert_query = queries.build_create_robot_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(insert_query),
            {
                "user_id": user_id,
                "token_id": robot_data.token_id,
                "name": robot_data.name,
                "type": robot_data.type,
                "status": status_value,
                "usercre": user_id,
                "created_at": now
            }
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать робота"
            )

        robot_id = int(result[0])
        if int(robot_data.type) == 2:
            cfg = self._merge_trading_robot_config(robot_data.config)
            self._assert_broker_matches_token(cfg, token_type)
            risk = dict(cfg.get("risk") or {})
            poll_h = float(
                robot_data.poll_interval_hours
                if robot_data.poll_interval_hours is not None
                else max((1 / 60), float(cfg.get("poll_interval_hours") or (5 / 60)))
            )
            th_start = self._strip_msk_hhmm(
                robot_data.trading_hours_start or risk.get("trading_hours_start"),
                "10:00"
            )
            th_end = self._strip_msk_hhmm(
                robot_data.trading_hours_end or risk.get("trading_hours_end"),
                "18:45"
            )
            weekdays = int(
                robot_data.allowed_weekdays
                if robot_data.allowed_weekdays is not None
                else risk.get("allowed_weekdays") or 31
            )
            await self._bootstrap_trading_robot(
                db,
                robot_id=robot_id,
                user_id=user_id,
                config=cfg,
                poll_interval_hours=poll_h,
                trading_hours_start=th_start,
                trading_hours_end=th_end,
                allowed_weekdays=weekdays
            )
        elif int(robot_data.type) == 1:
            cfg = dict(robot_data.config or {})
            poll_h = float(
                robot_data.poll_interval_hours
                if robot_data.poll_interval_hours is not None
                else max((1 / 60), float(cfg.get("poll_interval_hours") or (5 / 60)))
            )
            th_start = self._strip_msk_hhmm(robot_data.trading_hours_start, "10:00")
            th_end = self._strip_msk_hhmm(robot_data.trading_hours_end, "18:45")
            weekdays = int(robot_data.allowed_weekdays if robot_data.allowed_weekdays is not None else 31)
            await self._bootstrap_portfolio_robot(
                db,
                robot_id=robot_id,
                user_id=user_id,
                config=cfg,
                poll_interval_hours=poll_h,
                trading_hours_start=th_start,
                trading_hours_end=th_end,
                allowed_weekdays=weekdays
            )

        db.commit()

        # Получаем созданного робота с полной информацией
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        return robot

    async def _resolve_duplicate_robot_name(
            self,
            db: Session,
            user_id: int,
            requested_name: Optional[str],
            source_name: str
    ) -> str:
        base = (requested_name or f"{source_name} (copy)").strip()
        if not base:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name не может быть пустым"
            )
        check_name_query = queries.build_check_robot_name_exists_query(schema=settings.DB_SCHEMA)
        candidate = base
        suffix = 2
        while True:
            existing = db.execute(
                text(check_name_query),
                {"user_id": user_id, "name": candidate}
            ).first()
            if not existing:
                return candidate
            candidate = f"{base} ({suffix})"
            suffix += 1
            if suffix > 50:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Не удалось подобрать уникальное имя для копии робота"
                )

    async def duplicate_robot(
            self,
            db: Session,
            user_id: int,
            request: schemas.RobotDuplicateRequest
    ) -> dict:
        """Создать копию робота: strategy/risk/costs/schedule + reset universe (§7.8)."""
        from app.modules.robots.config.duplicate import (
            DEFAULT_COPY_SECTIONS,
            DEFAULT_RESET_SECTIONS,
            build_duplicated_config,
            resolve_schedule_from_source
        )
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        self.db = db
        source = await self.get_robot_by_id(db, request.source_robot_id, user_id)
        robot_type = int(source.get("type") or 0)
        if robot_type not in (1, 2):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Поддерживаются только типы 1 и 2"
            )

        source_cfg = dict(source.get("config") or {})
        source_broker = normalize_broker_type(str(source_cfg.get("broker_type") or "tinvest"))
        target_broker = normalize_broker_type(str(request.broker_type or source_broker))

        copy_sections = list(request.copy_sections or DEFAULT_COPY_SECTIONS)
        reset_sections = list(request.reset_sections or DEFAULT_RESET_SECTIONS)

        try:
            config = build_duplicated_config(
                robot_type=robot_type,
                source_config=source_cfg,
                target_broker=target_broker,
                copy_sections=copy_sections,
                reset_sections=reset_sections
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc)
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Некорректный config: {exc}"
            ) from exc

        poll_h, th_start, th_end, weekdays = resolve_schedule_from_source(
            source_cfg,
            source.get("schedule"),
            copy_schedule="schedule" in copy_sections
        )

        name = await self._resolve_duplicate_robot_name(
            db,
            user_id,
            request.name,
            str(source.get("name") or "Robot")
        )
        token_id = int(
            request.token_id
            if request.token_id is not None
            else (source.get("token") or {}).get("id") or 0
        )
        if token_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="token_id обязателен для копии робота"
            )

        created = await self.create_robot(
            db,
            user_id,
            schemas.RobotCreate(
                name=name,
                type=robot_type,
                token_id=token_id
            )
        )
        robot_id = int(created["id"])

        if robot_type == 2:
            await self._bootstrap_trading_robot(
                db,
                robot_id=robot_id,
                user_id=user_id,
                config=config,
                poll_interval_hours=poll_h,
                trading_hours_start=th_start,
                trading_hours_end=th_end,
                allowed_weekdays=weekdays
            )
            db.commit()
        else:
            await self.update_robot_config(db, robot_id, user_id, config)
            await self._replace_robot_schedule(
                db=db,
                robot_id=robot_id,
                user_id=user_id,
                poll_interval_hours=poll_h,
                trading_hours_start=th_start,
                trading_hours_end=th_end,
                allowed_weekdays=weekdays
            )
            db.commit()

        return await self.get_robot_by_id(db, robot_id, user_id)

    async def update_robot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            patch: schemas.RobotUpdate
    ) -> dict:
        """Обновляет базовые поля робота (name/token/type/status/config)."""
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        def _normalized_broker(value: Any) -> str:
            from app.modules.robots.trading.brokers.routing import normalize_broker_type

            return normalize_broker_type(str(value or "").strip())

        updates: Dict[str, Any] = {}
        if patch.name is not None:
            name = patch.name.strip()
            if not name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название не может быть пустым")
            if name != robot.get("name"):
                check_name_query = queries.build_check_robot_name_exists_query(schema=settings.DB_SCHEMA)
                existing = db.execute(text(check_name_query), {"user_id": user_id, "name": name}).first()
                if existing and int(existing[0]) != int(robot_id):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Робот с таким именем уже существует")
            updates["name"] = name

        new_token_type: Optional[int] = None
        if patch.token_id is not None:
            check_token_query = queries.build_check_token_query(schema=settings.DB_SCHEMA)
            token = db.execute(text(check_token_query), {"token_id": patch.token_id, "user_id": user_id}).first()
            if not token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен не найден или не активен")
            updates["token_id"] = int(patch.token_id)
            new_token_type = int(token[1])

        if patch.type is not None:
            if int(patch.type) not in (1, 2):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Поддерживаются только типы 1 и 2")
            updates["type"] = int(patch.type)

        if patch.status is not None:
            if int(patch.status) not in (1, 2):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Статус должен быть 1 или 2")
            updates["status"] = int(patch.status)

        if patch.config is not None:
            current_cfg = dict(robot.get("config") or {})
            incoming_cfg = dict(patch.config)
            merged_input = {**current_cfg, **incoming_cfg}
            if "pipeline" in incoming_cfg:
                merged_input["pipeline"] = incoming_cfg.get("pipeline")
            if int(updates.get("type", robot.get("type") or 0)) == 2:
                cfg = self._merge_trading_robot_config(merged_input)
            else:
                cfg = merged_input
            token_id_for_check = int(updates.get("token_id") or (robot.get("token") or {}).get("id") or 0)
            if token_id_for_check > 0:
                token_row = db.execute(
                    text(queries.build_check_token_query(schema=settings.DB_SCHEMA)),
                    {"token_id": token_id_for_check, "user_id": user_id}
                ).first()
                if token_row:
                    self._assert_broker_matches_token(cfg, int(token_row[1]))
            updates["config"] = json.dumps(cfg, ensure_ascii=False)
        elif new_token_type is not None:
            current_cfg = dict(robot.get("config") or {})
            self._assert_broker_matches_token(current_cfg, new_token_type)
            updates["config"] = json.dumps(current_cfg, ensure_ascii=False)

        set_parts = []
        params: Dict[str, Any] = {
            "robot_id": robot_id,
            "user_id": user_id,
            "usermod": user_id,
            "now": datetime.now(timezone.utc),
        }
        if updates:
            for key, value in updates.items():
                set_parts.append(f"{key} = :{key}")
                params[key] = value

            update_sql = f"""
                UPDATE robots
                SET {", ".join(set_parts)},
                    usermod = :usermod,
                    date_modification = :now
                WHERE id = :robot_id AND user_id = :user_id AND status != 0
                RETURNING id
            """
            changed = db.execute(text(update_sql), params).first()
            if not changed:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось обновить робота")

        schedule_changed = any([
            patch.poll_interval_hours is not None,
            patch.trading_hours_start is not None,
            patch.trading_hours_end is not None,
            patch.allowed_weekdays is not None,
        ])
        if schedule_changed:
            existing_schedule = robot.get("schedule") or {}
            if "config" in updates:
                raw_cfg = updates["config"]
                current_cfg = json.loads(raw_cfg) if isinstance(raw_cfg, str) else dict(raw_cfg or {})
            else:
                current_cfg = dict(robot.get("config") or {})
            resolved_poll_hours = float(
                patch.poll_interval_hours
                if patch.poll_interval_hours is not None
                else max((1 / 60), float(existing_schedule.get("interval_seconds") or 3600) / 3600.0)
            )
            resolved_start = str(patch.trading_hours_start if patch.trading_hours_start is not None else "10:00")
            resolved_end = str(patch.trading_hours_end if patch.trading_hours_end is not None else "18:45")
            resolved_weekdays = int(patch.allowed_weekdays if patch.allowed_weekdays is not None else int(existing_schedule.get("weekdays") or 31))
            self._sync_risk_schedule_fields(
                current_cfg,
                trading_hours_start=resolved_start,
                trading_hours_end=resolved_end,
                allowed_weekdays=resolved_weekdays
            )
            if int(robot.get("type") or updates.get("type") or 0) == 2:
                self._validate_robot_config(current_cfg)
            updates["config"] = json.dumps(current_cfg, ensure_ascii=False)
            await self._replace_robot_schedule(
                db=db,
                robot_id=robot_id,
                user_id=user_id,
                poll_interval_hours=resolved_poll_hours,
                trading_hours_start=resolved_start,
                trading_hours_end=resolved_end,
                allowed_weekdays=resolved_weekdays
            )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)



# TODO: Добавить валидацию обязательноых полей для включения
#     Первый статус - наличие рефреш интервала
    async def change_robot_status(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            new_status: int  # 1 - включить, 2 - выключить
    ) -> dict:
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        if new_status == 1:
            token = robot.get("token", {})
            if not token.get("id") or token.get("status") != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="У робота нет активного токена доступа"
                )
            if int(robot.get("type") or 0) == 2:
                cfg = dict(robot.get("config") or {})
                try:
                    await self._ensure_trading_universe_on_enable(db, robot_id, user_id, cfg)
                except HTTPException:
                    raise

        now = datetime.now(timezone.utc)

        # Обновляем статус
        update_query = queries.build_change_robot_status_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(update_query),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "status": new_status,
                "now": now,
                "usermod": user_id
            }
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось изменить статус робота"
            )

        db.commit()

        if new_status == 2 and int(robot.get("type") or 0) == 2:
            try:
                from app.core.background_jobs.repository import cancel_live_session_jobs_for_robot

                n = cancel_live_session_jobs_for_robot(
                    db,
                    robot_id=int(robot_id),
                    reason=f"robot {robot_id} disabled by user {user_id}"
                )
                db.commit()
                if n:
                    logger.info(
                        "cancelled %s live_trading_session job(s) robot_id=%s",
                        n,
                        robot_id
                    )
            except Exception as exc:
                logger.warning(
                    "failed to cancel live sessions on disable robot_id=%s: %s",
                    robot_id,
                    exc
                )
                try:
                    db.rollback()
                except Exception:
                    pass

        # Получаем обновленного робота
        updated_robot = await self.get_robot_by_id(db, robot_id, user_id)

        return updated_robot

    async def delete_robot(
            self,
            db: Session,
            robot_id: int,
            user_id: int
    ) -> dict:
        """Мягкое удаление робота (status=0)"""
        self.db = db
        await self.get_robot_by_id(db, robot_id, user_id)

        now = datetime.now(timezone.utc)
        delete_query = queries.build_soft_delete_robot_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(delete_query),
            {"robot_id": robot_id, "user_id": user_id, "usermod": user_id, "now": now}
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить робота"
            )
        db.commit()
        return {"id": result[0], "deleted": True}

    async def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Возвращает список доступных стратегий и их схем параметров."""
        from app.modules.robots.trading.strategies import list_strategies
        return list_strategies()

    async def get_strategy_info(self, name: str) -> Dict[str, Any]:
        """Returns one strategy metadata by name."""
        from app.modules.robots.trading.strategies import get_strategy_info
        info = get_strategy_info(name)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Стратегия '{name}' не найдена"
            )
        return info

    async def update_robot_config(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            config: Dict[str, Any]
    ) -> dict:
        """
        Обновляет конфиг робота с базовой валидацией strategy_params.
        """
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        current_cfg = dict(robot.get("config") or {})
        current_broker_raw = current_cfg.get("broker_type")
        requested_broker = normalize_broker_type(str((config or {}).get("broker_type") or current_broker_raw or "tinvest"))
        if current_broker_raw:
            current_broker = normalize_broker_type(str(current_broker_raw))
            if requested_broker != current_broker:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "broker_type нельзя изменить для существующего робота. "
                        "Создайте нового робота (или используйте duplicate workflow)."
                    )
                )
        token_type_raw = (robot.get("token") or {}).get("type")
        if token_type_raw is not None:
            self._assert_broker_matches_token(config if isinstance(config, dict) else {}, int(token_type_raw))

        robot_type = int(robot.get("type") or 0)
        if robot_type == 2:
            self._validate_robot_config(config)
        else:
            if not isinstance(config, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный config: expected object"
                )
            try:
                from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config

                validated = validate_robot_config(
                    robot_type=1,
                    raw=config or {},
                    broker_type=current_broker
                )
                normalized = dump_robot_config(validated)
                extra = {k: v for k, v in (config or {}).items() if k not in set(normalized.keys())}
                config.clear()
                config.update(normalized)
                config.update(extra)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Некорректный config: {e}"
                )

        update_query = queries.build_update_robot_config_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(update_query),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "config": json.dumps(config, ensure_ascii=False),
                "usermod": user_id,
                "now": datetime.now(timezone.utc)
            }
        ).first()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить конфигурацию робота"
            )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)

    async def update_robot_schedule(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            poll_interval_hours: float,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int
    ) -> dict:
        """Обновляет/создает активное расписание в robot_schedules."""
        self.db = db
        await self.get_robot_by_id(db, robot_id, user_id)
        await self._replace_robot_schedule(
            db=db,
            robot_id=robot_id,
            user_id=user_id,
            poll_interval_hours=poll_interval_hours,
            trading_hours_start=trading_hours_start,
            trading_hours_end=trading_hours_end,
            allowed_weekdays=allowed_weekdays
        )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)

    def validate_robot_config_payload(
            self,
            *,
            robot_type: int,
            config: Dict[str, Any],
            broker_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Profile-based validate + normalize without DB write."""
        from app.modules.robots.config.profiles import (
            dump_robot_config,
            resolve_schema_profile,
            validate_robot_config
        )

        try:
            profile = resolve_schema_profile(robot_type, config or {}, broker_type)
            model = validate_robot_config(
                robot_type=robot_type,
                raw=config or {},
                broker_type=broker_type
            )
            normalized = dump_robot_config(model)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Некорректный config: {e}"
            )

        return {
            "schema_profile": profile,
            "normalized_config": normalized,
        }

    async def _replace_robot_schedule(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            poll_interval_hours: float,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int
    ) -> None:
        def _normalize_hhmm(hhmm: str) -> str:
            parts = (hhmm or "00:00").strip().split(":")
            h = int(parts[0]) if len(parts) > 0 else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            h = max(0, min(23, h))
            m = max(0, min(59, m))
            return f"{h:02d}:{m:02d}:00+03:00"

        start_time_tz = _normalize_hhmm(trading_hours_start)
        end_time_tz = _normalize_hhmm(trading_hours_end)
        normalized_hours = max((1 / 60), min(12.0, float(poll_interval_hours)))
        interval_seconds = int(round(normalized_hours * 3600))
        interval_seconds = max(60, interval_seconds)

        disable_sql = f"""
            UPDATE robot_schedules
            SET is_active = 0,
                usermod = :usermod,
                date_modification = :now
            WHERE robot_id = :robot_id
              AND COALESCE(is_active, 1) = 1
        """
        db.execute(text(disable_sql), {"robot_id": robot_id, "usermod": user_id, "now": datetime.now(timezone.utc)})

        insert_sql = f"""
            INSERT INTO robot_schedules
                (robot_id, schedule_type, interval_seconds, start_time, end_time, weekdays, is_active, priority, description, usercre, date_creation)
            VALUES
                (:robot_id, 2, :interval_seconds, CAST(:start_time AS timetz), CAST(:end_time AS timetz), :weekdays, 1, 100, :description, :usercre, :created_at)
        """
        db.execute(
            text(insert_sql),
            {
                "robot_id": robot_id,
                "interval_seconds": interval_seconds,
                "start_time": start_time_tz,
                "end_time": end_time_tz,
                "weekdays": int(max(0, min(127, allowed_weekdays))),
                "description": "UI schedule",
                "usercre": user_id,
                "created_at": datetime.now(timezone.utc),
            }
        )

    @staticmethod
    def _iter_trade_dates(from_dt: datetime, to_dt: datetime) -> List[date]:
        d0 = from_dt.date()
        d1 = to_dt.date()
        out: List[date] = []
        cur = d0
        while cur <= d1:
            if cur.weekday() < 5:
                out.append(cur)
            cur += timedelta(days=1)
        return out

    @staticmethod
    def _iter_calendar_dates(from_dt: datetime, to_dt: datetime) -> List[date]:
        d0 = from_dt.date()
        d1 = to_dt.date()
        out: List[date] = []
        cur = d0
        while cur <= d1:
            out.append(cur)
            cur += timedelta(days=1)
        return out

    async def _fetch_board_issuesize_map(self, *, board: str) -> Dict[str, float]:
        from app.modules.robots.trading.data.providers.moex_snapshots import fetch_board_issuesize_map

        return await fetch_board_issuesize_map(board=board)

    async def _fetch_moex_history_snapshot_day(
            self,
            *,
            day: date,
            board: str = "TQBR",
            user_id: Optional[int] = None,
            run_id: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        from app.modules.robots.trading.data.providers.moex_snapshots import fetch_moex_history_snapshot_day

        return await fetch_moex_history_snapshot_day(
            day=day,
            board=board,
            user_id=user_id,
            run_id=run_id
        )

    async def _ensure_daily_snapshot_history(
            self,
            db: Session,
            *,
            day: date,
            board: str = "TQBR",
            user_id: Optional[int] = None,
            run_id: Optional[int] = None
    ) -> Optional[int]:
        from app.modules.robots.trading.data import get_market_data_facade

        return await get_market_data_facade().ensure_snapshot_day(
            db,
            day=day,
            board=board,
            user_id=user_id,
            run_id=run_id
        )

    @staticmethod
    def _history_derive_engine_params(
            config: Dict[str, Any],
            *,
            dms_service
    ) -> Dict[str, Any]:
        """Поля симуляции и pipeline из уже смерженного config (общий путь sync и deferred)."""
        from app.modules.robots.config.migration import (
            effective_pipeline_from_config,
            historical_screening_from_config,
            signal_generation_from_config
        )
        from app.modules.robots.universe import (
            normalize_universe_mode,
            normalize_crypto_universe_mode,
            universe_pipeline_filters,
            universe_whitelist_tickers
        )
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        config = dict(config)
        broker = normalize_broker_type(str(config.get("broker_type") or "tinvest"))
        is_crypto = broker == "bybit"
        if is_crypto:
            # type2_bybit: не гоняем MOEX П1/П2 (иначе data_source=bybit → 422).
            pipeline = {"mode": "ALL", "filters": []}
            pipeline_filters: List[Any] = []
            _hist = None
            _sig = signal_generation_from_config(config)
        else:
            pipeline = effective_pipeline_from_config(config)
            pipeline_filters = list(pipeline.get("filters") or [])
            _hist = historical_screening_from_config(config)
            _sig = signal_generation_from_config(config)
        # Как в DMS: до загрузки D1 для ATR% отфильтровать всё, что не требует свечей
        # (turnover/min_step_ratio — только поля снапшота; раньше они шли в «финал» и раздували fast_pass).
        fast_pipeline_filters = [
            f for f in pipeline_filters
            if str((f or {}).get("type") or "").lower() != "atr"
        ]
        universe_mode = (
            normalize_crypto_universe_mode(config)
            if is_crypto
            else normalize_universe_mode(config)
        )
        effective_pipeline_filters = universe_pipeline_filters(config, pipeline_filters)
        effective_fast_pipeline_filters = universe_pipeline_filters(config, fast_pipeline_filters)
        allowed_tickers_whitelist = universe_whitelist_tickers(config)
        strategy_name = str(_sig.strategy or config.get("strategy") or "grain_seed").strip().lower()
        from app.modules.robots.trading.strategies import get_strategy_info as _get_strategy_info
        if _get_strategy_info(strategy_name) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Указанная стратегия не найдена"
            )
        strategy_params = dict(_sig.params or config.get("strategy_params") or {})
        if _hist is not None:
            if _hist.interval and not strategy_params.get("moex_analysis_interval"):
                strategy_params["moex_analysis_interval"] = _hist.interval
            if _hist.lookback_days and not strategy_params.get("candle_days"):
                strategy_params["candle_days"] = _hist.lookback_days
        from app.modules.robots.trading.intervals import resolve_candle_interval_roles

        interval_roles = resolve_candle_interval_roles(strategy_params)
        exec_iv = interval_roles.execution
        moex_iv = interval_roles.moex_history
        interval_code_num = exec_iv.code_num
        interval_code = exec_iv.cache_label
        risk = dict(config.get("risk") or {})
        board = "TQBR"
        exec_cfg = dict(config.get("execution_model") or {})
        slippage_pct = float((exec_cfg.get("slippage_pct")) or 0.0)
        latency_sec = float((exec_cfg.get("latency_sec")) or 0.0)
        execution_model = str(exec_cfg.get("model") or "NEXT_BAR_OPEN").upper()
        pipeline_mode = str(pipeline.get("mode") or "ALL").upper()
        return {
            "historical_screening": _hist,
            "signal_generation": _sig,
            "pipeline_filters": effective_pipeline_filters,
            "fast_pipeline_filters": effective_fast_pipeline_filters,
            "universe_mode": universe_mode,
            "allowed_tickers_whitelist": allowed_tickers_whitelist,
            "raw_pipeline_filters": pipeline_filters,
            "strategy_name": strategy_name,
            "strategy_params": strategy_params,
            "interval_roles": interval_roles,
            "interval_code_num": interval_code_num,
            "interval_code": interval_code,
            "moex_interval_code_num": moex_iv.code_num,
            "moex_interval_code": moex_iv.cache_label,
            "min_required_candles": exec_iv.min_required_candles,
            "moex_min_required_candles": moex_iv.min_required_candles,
            "shared_canonical": exec_iv.shared_canonical,
            "resolved_interval": exec_iv,
            "resolved_moex_interval": moex_iv,
            "risk": risk,
            "board": board,
            "slippage_pct": slippage_pct,
            "latency_sec": latency_sec,
            "execution_model": execution_model,
            "pipeline_mode": pipeline_mode,
        }

    #///EPIC Backtesting.ITEM HistoryBacktest.TOPIC Endpoint Lifecycle [1]
    #/// Оркестрация /api/robots/history-backtest: merge config, подготовка history,
    #/// отбор тикеров через pipeline, загрузка свечей из cache/MOEX, симуляция и persist.
    #/// Источники данных приоритетно локальные таблицы ganaly/backtest, затем внешние API.
    async def run_robot_history_backtest(
            self,
            db: Session,
            user_id: int,
            request: schemas.RobotHistoryBacktestRequest,
            *,
            deferred_run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Исторический бэктест: history-таблицы -> MOEX History API, затем симуляция."""
        from app.modules.robots.trading.backtest.persistence import BacktestPersistence, BacktestPersistPayload
        from app.modules.robots.trading.backtest.metrics import BacktestMetricsCalculator
        from app.modules.corporate_actions.dividend_calendar_service import (
            DividendCalendarService,
            policy_from_robot_config
        )
        from app.modules.dms.service import dms_service

        robot: Optional[Dict[str, Any]] = None
        run_id: int
        # Нормализуем диапазон строго в UTC один раз и далее используем только его.
        requested_from_utc = _coerce_utc_dt(request.from_date)
        requested_to_utc = _coerce_utc_dt(request.to_date)
        if requested_from_utc is None or requested_to_utc is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from_date/to_date must be valid ISO datetimes"
            )

        if deferred_run_id is not None:
            row = db.execute(
                text(
                    f"""
                    SELECT user_id, robot_id, status, config_snapshot,
                           requested_from, requested_to, initial_capital, board
                    FROM backtest_runs
                    WHERE id = :id
                    """
                ),
                {"id": deferred_run_id}
            ).mappings().first()
            if not row or int(row.get("user_id") or 0) != int(user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
            st = str(row.get("status") or "").upper()
            if st in ("SUCCESS", "FAILED", "CANCELLED"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Прогон уже завершён"
                )
            snap = row.get("config_snapshot")
            if isinstance(snap, str):
                try:
                    config = dict(json.loads(snap))
                except json.JSONDecodeError:
                    config = {}
            elif isinstance(snap, dict):
                config = dict(snap)
            else:
                config = {}
            rid_row = row.get("robot_id")
            robot_pk = int(rid_row) if rid_row is not None else None
            run_id = int(deferred_run_id)
            if robot_pk is not None:
                robot = await self.get_robot_by_id(db, robot_pk, user_id)
        else:
            if request.robot_id is not None:
                robot = await self.get_robot_by_id(db, request.robot_id, user_id)
                if int(robot.get("type") or 0) != 2:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Backtest доступен только для торговых роботов type=2"
                    )
                config = dict(robot.get("config") or {})
            else:
                config = dict(request.config or {})
                if not config.get("strategy"):
                    config["strategy"] = (request.strategy or "grain_seed").strip().lower()
                strat = str(config.get("strategy") or "").strip().lower()
                from app.modules.robots.trading.strategies import get_strategy_info as _get_strategy_info
                if _get_strategy_info(strat) is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Указанная стратегия не найдена"
                    )

            req_strat = (request.strategy or "").strip().lower() or None
            if req_strat:
                from app.modules.robots.trading.strategies import get_strategy_info as _get_strategy_info
                if _get_strategy_info(req_strat) is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Указанная стратегия не найдена"
                    )

            request_cfg = dict(request.config or {})
            if request_cfg:
                # Accept UI alias riskManagment and normalize to backend "risk".
                rm = request_cfg.pop("riskManagment", None)
                if isinstance(rm, dict):
                    risk_alias: Dict[str, Any] = {}
                    if rm.get("стопЛосс") is not None:
                        risk_alias["stop_loss_percent"] = rm.get("стопЛосс")
                    if rm.get("тейкПрофит") is not None:
                        risk_alias["take_profit_percent"] = rm.get("тейкПрофит")
                    if rm.get("доляПозиции") is not None:
                        risk_alias["max_position_percent"] = rm.get("доляПозиции")
                    if rm.get("максПозиция") is not None:
                        risk_alias["max_position_rub"] = rm.get("максПозиция")
                    request_cfg["risk"] = {**dict(request_cfg.get("risk") or {}), **risk_alias}
                config = {**config, **request_cfg}
                base_cfg = dict((robot.get("config") or {})) if robot else {}
                if isinstance(config.get("pipeline"), dict):
                    config["pipeline"] = {**dict(base_cfg.get("pipeline") or {}), **dict(config.get("pipeline") or {})}
                if isinstance(config.get("costs"), dict):
                    config["costs"] = {**dict(base_cfg.get("costs") or {}), **dict(config.get("costs") or {})}
                if isinstance(config.get("risk"), dict):
                    config["risk"] = {**dict(base_cfg.get("risk") or {}), **dict(config.get("risk") or {})}
                if isinstance(config.get("strategy_params"), dict):
                    config["strategy_params"] = {**dict(base_cfg.get("strategy_params") or {}), **dict(config.get("strategy_params") or {})}

        p = self._history_derive_engine_params(config, dms_service=dms_service)
        from app.modules.robots.universe import (
            UNIVERSE_MODE_AUTO,
            UNIVERSE_MODE_FIXED,
            normalize_crypto_universe_mode,
            normalize_universe_mode,
            resolve_crypto_symbols,
            resolve_fixed_tickers,
            universe_filter_snapshot_row
        )
        from app.modules.robots.trading.brokers.routing import normalize_broker_type

        broker_type = normalize_broker_type(str(config.get("broker_type") or "tinvest"))
        is_crypto_backtest = broker_type == "bybit"
        if is_crypto_backtest:
            crypto_mode = normalize_crypto_universe_mode(config)
            if crypto_mode == UNIVERSE_MODE_FIXED and not resolve_crypto_symbols(config):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Для crypto backtest укажите allowed_symbols (universe_mode=fixed)"
                )
        elif p["universe_mode"] == UNIVERSE_MODE_FIXED and not resolve_fixed_tickers(config):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Укажите тикеры (universe_mode=fixed, fixed_tickers)"
            )
        pipeline_filters = p["pipeline_filters"]
        fast_pipeline_filters = p["fast_pipeline_filters"]
        allowed_tickers_whitelist = p.get("allowed_tickers_whitelist")
        strategy_name = p["strategy_name"]
        strategy_params = p["strategy_params"]
        interval_code_num = p["interval_code_num"]
        interval_code = p["interval_code"]
        moex_interval_code_num = int(p.get("moex_interval_code_num") or interval_code_num)
        moex_interval_code = str(p.get("moex_interval_code") or interval_code)
        resolved_exec_iv = p.get("resolved_interval")
        execution_moex_gap_ok = (
            resolved_exec_iv is not None and resolved_exec_iv.supports_moex_iss
        )
        risk = p["risk"]
        board = p["board"]
        slippage_pct = p["slippage_pct"]
        latency_sec = p["latency_sec"]
        execution_model = p["execution_model"]
        pipeline_mode = p["pipeline_mode"]

        bybit_token_id: Optional[int] = None
        if is_crypto_backtest:
            if request.token_id is not None:
                bybit_token_id = int(request.token_id)
            elif robot:
                _tok = (robot.get("token") or {}) if isinstance(robot.get("token"), dict) else {}
                if _tok.get("id") is not None:
                    bybit_token_id = int(_tok["id"])
                elif robot.get("token_id") is not None:
                    bybit_token_id = int(robot["token_id"])

        stage_logs: List[str] = []
        _roles = p.get("interval_roles")
        if _roles is not None:
            stage_logs.append(
                f"intervals: execution={_roles.execution.cache_label} (T-Invest/live/sim) "
                f"moex_history={_roles.moex_history.cache_label} (MOEX prefetch)"
            )
        stage_logs.append(
            f"universe: mode={p['universe_mode']} pipeline_filters={len(pipeline_filters)}"
        )
        div_policy = policy_from_robot_config(config)
        div_svc = DividendCalendarService(db)

        if deferred_run_id is None:
            robot_pk = request.robot_id if request.robot_id is not None else None
            run_sql_status = "QUEUED" if bool(getattr(request, "async_execution", False)) else "RUNNING"
            run_id = int(
                db.execute(
                    text(f"""
                INSERT INTO backtest_runs
                (robot_id, user_id, requested_from, requested_to, started_at, status, board, initial_capital, config_snapshot, execution_model, cancel_requested, partial_result)
                VALUES (:robot_id, :user_id, :requested_from, :requested_to, :started_at, :run_status, :board, :initial_capital, CAST(:config_snapshot AS jsonb), CAST(:execution_model AS jsonb), false, false)
                RETURNING id
            """),
                    {
                        "robot_id": robot_pk,
                        "user_id": user_id,
                        "requested_from": requested_from_utc,
                        "requested_to": requested_to_utc,
                        "started_at": datetime.now(timezone.utc),
                        "run_status": run_sql_status,
                        "board": board,
                        "initial_capital": request.initial_capital,
                        "config_snapshot": json.dumps(config, ensure_ascii=False),
                        "execution_model": json.dumps({
                            "slippage_pct": slippage_pct,
                            "latency_sec": latency_sec,
                            "model": execution_model,
                            "commission_model": "robot_costs",
                            "source_priority": [
                                "shared_market_candles",
                                "market_snapshot_history",
                                "market_snapshot_data_history",
                                "moex_iss_history_api",
                                "candles_cache",
                                "moex_iss_candles_api",
                            ],
                        }, ensure_ascii=False),
                    }
                ).scalar()
            )
            db.commit()
            if request.async_execution:
                try:
                    from app.modules.robots.trading.backtest.run_file_logger import (
                        log_backtest_run_info,
                        ensure_backtest_run_log
                    )

                    ensure_backtest_run_log(
                        int(run_id),
                        started_at=datetime.now(timezone.utc),
                        meta={
                            "run_id": int(run_id),
                            "user_id": int(user_id),
                            "status": "QUEUED",
                            "broker_type": broker_type,
                            "strategy": strategy_name,
                        }
                    )
                    log_backtest_run_info(
                        "QUEUED | ожидание фонового воркера (lane=heavy). "
                        "Лог продолжится после перехода в RUNNING."
                    )
                except Exception as log_ex:
                    logger.warning("backtest queued log open failed run_id=%s: %s", run_id, log_ex)
                return {"__async_enqueue__": True, "run_id": int(run_id), "status": "queued"}
        else:
            try:
                res = db.execute(
                    text(
                        f"""
                        UPDATE backtest_runs
                        SET status = 'RUNNING',
                            run_phase = 'fetching_market_data',
                            started_at = COALESCE(started_at, :ts)
                        WHERE id = :rid
                          AND status = 'QUEUED'
                          AND cancel_requested = false
                        """
                    ),
                    {"ts": datetime.now(timezone.utc), "rid": run_id}
                )
                db.commit()
                if (getattr(res, "rowcount", None) or 0) == 0:
                    row2 = db.execute(
                        text(
                            f"""
                            SELECT status, cancel_requested
                            FROM backtest_runs
                            WHERE id = :rid
                            LIMIT 1
                            """
                        ),
                        {"rid": run_id}
                    ).mappings().first()
                    if not row2:
                        return {"__worker_aborted__": True}
                    su = str(row2.get("status") or "").upper()
                    cq = bool(row2.get("cancel_requested"))
                    if su == "CANCELLED" or (su == "QUEUED" and cq):
                        return {"__worker_aborted__": True}
            except Exception:
                db.rollback()

        bt_run_id: Optional[int] = None
        _clear_backtest_run_tracking(run_id)
        run_started_at = datetime.now(timezone.utc)
        progress_bind = db.get_bind()

        from app.modules.robots.trading.backtest.run_file_logger import (
            close_backtest_run_log,
            log_backtest_run_exception,
            log_backtest_run_info,
            ensure_backtest_run_log
        )

        backtest_log_status = "RUNNING"
        backtest_log_error: Optional[str] = None
        backtest_log_summary: Optional[Dict[str, Any]] = None
        try:
            ensure_backtest_run_log(
                run_id,
                started_at=run_started_at,
                meta={
                    "run_id": int(run_id),
                    "user_id": int(user_id),
                    "robot_id": robot_pk,
                    "deferred": deferred_run_id is not None,
                    "strategy": strategy_name,
                    "broker_type": broker_type,
                    "board": board,
                    "from_date": requested_from_utc.isoformat(),
                    "to_date": requested_to_utc.isoformat(),
                    "initial_capital": float(request.initial_capital),
                    "universe_mode": p.get("universe_mode"),
                    "is_crypto": is_crypto_backtest,
                }
            )
            for _early_line in stage_logs:
                log_backtest_run_info("STAGE | %s", _early_line)
            _orig_stage_append = stage_logs.append

            def _stage_append_with_log(line: str) -> None:
                _orig_stage_append(line)
                log_backtest_run_info("STAGE | %s", line)

            stage_logs.append = _stage_append_with_log  # type: ignore[method-assign]
        except Exception as log_open_ex:
            logger.warning("backtest file log open failed run_id=%s: %s", run_id, log_open_ex)

        try:
            stage_logs.append("init: resumed deferred run" if deferred_run_id is not None else "init: created run")
            db.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS backtest_decisions (
                        id BIGSERIAL PRIMARY KEY,
                        run_id BIGINT NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
                        trade_date DATE NOT NULL,
                        ticker VARCHAR(20) NOT NULL,
                        source VARCHAR(20) NOT NULL DEFAULT 'PIPELINE',
                        result VARCHAR(20) NOT NULL,
                        reason TEXT NULL,
                        payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            db.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_backtest_decisions_run_day
                    ON backtest_decisions(run_id, trade_date)
                    """
                )
            )
            db.commit()
            try:
                bt_run_id = int(
                    db.execute(
                        text(
                            """
                            INSERT INTO backtest_runs
                            (name, description, robot_config_id, robot_config_snapshot, date_from, date_to, initial_capital,
                             commission_percent, slippage_percent, lot_fixed_fee, execution_model, status, progress_percent,
                             started_at, created_by)
                            VALUES
                            (:name, :description, :robot_config_id, CAST(:robot_config_snapshot AS jsonb), :date_from, :date_to, :initial_capital,
                             :commission_percent, :slippage_percent, :lot_fixed_fee, :execution_model, 'RUNNING', 0,
                             :started_at, :created_by)
                            RETURNING id
                            """
                        ),
                        {
                            "name": (f"robot-{robot_pk}-history-backtest" if robot_pk is not None else f"standalone-user-{user_id}-history-backtest"),
                            "description": "Auto-created from /api/robots/history-backtest",
                            "robot_config_id": int(robot_pk or 0),
                            "robot_config_snapshot": json.dumps(config, ensure_ascii=False),
                            "date_from": self._dt_date_utc(requested_from_utc),
                            "date_to": self._dt_date_utc(requested_to_utc),
                            "initial_capital": request.initial_capital,
                            "commission_percent": float((config.get("costs") or {}).get("broker_commission_rate") or 0.0005) * 100.0,
                            "slippage_percent": slippage_pct,
                            "lot_fixed_fee": 0.0,
                            "execution_model": execution_model,
                            "started_at": datetime.now(timezone.utc),
                            "created_by": str(user_id),
                        }
                    ).scalar()
                    or 0
                )
                db.commit()
            except Exception:
                db.rollback()
                bt_run_id = None
            trade_dates = self._iter_calendar_dates(requested_from_utc, requested_to_utc)
            td_total = len(trade_dates)
            skip_crypto_prefetch = bool(getattr(request, "skip_crypto_prefetch", False))
            screening_symbols_snapshot = getattr(request, "crypto_screening_symbols", None) or []
            if screening_symbols_snapshot and is_crypto_backtest:
                allowed_tickers_whitelist = {
                    str(s).strip().upper()
                    for s in screening_symbols_snapshot
                    if str(s).strip()
                }
            crypto_mode_pf = (
                normalize_crypto_universe_mode(config) if is_crypto_backtest else None
            )
            prefetch_phase = (
                "prefetching_crypto_market"
                if is_crypto_backtest and crypto_mode_pf != UNIVERSE_MODE_FIXED
                else "prefetching_market_snapshots"
            )
            try:
                db.execute(
                    text(
                        f"""
                        UPDATE backtest_runs
                        SET trade_dates_total = :td,
                            trade_dates_remaining = :td,
                            run_phase = :phase
                        WHERE id = :rid
                        """
                    ),
                    {"td": td_total, "rid": run_id, "phase": prefetch_phase}
                )
                db.commit()
            except Exception:
                db.rollback()
            self._flush_backtest_progress(
                progress_bind,
                run_id,
                prefetch_phase,
                phase_units_done=0,
                phase_units_total=td_total,
                trade_dates_total=td_total,
                trade_dates_remaining=td_total,
                started_at=run_started_at
            )
            stage_logs.append(
                f"history: processing {len(trade_dates)} calendar dates in range "
                f"{requested_from_utc.date()}–{requested_to_utc.date()}"
            )
            prefetch_missing: List[str] = []
            pipeline_user_cancelled = False
            if is_crypto_backtest:
                if crypto_mode_pf != UNIVERSE_MODE_FIXED:
                    if not skip_crypto_prefetch:
                        if _is_backtest_run_cancelled(run_id):
                            stage_logs.append("crypto: screening prefetch skipped (cancel requested)")
                            pipeline_user_cancelled = True
                        else:
                            from app.modules.robots.trading.backtest.crypto_screening_prefetch import (
                                schedule_crypto_screening_prefetch
                            )

                            stage_logs.append(
                                "crypto: deferring D1/funding prefetch to background job "
                                "(scoring starts after prefetch completes)"
                            )
                            await schedule_crypto_screening_prefetch(
                                db,
                                run_id=run_id,
                                user_id=user_id,
                                body=request.model_dump(mode="json"),
                                trade_dates=trade_dates,
                                config=config,
                                allowed_tickers_whitelist=allowed_tickers_whitelist,
                                progress_bind=progress_bind,
                                run_started_at=run_started_at
                            )
                            try:
                                log_backtest_run_info(
                                    "PREFETCH | delegated to background job crypto_screening_prefetch"
                                )
                            except Exception:
                                pass
                            return {"__prefetch_scheduled__": True}
                    else:
                        stage_logs.append(
                            "crypto: screening prefetch completed (background job) — starting scoring"
                        )
                        if allowed_tickers_whitelist:
                            stage_logs.append(
                                f"crypto: screening pool frozen at prefetch ({len(allowed_tickers_whitelist)} symbols)"
                            )
                else:
                    stage_logs.append("crypto: fixed universe — screening prefetch skipped")
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    prefetch_phase,
                    phase_units_done=td_total,
                    phase_units_total=td_total,
                    trade_dates_total=td_total,
                    trade_dates_remaining=0,
                    started_at=run_started_at
                )
            for d in trade_dates:
                if is_crypto_backtest:
                    break
                if _is_backtest_run_cancelled(run_id):
                    stage_logs.append(f"cancel: user requested stop during prefetch at day={d.isoformat()}")
                    rem_pf = max(0, len(trade_dates) - trade_dates.index(d) - 1)
                    _mark_backtest_run_cancelled_in_db(db, run_id, trade_date=d, trade_dates_remaining=rem_pf)
                    pipeline_user_cancelled = True
                    break
                try:
                    sid_pf = await self._ensure_daily_snapshot_history(
                        db, day=d, board=board, user_id=user_id, run_id=run_id
                    )
                    if not sid_pf:
                        prefetch_missing.append(d.isoformat())
                except Exception as ex:
                    logger.warning("history snapshot prefetch failed day=%s err=%s", d.isoformat(), ex)
                    prefetch_missing.append(d.isoformat())
                rem_pf = max(0, len(trade_dates) - trade_dates.index(d) - 1)
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    "prefetching_market_snapshots",
                    phase_units_done=max(0, td_total - rem_pf),
                    phase_units_total=td_total,
                    trade_dates_total=td_total,
                    trade_dates_remaining=rem_pf,
                    current_trade_date=d,
                    started_at=run_started_at
                )
            stage_logs.append(
                f"history: market_snapshot_history prefetch done; days_missing_snapshot={len(prefetch_missing)}"
            )
            if prefetch_missing:
                stage_logs.append(f"history: prefetch missing_days={','.join(prefetch_missing[:40])}")
            if not pipeline_user_cancelled:
                try:
                    db.execute(
                        text(
                            f"""
                            UPDATE backtest_runs
                            SET run_phase = 'scoring'
                            WHERE id = :rid AND COALESCE(cancel_requested, false) = false
                            """
                        ),
                        {"rid": run_id}
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                scoring_units_total = td_total * _SCORING_PROGRESS_SUBSTEPS
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    "scoring",
                    phase_units_done=0,
                    phase_units_total=scoring_units_total,
                    trade_dates_total=td_total,
                    trade_dates_remaining=td_total,
                    started_at=run_started_at
                )
            from app.modules.robots.trading.pipeline.universe_scoring import (
                run_history_universe_scoring,
                SCORING_PROGRESS_SUBSTEPS
            )

            allowed_figis_by_date: Dict[str, List[str]] = {}
            decisions_rows: List[Dict[str, Any]] = []
            day_stats: Dict[str, Dict[str, int]] = {}
            processed_days = 0
            skipped_fetch_days = 0
            skipped_empty_days = 0
            last_history_error: Optional[str] = None
            missing_history_days: List[str] = []
            scoring_units_total = td_total * SCORING_PROGRESS_SUBSTEPS
            selected_tickers: List[str] = []

            if is_crypto_backtest:
                crypto_mode = normalize_crypto_universe_mode(config)
                if crypto_mode == UNIVERSE_MODE_FIXED:
                    symbols = resolve_crypto_symbols(config)
                    if not symbols and allowed_tickers_whitelist:
                        symbols = [
                            str(s).strip().upper()
                            for s in allowed_tickers_whitelist
                            if str(s).strip()
                        ]
                    if not symbols:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Для crypto backtest укажите allowed_symbols в config"
                        )
                    selected_tickers = sorted(set(symbols))
                    allowed_figis_by_date = {d.isoformat(): list(selected_tickers) for d in trade_dates}
                    stage_logs.append(
                        f"crypto: fixed universe {len(selected_tickers)} symbols (24/7)"
                    )
                    self._flush_backtest_progress(
                        progress_bind,
                        run_id,
                        "scoring",
                        phase_units_done=scoring_units_total,
                        phase_units_total=scoring_units_total,
                        trade_dates_total=td_total,
                        trade_dates_remaining=0,
                        started_at=run_started_at
                    )
                else:

                    def _flush_crypto_scoring_progress(
                        phase_units_done: int,
                        *,
                        current_trade_date: date,
                        trade_dates_remaining: int
                    ) -> None:
                        self._flush_backtest_progress(
                            progress_bind,
                            run_id,
                            "scoring",
                            phase_units_done=phase_units_done,
                            phase_units_total=scoring_units_total,
                            trade_dates_total=td_total,
                            trade_dates_remaining=trade_dates_remaining,
                            current_trade_date=current_trade_date,
                            started_at=run_started_at
                        )

                    from app.modules.robots.trading.pipeline.crypto_universe_scoring import (
                        run_history_crypto_universe_scoring
                    )

                    crypto_scoring = await run_history_crypto_universe_scoring(
                        db=db,
                        trade_dates=trade_dates,
                        config=config,
                        user_id=user_id,
                        robot_id=robot_pk,
                        run_id=run_id,
                        allowed_tickers_whitelist=allowed_tickers_whitelist,
                        bybit_token_id=bybit_token_id,
                        is_cancelled=lambda: _is_backtest_run_cancelled(run_id),
                        flush_progress=_flush_crypto_scoring_progress
                    )
                    allowed_figis_by_date = crypto_scoring.allowed_figis_by_date
                    decisions_rows = crypto_scoring.decisions_rows
                    processed_days = crypto_scoring.processed_days
                    selected_tickers = list(crypto_scoring.selected_tickers)
                    if crypto_scoring.cancelled:
                        pipeline_user_cancelled = True
                    stage_logs.append(
                        f"crypto: auto universe scanned={crypto_scoring.scanned_tickers} "
                        f"selected={len(selected_tickers)} days={processed_days}"
                    )
            else:
                def _flush_scoring_progress(
                    phase_units_done: int,
                    *,
                    current_trade_date: date,
                    trade_dates_remaining: int
                ) -> None:
                    self._flush_backtest_progress(
                        progress_bind,
                        run_id,
                        "scoring",
                        phase_units_done=phase_units_done,
                        phase_units_total=scoring_units_total,
                        trade_dates_total=td_total,
                        trade_dates_remaining=trade_dates_remaining,
                        current_trade_date=current_trade_date,
                        started_at=run_started_at
                    )

                scoring_result = await run_history_universe_scoring(
                    db=db,
                    robot_service=self,
                    trade_dates=trade_dates,
                    board=board,
                    config=config,
                    pipeline_filters=pipeline_filters,
                    fast_pipeline_filters=fast_pipeline_filters,
                    pipeline_mode=pipeline_mode,
                    allowed_tickers_whitelist=allowed_tickers_whitelist,
                    div_policy=div_policy,
                    user_id=user_id,
                    run_id=run_id,
                    ensure_snapshot=self._ensure_daily_snapshot_history,
                    is_cancelled=lambda: _is_backtest_run_cancelled(run_id),
                    flush_progress=_flush_scoring_progress
                )
                allowed_figis_by_date = scoring_result.allowed_figis_by_date
                decisions_rows = scoring_result.decisions_rows
                day_stats = scoring_result.day_stats
                processed_days = scoring_result.processed_days
                skipped_fetch_days = scoring_result.skipped_fetch_days
                skipped_empty_days = scoring_result.skipped_empty_days
                missing_history_days = scoring_result.missing_history_days
                last_history_error = scoring_result.last_history_error
                selected_tickers = list(scoring_result.selected_tickers)
                if scoring_result.cancelled:
                    pipeline_user_cancelled = True
            if bt_run_id and day_stats:
                try:
                    progress = round((len(day_stats) / max(1, len(trade_dates))) * 100.0, 2)
                    db.execute(
                        text(
                            """
                            UPDATE backtest_runs
                            SET progress_percent=:progress_percent
                            WHERE id=:id
                            """
                        ),
                        {"id": bt_run_id, "progress_percent": progress}
                    )
                    db.commit()
                except Exception:
                    db.rollback()
            if not pipeline_user_cancelled:
                stage_logs.append(
                    f"history: summary processed={processed_days}, skipped_fetch={skipped_fetch_days}, skipped_empty={skipped_empty_days}"
                )
                if missing_history_days:
                    stage_logs.append(f"history: missing_days={','.join(missing_history_days)}")
    
                figis = sorted(set(selected_tickers))
                if not figis:
                    dbg = f"processed={processed_days}, skipped_fetch={skipped_fetch_days}, skipped_empty={skipped_empty_days}, trade_dates={len(trade_dates)}"
                    if last_history_error:
                        dbg = f"{dbg}, last_error={last_history_error}"
                    if day_stats:
                        day_parts = []
                        for day, st in sorted(day_stats.items(), key=lambda x: x[0]):
                            day_parts.append(
                                f"{day}:rows={int(st.get('rows_total', 0))},fast={int(st.get('fast_passed', 0))},final={int(st.get('final_passed', 0))}"
                            )
                        dbg = f"{dbg}, day_stats=[{' | '.join(day_parts)}]"
                    reject_reasons: Dict[str, int] = {}
                    for dr in decisions_rows:
                        if str(dr.get("result") or "").upper() != "REJECT":
                            continue
                        rs = str(dr.get("reason") or "").strip() or "unknown"
                        reject_reasons[rs] = int(reject_reasons.get(rs, 0)) + 1
                    if reject_reasons:
                        top = sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                        dbg = f"{dbg}, top_rejects={'; '.join([f'{k} x{v}' for k, v in top])}"
                    try:
                        from app.modules.robots.trading.backtest.universe_reject_report import (
                            emit_universe_reject_report
                        )

                        emit_universe_reject_report(
                            run_id,
                            decisions_rows=decisions_rows,
                            config=config,
                            day_stats=day_stats or None,
                            is_crypto=is_crypto_backtest
                        )
                    except Exception as report_exc:
                        logger.warning(
                            "universe reject report failed run_id=%s: %s",
                            run_id,
                            report_exc
                        )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Нет бумаг для бэктеста за выбранный период ({dbg})"
                    )
                stage_logs.append(f"pipeline: selected {len(figis)} tickers")
                from_day = self._dt_date_utc(requested_from_utc)
                to_day = self._dt_date_utc(requested_to_utc)
                resolved_moex_iv = p.get("resolved_moex_interval")
                min_required_candles = int(p.get("min_required_candles") or 1)
                moex_min_required = int(p.get("moex_min_required_candles") or 1)

                try:
                    db.execute(
                        text(
                            f"UPDATE backtest_runs SET run_phase='prefetching_candles' WHERE id=:rid"
                        ),
                        {"rid": run_id}
                    )
                    db.commit()
                except Exception:
                    db.rollback()

                from app.modules.robots.trading.data import get_market_data_facade

                market_data = get_market_data_facade()
                candles_tickers_total = len(figis)
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    "prefetching_candles",
                    phase_units_done=0,
                    phase_units_total=max(1, candles_tickers_total),
                    trade_dates_total=td_total,
                    trade_dates_remaining=0,
                    started_at=run_started_at
                )
                if is_crypto_backtest:
                    from app.modules.robots.trading.runtime import get_trading_orchestrator
                    from app.modules.robots.trading.backtest.backtest_narrative_log import (
                        backtest_narrative,
                        format_candle_prefetch_result,
                        format_funding_prefetch_result,
                        format_symbol_list,
                        narrative_result,
                        narrative_section,
                        narrative_step,
                        narrative_sub
                    )

                    bybit_cfg = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
                    instrument_category = str(bybit_cfg.get("instrument_category") or "linear").strip().lower()
                    orch = get_trading_orchestrator()
                    narrative_section("Подготовка свечей для симуляции сделок", run_id=run_id)
                    with backtest_narrative(run_id):
                        narrative_step(
                            f"Догрузка свечей исполнения ({resolved_exec_iv.cache_label}) в candles_cache"
                        )
                        narrative_sub(
                            f"Символов после скоринга: {len(figis)}; "
                            f"период {from_day.isoformat()}..{to_day.isoformat()}"
                        )
                        prefetch_stats, _prefetch_candles_skip = await orch.prefetch_crypto_candles_for_replay(
                            db,
                            symbols=figis,
                            resolved=resolved_exec_iv,
                            from_date=from_day,
                            till_date=to_day,
                            instrument_category=instrument_category,
                            user_id=user_id,
                            run_id=run_id,
                            is_cancelled=lambda: _is_backtest_run_cancelled(run_id),
                            progress_callback=lambda done, total: self._flush_backtest_progress(
                                progress_bind,
                                run_id,
                                "prefetching_candles",
                                phase_units_done=done,
                                phase_units_total=max(1, total),
                                trade_dates_total=td_total,
                                started_at=run_started_at
                            ),
                            load_cached_candles=False
                        )
                        narrative_result(format_candle_prefetch_result(prefetch_stats))
                        narrative_sub(
                            f"Кэш ByBit подготовлен: {prefetch_stats.processed_tickers}/"
                            f"{prefetch_stats.total_tickers} символов "
                            f"(bulk load в память — на фазе loading_candles)"
                        )
                        costs_cfg = config.get("costs") if isinstance(config.get("costs"), dict) else {}
                        funding_enabled = bool(costs_cfg.get("funding_rate_enabled", True))
                        if funding_enabled and instrument_category != "spot":
                            narrative_step("Проверка funding rate для симуляции")
                            funding_stats = await orch.prefetch_crypto_funding_for_replay(
                                db,
                                symbols=figis,
                                from_date=from_day,
                                till_date=to_day,
                                instrument_category=instrument_category,
                                user_id=user_id,
                                run_id=run_id,
                                is_cancelled=lambda: _is_backtest_run_cancelled(run_id)
                            )
                            narrative_result(format_funding_prefetch_result(funding_stats))
                    stage_logs.append(
                        f"candles: bybit prefetch interval={resolved_exec_iv.cache_label} "
                        f"{prefetch_stats.summary()}"
                    )
                    if prefetch_stats.cancelled:
                        pipeline_user_cancelled = True

                    costs_cfg = config.get("costs") if isinstance(config.get("costs"), dict) else {}
                    funding_enabled = bool(costs_cfg.get("funding_rate_enabled", True))
                    if funding_enabled and instrument_category != "spot":
                        stage_logs.append(f"funding: bybit {funding_stats.summary()}")
                        if funding_stats.cancelled:
                            pipeline_user_cancelled = True
                elif resolved_moex_iv is not None:
                    prefetch_stats = await market_data.ensure_candles(
                        db,
                        board=board,
                        tickers=figis,
                        resolved=resolved_moex_iv,
                        from_date=from_day,
                        till_date=to_day,
                        user_id=user_id,
                        run_id=run_id,
                        is_cancelled=lambda: _is_backtest_run_cancelled(run_id),
                        progress_callback=lambda done, total: self._flush_backtest_progress(
                            progress_bind,
                            run_id,
                            "prefetching_candles",
                            phase_units_done=done,
                            phase_units_total=max(1, total),
                            trade_dates_total=td_total,
                            started_at=run_started_at
                        )
                    )
                    stage_logs.append(
                        f"candles: MOEX prefetch interval={resolved_moex_iv.cache_label} "
                        f"{prefetch_stats.summary()}"
                    )
                    if prefetch_stats.cancelled:
                        pipeline_user_cancelled = True

                if pipeline_user_cancelled:
                    raise asyncio.CancelledError()

                try:
                    db.execute(
                        text(
                            f"UPDATE backtest_runs SET run_phase='loading_candles' WHERE id=:rid"
                        ),
                        {"rid": run_id}
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                candles_tickers_total = len(figis)
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    "loading_candles",
                    phase_units_done=0,
                    phase_units_total=max(1, candles_tickers_total),
                    trade_dates_total=td_total,
                    trade_dates_remaining=0,
                    started_at=run_started_at
                )

                candles_by_figi: Dict[str, List[Dict[str, Any]]] = {}
                if is_crypto_backtest:
                    from_dt = datetime.combine(from_day, time.min, tzinfo=timezone.utc)
                    to_dt_exclusive = datetime.combine(to_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
                    from app.modules.robots.trading.runtime import get_trading_orchestrator
                    from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

                    candles_by_figi = get_trading_orchestrator().load_candles_by_symbol_from_cache(
                        db,
                        symbols=figis,
                        interval_code=interval_code,
                        interval_code_num=interval_code_num,
                        from_dt=from_dt,
                        to_dt_exclusive=to_dt_exclusive,
                        market="bybit",
                        batch_size=_CANDLE_LOAD_BATCH_SIZE
                    )
                    touch_backtest_progress_runtime(run_id)
                    self._flush_backtest_progress(
                        progress_bind,
                        run_id,
                        "loading_candles",
                        phase_units_done=len(candles_by_figi),
                        phase_units_total=max(1, candles_tickers_total),
                        trade_dates_total=td_total,
                        started_at=run_started_at
                    )
                    stage_logs.append(
                        f"candles: bybit bulk cache load symbols={len(candles_by_figi)}/{len(figis)} "
                        f"interval={interval_code}"
                    )
                moex_gap_attempts = 0
                moex_gap_success = 0
                if not is_crypto_backtest:
                    from_dt = datetime.combine(from_day, time.min, tzinfo=timezone.utc)
                    to_dt_exclusive = datetime.combine(to_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
                    to_ts_shared = to_dt_exclusive - timedelta(microseconds=1)

                    from app.modules.market_data_v1 import repository as shared_market_repository
                    from app.modules.market_data_v1.intervals import strategy_interval_code_to_shared_canonical

                    from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

                    shared_canonical = p.get("shared_canonical") or strategy_interval_code_to_shared_canonical(interval_code_num)
                    shared_rows_total = 0
                    if shared_canonical and figis:
                        for batch_start in range(0, len(figis), _CANDLE_LOAD_BATCH_SIZE):
                            if _is_backtest_run_cancelled(run_id):
                                pipeline_user_cancelled = True
                                break
                            batch = figis[batch_start: batch_start + _CANDLE_LOAD_BATCH_SIZE]
                            try:
                                shared_rows = shared_market_repository.list_candles(
                                    db,
                                    tickers=batch,
                                    board=board,
                                    interval=shared_canonical,
                                    from_ts=from_dt,
                                    to_ts=to_ts_shared
                                )
                            except Exception as ex:
                                shared_rows = []
                                stage_logs.append(
                                    f"candles: shared_market_candles batch@{batch_start} failed ({ex})"
                                )
                            shared_rows_total += len(shared_rows or [])
                            by_ticker: Dict[str, List[Dict[str, Any]]] = {}
                            for r in shared_rows or []:
                                tk = str((r or {}).get("ticker") or "").strip().upper()
                                if not tk:
                                    continue
                                by_ticker.setdefault(tk, []).append(r)
                            for tk, rows in by_ticker.items():
                                rows.sort(key=lambda x: x.get("bucket_start") or datetime.min.replace(tzinfo=timezone.utc))
                                one: List[Dict[str, Any]] = []
                                for c in rows:
                                    close = float(c.get("close") or 0)
                                    units = int(close)
                                    nano = int(round((close - units) * 1_000_000_000))
                                    bt = c.get("bucket_start")
                                    time_iso = bt.isoformat() if hasattr(bt, "isoformat") else (str(bt) if bt else "")
                                    one.append({
                                        "time": time_iso,
                                        "open": {"units": int(float(c.get("open") or 0)), "nano": 0},
                                        "high": {"units": int(float(c.get("high") or 0)), "nano": 0},
                                        "low": {"units": int(float(c.get("low") or 0)), "nano": 0},
                                        "close": {"units": units, "nano": nano},
                                        "volume": int(c.get("volume") or 0),
                                    })
                                if one:
                                    candles_by_figi[tk] = one
                            touch_backtest_progress_runtime(run_id)
                            self._flush_backtest_progress(
                                progress_bind,
                                run_id,
                                "loading_candles",
                                phase_units_done=min(candles_tickers_total, batch_start + len(batch)),
                                phase_units_total=max(1, candles_tickers_total),
                                trade_dates_total=td_total,
                                started_at=run_started_at
                            )
                        stage_logs.append(
                            f"candles: shared_market_candles interval={shared_canonical} "
                            f"rows={shared_rows_total} tickers_with_series={len(candles_by_figi)} "
                            f"(db-only, batches={max(1, (len(figis) + _CANDLE_LOAD_BATCH_SIZE - 1) // _CANDLE_LOAD_BATCH_SIZE)})"
                        )
                    elif not shared_canonical:
                        stage_logs.append(
                            f"candles: no shared_market_candles mapping for interval_code={interval_code_num} "
                            f"(legacy candles_cache path)"
                        )

                    min_required_candles = int(p.get("min_required_candles") or 1)
                    need_legacy = [
                        tk for tk in figis
                        if tk not in candles_by_figi or len(candles_by_figi.get(tk) or []) < min_required_candles
                    ]
                    if need_legacy:
                        moex_hint = (
                            f"MOEX gap-fill при пробелах (moex={moex_interval_code})"
                            if execution_moex_gap_ok
                            else "MOEX gap-fill пропущен — execution_interval не поддерживается ISS; нужен T-Invest cache"
                        )
                        stage_logs.append(
                            f"candles: candles_cache read for {len(need_legacy)} ticker(s), "
                            f"execution_interval={interval_code}; {moex_hint}"
                        )

                    candles_loaded = len(candles_by_figi)
                    shared_satisfied = len(figis) - len(need_legacy)
                    moex_gap_attempts = 0
                    moex_gap_success = 0

                    legacy_rows_bulk: Dict[str, List[Any]] = {}
                    if need_legacy:
                        legacy_rows_bulk = market_data.read_candles_cache_rows_bulk(
                            db,
                            market="moex",
                            instrument_ids=need_legacy,
                            interval_code=interval_code,
                            interval_code_num=interval_code_num,
                            from_dt=from_dt,
                            to_dt_exclusive=to_dt_exclusive,
                            batch_size=_CANDLE_LOAD_BATCH_SIZE
                        )

                    gap_refill_figis: List[str] = []
                    for legacy_idx, figi in enumerate(need_legacy):
                        if _is_backtest_run_cancelled(run_id):
                            pipeline_user_cancelled = True
                            break
                        c_rows = list(legacy_rows_bulk.get(str(figi).strip().upper()) or [])
                        if len(c_rows) < min_required_candles and execution_moex_gap_ok:
                            moex_gap_attempts += 1
                            gap = await market_data.gap_fill_ticker(
                                db,
                                board=board,
                                ticker=figi,
                                interval_code=interval_code,
                                interval_code_num=interval_code_num,
                                from_day=from_day,
                                to_day=to_day,
                                user_id=user_id
                            )
                            if gap.success:
                                moex_gap_success += 1
                                gap_refill_figis.append(figi)
                            elif moex_gap_attempts <= 3:
                                stage_logs.append(f"candles: moex gap-fill failed ticker={figi}")
                        one: List[Dict[str, Any]] = []
                        for c in c_rows:
                            close = float(c["close"] or 0)
                            units = int(close)
                            nano = int(round((close - units) * 1_000_000_000))
                            one.append({
                                "time": c["candle_time"].isoformat() if c["candle_time"] else "",
                                "open": {"units": int(float(c["open"] or 0)), "nano": 0},
                                "high": {"units": int(float(c["high"] or 0)), "nano": 0},
                                "low": {"units": int(float(c["low"] or 0)), "nano": 0},
                                "close": {"units": units, "nano": nano},
                                "volume": int(c["volume"] or 0),
                            })
                        if one:
                            candles_by_figi[figi] = one
                        candles_loaded = len(candles_by_figi)
                        if legacy_idx % 4 == 0 or legacy_idx + 1 == len(need_legacy):
                            touch_backtest_progress_runtime(run_id)
                            self._flush_backtest_progress(
                                progress_bind,
                                run_id,
                                "loading_candles",
                                phase_units_done=min(
                                    candles_tickers_total,
                                    shared_satisfied + legacy_idx + 1
                                ),
                                phase_units_total=max(1, candles_tickers_total),
                                trade_dates_total=td_total,
                                started_at=run_started_at
                            )

                    if gap_refill_figis:
                        refill_bulk = market_data.read_candles_cache_rows_bulk(
                            db,
                            market="moex",
                            instrument_ids=gap_refill_figis,
                            interval_code=interval_code,
                            interval_code_num=interval_code_num,
                            from_dt=from_dt,
                            to_dt_exclusive=to_dt_exclusive,
                            batch_size=_CANDLE_LOAD_BATCH_SIZE
                        )
                        for figi in gap_refill_figis:
                            c_rows = list(refill_bulk.get(str(figi).strip().upper()) or [])
                            one: List[Dict[str, Any]] = []
                            for c in c_rows:
                                close = float(c["close"] or 0)
                                units = int(close)
                                nano = int(round((close - units) * 1_000_000_000))
                                one.append({
                                    "time": c["candle_time"].isoformat() if c["candle_time"] else "",
                                    "open": {"units": int(float(c["open"] or 0)), "nano": 0},
                                    "high": {"units": int(float(c["high"] or 0)), "nano": 0},
                                    "low": {"units": int(float(c["low"] or 0)), "nano": 0},
                                    "close": {"units": units, "nano": nano},
                                    "volume": int(c["volume"] or 0),
                                })
                            if one:
                                candles_by_figi[figi] = one
                        candles_loaded = len(candles_by_figi)

                    if moex_gap_attempts:
                        moex_lbl = (p.get("moex_interval_code") or interval_code)
                        stage_logs.append(
                            f"candles: moex gap-fill attempts={moex_gap_attempts} "
                            f"success={moex_gap_success} moex_interval={moex_lbl} sim_interval={interval_code}"
                        )


                missing_candle_tickers = [tk for tk in figis if tk not in candles_by_figi or len(candles_by_figi.get(tk) or []) < min_required_candles]
                if missing_candle_tickers:
                    stage_logs.append(
                        f"candles: still missing after gap-fill {len(missing_candle_tickers)}/{len(figis)} "
                        f"(interval={interval_code})"
                    )
    
                if not candles_by_figi:
                    if is_crypto_backtest:
                        detail = (
                            f"Нет свечей для crypto backtest: interval={interval_code}, "
                            f"загружено 0 из {len(figis)} symbols за {from_day}..{to_day}. "
                            "Проверьте ByBit kline prefetch и allowed_symbols."
                        )
                    else:
                        detail = (
                            f"Нет свечей для симуляции: execution_interval={interval_code}, "
                            f"moex_prefetch={p.get('moex_interval_code') or 'I10'}, "
                            f"загружено 0 из {len(figis)} тикеров за {from_day}..{to_day}. "
                            f"Для M5 нужны свечи T-Invest (candles_cache/брокер), MOEX ISS 5m не отдаёт. "
                            f"MOEX gap-fill: {moex_gap_success}/{moex_gap_attempts}."
                        )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=detail
                    )
                stage_logs.append(f"candles: loaded for {len(candles_by_figi)} tickers")
    
                strategy_params["figis"] = list(candles_by_figi.keys())

                async def _backtest_cancel_requested() -> bool:
                    return is_history_backtest_cancelled(run_id)

                def _backtest_cancel_sync() -> bool:
                    return is_history_backtest_cancelled(run_id)

                _last_sim_progress_mono = 0.0

                def _on_sim_progress(done: int, total: int) -> None:
                    nonlocal _last_sim_progress_mono
                    now_m = time_mod.monotonic()
                    if done < total and done % 48 != 0 and (now_m - _last_sim_progress_mono) < 0.8:
                        return
                    _last_sim_progress_mono = now_m
                    RobotService._flush_backtest_progress(
                        progress_bind,
                        run_id,
                        "simulating",
                        phase_units_done=int(done),
                        phase_units_total=max(1, int(total)),
                        trade_dates_total=td_total,
                        started_at=run_started_at
                    )

                try:
                    db.execute(
                        text(
                            f"UPDATE backtest_runs SET run_phase='simulating' WHERE id=:rid"
                        ),
                        {"rid": run_id}
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                self._flush_backtest_progress(
                    progress_bind,
                    run_id,
                    "simulating",
                    phase_units_done=0,
                    phase_units_total=1,
                    trade_dates_total=td_total,
                    started_at=run_started_at
                )
                try:
                    from app.core.logging_config import get_rest_logger

                    get_rest_logger().info(
                        "history-backtest run_id=%s phase=simulating tickers=%s",
                        run_id,
                        len(candles_by_figi)
                    )
                except Exception:
                    pass

                from app.modules.robots.trading.runtime import get_trading_orchestrator

                _sim_robot_id = int(robot_pk or (robot.get("id") if robot else 0) or run_id)
                _token_row = (robot or {}).get("token") or {}
                _token_id = int(_token_row.get("id") or 0)

                stage_logs.append(
                    f"simulation: TradingOrchestrator (BACKTEST) strategy={strategy_name} robot_id={_sim_robot_id}"
                )
                res = await get_trading_orchestrator().run_backtest_replay(
                    db=db,
                    schema=settings.DB_SCHEMA,
                    robot_id=_sim_robot_id,
                    user_id=user_id,
                    token_id=_token_id,
                    token="",
                    config=config,
                    candles_by_figi=candles_by_figi,
                    allowed_figis_by_date=allowed_figis_by_date,
                    initial_capital=float(request.initial_capital),
                    cancel_check=_backtest_cancel_requested,
                    cancel_check_sync=_backtest_cancel_sync,
                    progress_callback_sync=_on_sim_progress
                )
                if not getattr(res, "cancelled", False) and not _is_backtest_run_cancelled(run_id):
                    stage_logs.append("simulation: completed")
                else:
                    stage_logs.append("simulation: stopped (cancel requested)")
            else:
                from app.modules.robots.trading.backtest.types import BacktestResult

                res = BacktestResult(
                    initial_capital=float(request.initial_capital),
                    final_equity=float(request.initial_capital),
                    total_return_percent=0.0,
                    max_drawdown_percent=None
                )
                stage_logs.append("simulation: skipped (pipeline cancelled)")
        except ValueError as e:
            backtest_log_status = "FAILED"
            backtest_log_error = str(e)
            log_backtest_run_exception("backtest ValueError")
            _clear_backtest_run_tracking(run_id)
            try:
                close_backtest_run_log(
                    run_id,
                    status=backtest_log_status,
                    summary=backtest_log_summary,
                    error=backtest_log_error
                )
            except Exception:
                pass
            try:
                _mark_backtest_run_failed(db, run_id, str(e))
            except Exception:
                db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except HTTPException as hex:
            backtest_log_status = "FAILED"
            backtest_log_error = str(hex.detail)
            log_backtest_run_exception("backtest HTTPException: %s", hex.detail)
            _clear_backtest_run_tracking(run_id)
            try:
                close_backtest_run_log(
                    run_id,
                    status=backtest_log_status,
                    summary=backtest_log_summary,
                    error=backtest_log_error
                )
            except Exception:
                pass
            try:
                _mark_backtest_run_failed(db, run_id, str(hex.detail))
            except Exception:
                db.rollback()
            raise
        except Exception as e:
            backtest_log_status = "FAILED"
            backtest_log_error = str(e)
            log_backtest_run_exception("robot history backtest failed")
            try_dispose_pool_on_connectivity_error(e)
            _clear_backtest_run_tracking(run_id)
            try:
                close_backtest_run_log(
                    run_id,
                    status=backtest_log_status,
                    summary=backtest_log_summary,
                    error=backtest_log_error
                )
            except Exception:
                pass
            logger.exception("robot history backtest failed")
            try:
                _mark_backtest_run_failed(db, run_id, f"Ошибка загрузки данных или расчёта: {e}")
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ошибка загрузки данных или расчёта: {e}"
            )

        result = {
            "run_id": int(run_id),
            "strategy": strategy_name,
            "initial_capital": res.initial_capital,
            "final_equity": res.final_equity,
            "total_return_percent": res.total_return_percent,
            "max_drawdown_percent": res.max_drawdown_percent,
            "trades": res.trades,
            "signals": [
                {
                    "figi": s.get("figi"),
                    "signal_type": s.get("signal_type"),
                    "was_executed": int(bool(s.get("was_executed"))),
                    "bar_time": s.get("bar_time"),
                    "reason": s.get("reason"),
                }
                for s in (getattr(res, "signals", None) or [])
            ],
            "equity_curve": res.equity_curve,
            "stages": stage_logs,
            "history_stats": {
                "processed": processed_days,
                "skipped_fetch": skipped_fetch_days,
                "skipped_empty": skipped_empty_days,
                "total_trade_dates": len(trade_dates),
            },
            "fee_summary": dict(getattr(res, "fee_summary", None) or {}),
            "margin_summary": dict(getattr(res, "margin_summary", None) or {}),
        }
        # Daily summary for UI: candidates/signals/trades breakdown by day.
        try:
            daily_map: Dict[str, Dict[str, int]] = {}
            for d in trade_dates:
                key = d.isoformat()
                daily_map[key] = {
                    "candidates_accept": 0,
                    "candidates_reject": 0,
                    "signals_total": 0,
                    "signals_executed": 0,
                    "trades_total": 0,
                }
            for dr in decisions_rows:
                day = str(dr.get("trade_date") or "")
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                if str(dr.get("result") or "").upper() == "ACCEPT":
                    daily_map[day]["candidates_accept"] += 1
                else:
                    daily_map[day]["candidates_reject"] += 1
            for s in res.signals:
                bt = str(s.get("bar_time") or "")
                day = bt[:10] if len(bt) >= 10 else ""
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                daily_map[day]["signals_total"] += 1
                if int(bool(s.get("was_executed"))):
                    daily_map[day]["signals_executed"] += 1
            for t in res.trades:
                bt = str(t.get("bar_time") or "")
                day = bt[:10] if len(bt) >= 10 else ""
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                daily_map[day]["trades_total"] += 1
            result["daily_summary"] = [
                {"date": d, **vals}
                for d, vals in sorted(daily_map.items(), key=lambda x: x[0])
            ]
        except Exception:
            # Do not fail backtest response on analytics post-processing.
            result["daily_summary"] = []
        skip_heavy_persist = (
            pipeline_user_cancelled
            or is_history_backtest_cancelled(run_id)
            or bool(getattr(res, "cancelled", False))
        )
        from app.core.db_retry import run_db_with_retry
        from app.modules.robots.trading.backtest.persist_checkpoint import (
            build_persist_checkpoint_payload,
            delete_persist_checkpoint,
            write_persist_checkpoint
        )
        from app.modules.robots.trading.backtest.persist_phase import execute_backtest_persist_phase
        from sqlalchemy.exc import InterfaceError, OperationalError

        write_persist_checkpoint(
            run_id,
            run_started_at,
            build_persist_checkpoint_payload(
                run_id=run_id,
                run_started_at=run_started_at,
                robot_pk=robot_pk,
                bt_run_id=bt_run_id,
                slippage_pct=slippage_pct,
                is_crypto_backtest=is_crypto_backtest,
                requested_from_utc=requested_from_utc,
                requested_to_utc=requested_to_utc,
                skip_heavy_persist=skip_heavy_persist,
                pipeline_user_cancelled=pipeline_user_cancelled,
                td_total=td_total,
                config=config,
                res=res,
                decisions_rows=decisions_rows,
                result=result
            )
        )

        def _persist_phase() -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
            return execute_backtest_persist_phase(
                flush_progress=self._flush_backtest_progress,
                dt_date_utc=self._dt_date_utc,
                db=db,
                progress_bind=progress_bind,
                run_id=run_id,
                run_started_at=run_started_at,
                td_total=td_total,
                skip_heavy_persist=skip_heavy_persist,
                bt_run_id=bt_run_id,
                res=res,
                slippage_pct=slippage_pct,
                decisions_rows=decisions_rows,
                is_crypto_backtest=is_crypto_backtest,
                config=config,
                result=result,
                robot_pk=robot_pk,
                requested_from_utc=requested_from_utc,
                requested_to_utc=requested_to_utc,
                pipeline_user_cancelled=pipeline_user_cancelled
            )

        persist_checkpoint_kept = True
        try:
            backtest_log_status, backtest_log_summary, backtest_log_error = run_db_with_retry(
                db,
                _persist_phase,
                max_attempts=60,
                delay_sec=10.0,
                max_delay_sec=30.0
            )
            delete_persist_checkpoint(run_id, run_started_at)
            persist_checkpoint_kept = False
        except Exception as exc:
            db.rollback()
            is_conn = isinstance(exc, (OperationalError, InterfaceError))
            if is_conn:
                try_dispose_pool_on_connectivity_error(exc)
            log_backtest_run_exception("failed to persist robot backtest run")
            logger.exception("failed to persist robot backtest run")
            if is_conn and persist_checkpoint_kept:
                backtest_log_status = "PENDING_PERSIST"
                backtest_log_error = str(exc)[:500]
                backtest_log_summary = {
                    "total_return_percent": res.total_return_percent,
                    "max_drawdown_percent": res.max_drawdown_percent,
                    "trades_total": len(res.trades),
                    "final_equity": res.final_equity,
                }

                def _mark_persist_pending() -> None:
                    db.execute(
                        text(
                            f"""
                            UPDATE backtest_runs
                            SET run_phase = 'persist_pending',
                                error_message = :msg
                            WHERE id = :rid
                              AND status IN ('RUNNING', 'FETCHING')
                            """
                        ),
                        {"rid": run_id, "msg": "persist-waiting-db"}
                    )
                    db.commit()

                try:
                    run_db_with_retry(db, _mark_persist_pending, max_attempts=5, delay_sec=2.0)
                except Exception:
                    db.rollback()
            else:
                backtest_log_status = "FAILED"
                backtest_log_error = "persist-failed"

                def _mark_persist_failed() -> None:
                    db.execute(
                        text(f"""
                            UPDATE backtest_runs
                            SET status='FAILED',
                                finished_at=:finished_at,
                                error_message=:error_message
                            WHERE id=:run_id
                        """),
                        {
                            "run_id": run_id,
                            "finished_at": datetime.now(timezone.utc),
                            "error_message": "persist-failed",
                        }
                    )
                    db.commit()

                try:
                    run_db_with_retry(db, _mark_persist_failed, max_attempts=5, delay_sec=2.0)
                except Exception:
                    db.rollback()
        try:
            close_backtest_run_log(
                run_id,
                status=backtest_log_status,
                summary=backtest_log_summary,
                error=backtest_log_error,
                started_at=run_started_at
            )
        except Exception as close_ex:
            logger.warning("backtest file log close failed run_id=%s: %s", run_id, close_ex)
        _clear_backtest_run_tracking(run_id)
        return result

    async def get_live_snapshot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            *,
            mode: str = "full"
    ) -> Dict[str, Any]:
        """REST snapshot для Live-экрана.

        mode=ops  — сигналы/заявки/логи из БД (без брокера и reconcile).
        mode=full — + портфель брокера и reconcile заявок.
        """
        snap_mode = str(mode or "full").strip().lower()
        if snap_mode not in {"ops", "full"}:
            snap_mode = "full"
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Робот не является торговым")

        config = dict(robot.get("config") or {})
        strategy = str(config.get("strategy") or "grain_seed")
        token_meta = robot.get("token") or {}
        token_type_raw = token_meta.get("type")
        try:
            token_type = int(token_type_raw) if token_type_raw is not None else None
        except (TypeError, ValueError):
            token_type = None
        from app.modules.robots.trading.brokers.routing import (
            BrokerTokenMismatchError,
            enforce_broker_for_token
        )

        try:
            broker_type = enforce_broker_for_token(
                config,
                token_type=token_type,
                mutate=True,
                require_token=True
            )
        except BrokerTokenMismatchError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            ) from exc
        account_id = config.get("account_id")

        positions_q = f"""
            SELECT id, figi, side, quantity, COALESCE(entry_price, price) AS entry_price, status, created_at
            FROM robot_trades
            WHERE robot_id = :robot_id
              AND status IN ('open', 'partial')
            ORDER BY created_at DESC
            LIMIT 100
        """
        positions_rows = db.execute(text(positions_q), {"robot_id": robot_id}).fetchall()
        active_positions = [
            {
                "id": int(r[0]),
                "figi": str(r[1]),
                "side": str(r[2]),
                "quantity": float(r[3] or 0),
                "entry_price": float(r[4] or 0),
                "status": str(r[5]),
                "created_at": r[6],
            }
            for r in positions_rows
        ]

        signals_q = f"""
            SELECT id, figi, signal_type, signal_strength, price_at_signal, was_executed,
                   executed_trade_id, created_at
            FROM robot_signals
            WHERE robot_id = :robot_id
            ORDER BY created_at DESC
            LIMIT 100
        """
        signals_rows = db.execute(text(signals_q), {"robot_id": robot_id}).fetchall()
        recent_signals = [
            {
                "id": int(r[0]),
                "figi": str(r[1]),
                "signal_type": str(r[2]),
                "signal_strength": int(r[3] or 0),
                "price_at_signal": float(r[4] or 0),
                "was_executed": int(r[5] or 0),
                "executed_trade_id": int(r[6]) if r[6] is not None else None,
                "created_at": r[7],
            }
            for r in signals_rows
        ]

        portfolio_positions: List[Dict[str, Any]] = []
        portfolio_summary: Dict[str, Any] = {}
        portfolio_fetch_error: Optional[str] = None
        portfolio_source: Optional[str] = None
        broker_for_orders = None
        resolved_account_for_orders: Optional[str] = (
            str(account_id).strip() if account_id else None
        ) or None
        orders_synced_at = None

        if snap_mode == "ops":
            # Fast path: DB-only orders/signals; keep portfolio empty for client merge.
            recent_orders = _load_live_account_orders(
                db,
                user_id=int(user_id),
                broker_account_id=resolved_account_for_orders
            )
            open_orders, order_history = _split_db_orders(recent_orders)
        else:
            try:
                from app.modules.robots.trading.brokers import create_broker_facade
                from app.modules.tinvest.service import tinvest_service

                token_row = robot.get("token") or {}
                token_str: Optional[str] = None
                token_id = token_row.get("id")
                if token_id:
                    td = await token_service.get_token_by_id(db, int(token_id), user_id)
                    token_str = (td or {}).get("token")
                if not token_str:
                    portfolio_fetch_error = "no_broker_token"
                else:
                    token_extra = (td or {}).get("extra_data") if isinstance((td or {}).get("extra_data"), dict) else {}
                    broker = create_broker_facade(
                        broker_type,
                        token_str,
                        token_extra_data=token_extra,
                        robot_config=config
                    )
                    resolved_account_id = await _resolve_robot_account_id(broker, account_id)
                    if not resolved_account_id:
                        portfolio_fetch_error = "no_account_id"
                    else:
                        account_id = resolved_account_id
                        broker_for_orders = broker
                        resolved_account_for_orders = str(resolved_account_id)
                        if not str(config.get("account_id") or "").strip():
                            try:
                                _persist_robot_account_id(db, robot_id, user_id, resolved_account_id)
                                config = {**config, "account_id": resolved_account_id}
                            except Exception as persist_exc:
                                try:
                                    db.rollback()
                                except Exception:
                                    pass
                                logger.warning(
                                    "live snapshot account_id persist failed robot_id=%s: %s",
                                    robot_id,
                                    persist_exc
                                )

                        broker_exc: Optional[Exception] = None
                        is_bybit = broker_type.strip().lower() == "bybit"
                        fetch_modes = ("broker") if is_bybit else ("broker", "tinvest_service")
                        for fetch_mode in fetch_modes:
                            try:
                                if fetch_mode == "broker":
                                    pf = await broker.get_portfolio(str(account_id))
                                else:
                                    pdata = await tinvest_service.get_portfolio_data(
                                        token_str,
                                        account_id=str(account_id),
                                        db=db,
                                        token_id=int(token_id) if token_id is not None else None,
                                        user_id=int(user_id)
                                    )
                                    pf = dict((pdata or {}).get("portfolio") or {})
                                positions_raw = list(pf.get("positions") or [])
                                portfolio_positions = _normalize_portfolio_positions(
                                    positions_raw,
                                    type_names=_instrument_type_label_map(db)
                                )
                                portfolio_summary = {k: v for k, v in pf.items() if k != "positions"}
                                portfolio_source = fetch_mode
                                portfolio_fetch_error = None
                                if portfolio_positions or fetch_mode == "broker":
                                    break
                            except Exception as exc:
                                broker_exc = exc
                                if (
                                    is_bybit
                                    and token_id is not None
                                    and _is_bybit_auth_error(exc)
                                ):
                                    try:
                                        try:
                                            db.rollback()
                                        except Exception:
                                            pass
                                        _expire_token_and_disable_robots(
                                            db,
                                            token_id=int(token_id),
                                            user_id=int(user_id),
                                            error_message=str(exc)
                                        )
                                        logger.warning(
                                            "ByBit token expired/invalid -> deactivated token_id=%s and disabled robots for user_id=%s",
                                            token_id,
                                            user_id
                                        )
                                    except Exception as deact_exc:
                                        logger.error(
                                            "Failed to deactivate ByBit token token_id=%s user_id=%s: %s",
                                            token_id,
                                            user_id,
                                            deact_exc,
                                            exc_info=True
                                        )
                                logger.warning(
                                    "live snapshot portfolio fetch (%s) robot_id=%s: %s",
                                    fetch_mode,
                                    robot_id,
                                    exc
                                )

                        if not portfolio_positions and portfolio_source != "broker":
                            db_positions = _load_portfolio_positions_from_db(
                                db, user_id, str(account_id)
                            )
                            if db_positions:
                                portfolio_positions = db_positions
                                portfolio_source = "db_snapshot"
                                portfolio_fetch_error = None
                            elif broker_exc is not None:
                                portfolio_fetch_error = str(broker_exc)[:200] or "portfolio_fetch_failed"
            except Exception as exc:
                portfolio_fetch_error = str(exc)[:200] or "portfolio_fetch_failed"
                logger.warning(
                    "live snapshot portfolio fetch failed robot_id=%s: %s",
                    robot_id,
                    exc,
                    exc_info=True
                )

            # Orders from portfolio_orders; two-way reconcile with broker when possible.
            recent_orders = _load_live_account_orders(
                db, user_id=int(user_id), broker_account_id=resolved_account_for_orders or account_id
            )
            if broker_for_orders is not None and resolved_account_for_orders:
                try:
                    await _reconcile_robot_orders_with_broker(
                        db,
                        robot_id=int(robot_id),
                        broker=broker_for_orders,
                        account_id=resolved_account_for_orders,
                        user_id=int(user_id)
                    )
                    orders_synced_at = datetime.now(timezone.utc)
                    recent_orders = _load_live_account_orders(
                        db,
                        user_id=int(user_id),
                        broker_account_id=resolved_account_for_orders
                    )
                    try:
                        from app.modules.robots.live_events import notify_live_orders_refresh

                        notify_live_orders_refresh(
                            int(robot_id),
                            user_id=int(user_id),
                            account_id=str(resolved_account_for_orders)
                        )
                    except Exception:
                        pass
                except Exception as exc:
                    logger.warning(
                        "live snapshot order reconcile failed robot_id=%s: %s",
                        robot_id,
                        exc
                    )
            open_orders, order_history = _split_db_orders(recent_orders)

        stream_q = f"""
            SELECT MAX(created_at) AS last_event_at
            FROM robot_execution_logs
            WHERE robot_id = :robot_id
        """
        stream_row = db.execute(text(stream_q), {"robot_id": robot_id}).first()

        # Active background trading session (independent of Live UI /ws/live).
        session_q = f"""
            SELECT id, status, started_at, updated_at
            FROM background_jobs
            WHERE job_type = 'live_trading_session'
              AND (payload->>'robot_id')::text = :robot_id
              AND status IN ('queued', 'running')
            ORDER BY id DESC
            LIMIT 1
        """
        session_row = None
        try:
            session_row = db.execute(text(session_q), {"robot_id": str(robot_id)}).first()
        except Exception:
            session_row = None

        stream_health = {
            "last_event_at": stream_row[0] if stream_row else None,
            "connected_hint": int(robot.get("status") or 0) == 1,
            "trading_session_active": bool(session_row),
            "trading_session_status": str(session_row[1]) if session_row else None,
            "trading_session_started_at": session_row[2] if session_row else None,
            "trading_session_heartbeat_at": session_row[3] if session_row else None,
        }

        from app.modules.robots.live_events import fetch_recent_session_logs

        recent_logs = fetch_recent_session_logs(db, robot_id, limit=150)

        return {
            "robot_id": int(robot_id),
            "status": int(robot.get("status") or 0),
            "broker_type": broker_type,
            "strategy": strategy,
            "account_id": account_id,
            "active_positions": active_positions,
            "portfolio_positions": portfolio_positions,
            "portfolio_summary": portfolio_summary,
            "portfolio_fetch_error": portfolio_fetch_error,
            "portfolio_source": portfolio_source,
            "recent_signals": recent_signals,
            "recent_orders": recent_orders,
            "open_orders": open_orders,
            "order_history": order_history,
            "orders_synced_at": orders_synced_at,
            "recent_logs": recent_logs,
            "stream_health": stream_health,
        }

    async def place_manual_live_order(
            self,
            db: Session,
            *,
            user_id: int,
            robot_id: int,
            figi: str,
            side: str,
            price: float,
            quantity: Optional[float] = None,
            notional: Optional[float] = None,
            reduce_only: bool = False
    ) -> Dict[str, Any]:
        """Place a limit order via robot broker token (bypasses Stage6 risk gates)."""
        from app.modules.robots.live_events import insert_session_log, notify_live_orders_refresh
        from app.modules.robots.trading.brokers import create_broker_facade
        from app.modules.robots.trading.brokers.routing import (
            BrokerTokenMismatchError,
            enforce_broker_for_token
        )
        from app.modules.robots.trading.manual_order import (
            format_manual_broker_reject,
            resolve_manual_order_quantity
        )

        robot = await self.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Робот не является торговым"
            )
        token_meta = robot.get("token") or {}
        if not token_meta.get("id") or int(token_meta.get("status") or 0) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У робота нет активного токена доступа"
            )

        config = dict(robot.get("config") or {})
        try:
            token_type = int(token_meta.get("type")) if token_meta.get("type") is not None else None
        except (TypeError, ValueError):
            token_type = None
        try:
            broker_type = enforce_broker_for_token(
                config,
                token_type=token_type,
                mutate=True,
                require_token=True
            )
        except BrokerTokenMismatchError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        symbol = str(figi or "").strip().upper()
        if not symbol:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="figi обязателен")
        side_u = str(side or "").strip().upper()
        if side_u not in {"BUY", "SELL"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="side должен быть BUY или SELL")
        px = float(price or 0)
        if px <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="price must be > 0")

        try:
            qty = resolve_manual_order_quantity(price=px, quantity=quantity, notional=notional)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if qty <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quantity must be > 0")

        # T-Invest facade expects integer lots.
        order_qty: float | int = int(qty) if str(broker_type).lower() == "tinvest" else qty
        if str(broker_type).lower() == "tinvest" and int(order_qty) <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="для T-Invest quantity должен быть целым лотом >= 1"
            )

        token_id = int(token_meta["id"])
        td = await token_service.get_token_by_id(db, token_id, user_id)
        token_str = (td or {}).get("token")
        if not token_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="не удалось загрузить токен брокера"
            )
        token_extra = (td or {}).get("extra_data") if isinstance((td or {}).get("extra_data"), dict) else {}
        broker = create_broker_facade(
            broker_type,
            token_str,
            token_extra_data=token_extra,
            robot_config=config
        )
        account_id = await _resolve_robot_account_id(broker, config.get("account_id"))
        if not account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="у робота не задан account_id"
            )
        if not str(config.get("account_id") or "").strip():
            try:
                _persist_robot_account_id(db, robot_id, user_id, str(account_id))
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        direction = "ORDER_DIRECTION_BUY" if side_u == "BUY" else "ORDER_DIRECTION_SELL"
        size_from_notional = notional is not None and float(notional) > 0
        requested_notional = float(notional) if size_from_notional else None

        from app.modules.portfolio.order_registry import (
            SOURCE_MANUAL,
            insert_pending_order,
            resolve_portfolio_account_pk,
            update_order_by_pk
        )
        from app.modules.robots.trading.stages.stage6_orders import Stage6Orders

        pa_id = resolve_portfolio_account_pk(
            db, user_id=int(user_id), broker_account_id=str(account_id)
        )
        if not pa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="не удалось привязать заявку к portfolio_accounts"
            )

        portfolio_order_id = insert_pending_order(
            db,
            portfolio_account_id=int(pa_id),
            robot_id=int(robot_id),
            figi=symbol,
            side=side_u.lower(),
            quantity=float(order_qty),
            price=px,
            source=SOURCE_MANUAL,
            reason="manual",
            commit=True
        )
        if portfolio_order_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="не удалось сохранить заявку в portfolio_orders"
            )

        try:
            order = await broker.post_order(
                figi=symbol,
                quantity=order_qty,
                price=px,
                direction=direction,
                account_id=str(account_id),
                reduce_only=bool(reduce_only),
                qty_round_up=bool(size_from_notional)
            )
        except Exception as exc:
            logger.warning(
                "manual order failed robot_id=%s figi=%s side=%s: %s",
                robot_id,
                symbol,
                side_u,
                exc
            )
            update_order_by_pk(
                db,
                row_id=int(portfolio_order_id),
                status="rejected",
                commit=True
            )
            free_hint: Optional[float] = None
            try:
                free_hint = float(await broker.get_free_funds(str(account_id)))
            except Exception:
                free_hint = None
            detail = format_manual_broker_reject(exc, free_funds=free_hint)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"брокер отклонил заявку: {detail}"
            ) from exc

        order_id = str((order or {}).get("orderId") or "").strip()
        order_status = str(
            (order or {}).get("executionReportStatus") or "EXECUTION_REPORT_STATUS_NEW"
        )
        db_status = Stage6Orders.map_execution_status_to_trade_status(order_status)
        if db_status == "open":
            db_status = "filled"
        placed_qty = float(order_qty)
        try:
            if order and order.get("qty") is not None:
                placed_qty = float(order.get("qty"))
        except Exception:
            placed_qty = float(order_qty)

        update_order_by_pk(
            db,
            row_id=int(portfolio_order_id),
            order_id=order_id or None,
            status=db_status if db_status in {"pending", "partial", "filled", "cancelled", "rejected"} else "pending",
            quantity=placed_qty,
            price=px,
            commit=True
        )

        if size_from_notional and requested_notional is not None:
            log_msg = (
                f"[MANUAL] {side_u} {symbol} sum={requested_notional:g}USDT "
                f"→ qty={placed_qty:g} @ {px:g} order_id={order_id or '—'} "
                f"reduce_only={bool(reduce_only)}"
            )
        else:
            log_msg = (
                f"[MANUAL] {side_u} {symbol} qty={placed_qty:g} @ {px:g} "
                f"order_id={order_id or '—'} reduce_only={bool(reduce_only)}"
            )
        try:
            insert_session_log(db, robot_id=int(robot_id), message=log_msg, level="INFO")
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        if portfolio_order_id is not None:
            try:
                notify_live_orders_refresh(
                    int(robot_id),
                    user_id=int(user_id),
                    account_id=str(account_id) if account_id else None
                )
            except Exception:
                pass

        return {
            "order_id": order_id,
            "figi": symbol,
            "side": side_u,
            "quantity": placed_qty,
            "price": px,
            "status": db_status,
            "broker_type": str(broker_type),
            "reduce_only": bool(reduce_only),
            "notional": requested_notional,
            "size_mode": "notional" if size_from_notional else "quantity",
            "event_id": int(portfolio_order_id) if portfolio_order_id is not None else None,
            "account_order_id": int(portfolio_order_id) if portfolio_order_id is not None else None,
        }

    async def sync_live_orders(
            self,
            db: Session,
            *,
            user_id: int,
            robot_id: int
    ) -> Dict[str, Any]:
        """Reconcile portfolio_orders with broker open orders (statuses + import)."""
        from app.modules.robots.trading.brokers import create_broker_facade
        from app.modules.robots.trading.brokers.routing import (
            BrokerTokenMismatchError,
            enforce_broker_for_token
        )

        robot = await self.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="синхронизация заявок доступна только для торговых роботов"
            )
        token_meta = robot.get("token") or {}
        if not token_meta.get("id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У робота нет активного токена доступа"
            )
        config = dict(robot.get("config") or {})
        try:
            token_type = int(token_meta.get("type")) if token_meta.get("type") is not None else None
        except (TypeError, ValueError):
            token_type = None
        try:
            broker_type = enforce_broker_for_token(
                config,
                token_type=token_type,
                mutate=True,
                require_token=True
            )
        except BrokerTokenMismatchError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        td = await token_service.get_token_by_id(db, int(token_meta["id"]), user_id)
        token_str = (td or {}).get("token")
        if not token_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="не удалось загрузить токен брокера"
            )
        token_extra = (td or {}).get("extra_data") if isinstance((td or {}).get("extra_data"), dict) else {}
        broker = create_broker_facade(
            broker_type,
            token_str,
            token_extra_data=token_extra,
            robot_config=config
        )
        account_id = await _resolve_robot_account_id(broker, config.get("account_id"))
        if not account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="у робота не задан account_id"
            )

        # Manual sync must insert missing history (snapshot keeps insert_history=False).
        stats = await _reconcile_robot_orders_with_broker(
            db,
            robot_id=int(robot_id),
            broker=broker,
            account_id=str(account_id),
            user_id=int(user_id),
            insert_history=True
        )
        recent = _load_live_account_orders(
            db, user_id=int(user_id), broker_account_id=str(account_id)
        )
        open_orders, order_history = _split_db_orders(recent)
        try:
            from app.modules.robots.live_events import notify_live_orders_refresh

            notify_live_orders_refresh(
                int(robot_id),
                user_id=int(user_id),
                account_id=str(account_id)
            )
        except Exception:
            pass
        return {
            "robot_id": int(robot_id),
            "updated": int(stats.get("updated") or 0),
            "imported": int(stats.get("imported") or 0),
            "upserted": int(stats.get("upserted") or 0),
            "cancelled": int(stats.get("cancelled") or 0),
            "history_updated": int(stats.get("history_updated") or 0),
            "healed_open": int(stats.get("healed_open") or 0),
            "healed_closed": int(stats.get("healed_closed") or 0),
            "orders_synced_at": datetime.now(timezone.utc),
            "open_orders": open_orders,
            "order_history": order_history,
        }

    async def get_backtest_history(
            self,
            db: Session,
            user_id: int,
            robot_id: Optional[int] = None,
            limit: int = 30,
            only_active: bool = False,
            broker_type: Optional[str] = None
    ) -> Dict[str, Any]:
        if robot_id is not None:
            await self.get_robot_by_id(db, robot_id, user_id)

        status_filter = (
            "AND br.status IN ('RUNNING','QUEUED','FETCHING')"
            if only_active
            else "AND br.status IN ('SUCCESS','FAILED','CANCELLED','RUNNING','QUEUED','FETCHING')"
        )
        if robot_id is not None:
            where_robot = "br.robot_id = :robot_id"
            params_base: Dict[str, Any] = {"robot_id": robot_id}
        else:
            where_robot = "br.user_id = :user_id"
            params_base = {"user_id": user_id}

        broker_filter = ""
        bt_norm = str(broker_type or "").strip().lower()
        if bt_norm in ("tinvest", "bybit"):
            broker_filter = (
                "AND LOWER(COALESCE(br.config_snapshot->>'broker_type', 'tinvest')) = :broker_type"
            )
            params_base["broker_type"] = bt_norm

        total_sql = f"""
            SELECT COUNT(*)
            FROM backtest_runs br
            WHERE {where_robot}
              {status_filter}
              {broker_filter}
        """
        total = int(db.execute(text(total_sql), params_base).scalar() or 0)

        rows_sql = f"""
            SELECT
                br.id,
                br.robot_id,
                LOWER(NULLIF(TRIM(br.config_snapshot->>'strategy'), '')) AS strategy,
                br.status,
                br.run_phase,
                br.error_message,
                br.requested_from,
                br.requested_to,
                br.initial_capital,
                COALESCE(bm.final_equity, 0) AS final_equity,
                COALESCE(bm.total_return_percent, 0) AS total_return_percent,
                bm.max_drawdown_percent,
                br.started_at AS created_at,
                COALESCE(bm.payload, '{{}}'::jsonb) AS result_payload,
                LOWER(COALESCE(br.config_snapshot->>'broker_type', 'tinvest')) AS broker_type,
                COALESCE(
                    NULLIF(TRIM(br.config_snapshot->>'market_profile'), ''),
                    CASE
                        WHEN LOWER(COALESCE(br.config_snapshot->>'broker_type', 'tinvest')) = 'bybit'
                        THEN 'crypto'
                        ELSE 'moex'
                    END
                ) AS market_profile
            FROM backtest_runs br
            LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
            WHERE {where_robot}
              {status_filter}
              {broker_filter}
            ORDER BY br.started_at DESC
            LIMIT :limit
        """
        params = {**params_base, "limit": limit}
        rows = db.execute(text(rows_sql), params).fetchall()
        items = []
        for r in rows:
            strat_key = str(r[2]).strip().lower() if r[2] else None
            items.append(
                {
                "id": int(r[0]),
                "robot_id": int(r[1]) if r[1] is not None else None,
                "strategy": strat_key,
                "strategy_title": _strategy_display_title(strat_key),
                "status": str(r[3] or "").upper() or None,
                "run_phase": str(r[4]) if r[4] is not None else None,
                "error_message": str(r[5]) if r[5] else None,
                "requested_from": r[6],
                "requested_to": r[7],
                "initial_capital": float(r[8] or 0),
                "final_equity": float(r[9] or 0),
                "total_return_percent": float(r[10] or 0),
                "max_drawdown_percent": float(r[11]) if r[11] is not None else None,
                "created_at": r[12],
                "result_payload": r[13] or {},
                "broker_type": str(r[14]) if r[14] is not None else None,
                "market_profile": str(r[15]) if r[15] is not None else None,
                }
            )
        return {"total": total, "items": items}

    async def request_backtest_cancel(self, db: Session, run_id: int, user_id: int) -> Dict[str, Any]:
        """Отмена: QUEUED → сразу CANCELLED; RUNNING давно без финала → CANCELLED (зомби); иначе cancel_pending."""
        zombie_run_hours = 48
        header = db.execute(
            text(f"""
                SELECT br.robot_id, br.user_id, br.status, br.started_at
                FROM backtest_runs br
                WHERE br.id = :run_id
                LIMIT 1
            """),
            {"run_id": run_id}
        ).first()
        if not header:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
        robot_pk = header[0]
        run_uid = header[1]
        ok = False
        if run_uid is not None and int(run_uid) == int(user_id):
            ok = True
        elif robot_pk is not None:
            try:
                await self.get_robot_by_id(db, int(robot_pk), user_id)
                ok = True
            except HTTPException:
                ok = False
        if not ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к прогону")

        st = str(header[2] or "").upper()
        started_at = header[3]
        now = datetime.now(timezone.utc)
        if started_at is not None:
            sa = started_at
            if getattr(sa, "tzinfo", None) is None:
                sa = sa.replace(tzinfo=timezone.utc)
            else:
                sa = sa.astimezone(timezone.utc)
            stale_running = sa < (now - timedelta(hours=zombie_run_hours))
        else:
            stale_running = False

        if st in ("SUCCESS", "FAILED"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Прогон уже завершён")
        if st == "CANCELLED":
            db.commit()
            return {
                "run_id": run_id,
                "cancel_requested": True,
                "status": "CANCELLED",
                "run_phase": None,
                "stale_reconciled": False,
            }

        ts_fin = now
        out_status: Optional[str] = None
        out_phase: Optional[str] = None
        stale_flag = False

        if st == "QUEUED":
            db.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET cancel_requested = true,
                        status = 'CANCELLED',
                        partial_result = true,
                        finished_at = :ft,
                        run_phase = 'cancelled'
                    WHERE id = :rid AND status = 'QUEUED'
                    """
                ),
                {"rid": run_id, "ft": ts_fin}
            )
            out_status, out_phase = "CANCELLED", "cancelled"
        elif st in ("RUNNING", "FETCHING") and stale_running:
            stale_flag = True
            db.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET cancel_requested = true,
                        status = 'CANCELLED',
                        partial_result = true,
                        finished_at = :ft,
                        run_phase = 'cancelled'
                    WHERE id = :rid AND status IN ('RUNNING', 'FETCHING')
                    """
                ),
                {"rid": run_id, "ft": ts_fin}
            )
            out_status, out_phase = "CANCELLED", "cancelled"
        elif st in ("RUNNING", "FETCHING"):
            signal_history_backtest_cancel(run_id)
            db.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET cancel_requested = true,
                        status = 'CANCELLED',
                        partial_result = true,
                        finished_at = :ft,
                        run_phase = 'cancelled'
                    WHERE id = :rid AND status IN ('RUNNING', 'FETCHING')
                    """
                ),
                {"rid": run_id, "ft": ts_fin}
            )
            out_status, out_phase = "CANCELLED", "cancelled"
        else:
            db.execute(
                text(
                    f"UPDATE backtest_runs SET cancel_requested = true WHERE id = :rid"
                ),
                {"rid": run_id}
            )
            out_status = st if st else None
            out_phase = None

        db.commit()
        return {
            "run_id": run_id,
            "cancel_requested": True,
            "status": out_status,
            "run_phase": out_phase,
            "stale_reconciled": stale_flag,
        }

    async def get_active_backtest_run(self, db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        row = db.execute(
            text(f"""
                SELECT br.id FROM backtest_runs br
                WHERE br.status IN ('RUNNING','QUEUED','FETCHING')
                  AND (
                        br.user_id = :uid
                        OR br.robot_id IN (SELECT id FROM robots WHERE user_id = :uid)
                      )
                ORDER BY br.started_at DESC NULLS LAST, br.id DESC
                LIMIT 1
            """),
            {"uid": user_id}
        ).scalar()
        if not row:
            return None
        return await self.get_backtest_run_status(db, int(row), user_id)

    async def get_backtest_run_status(
            self,
            db: Session,
            run_id: int,
            user_id: int
    ) -> Dict[str, Any]:
        """Лёгкий статус прогона для опроса (без signals/orders/snapshots)."""
        from app.modules.robots.backtest_progress import phase_label_ru

        try:
            _maybe_reconcile_orphan_queued_run(db, run_id)
            _maybe_reconcile_zombie_failed_job(db, run_id)
            _maybe_reconcile_stale_backtest_run(db, run_id)
        except Exception:
            logger.exception("stale backtest reconcile failed run_id=%s", run_id)
            db.rollback()

        def _fetch_header():
            return db.execute(
                text(f"""
                SELECT
                    br.id,
                    br.robot_id,
                    br.user_id,
                    br.status,
                    br.requested_from,
                    br.requested_to,
                    br.started_at,
                    br.finished_at,
                    br.initial_capital,
                    br.partial_result,
                    br.progress_percent,
                    br.eta_seconds,
                    br.eta_confidence,
                    br.phase_units_done,
                    br.phase_units_total,
                    br.run_phase,
                    br.current_trade_date,
                    br.trade_dates_total,
                    br.trade_dates_remaining,
                    br.cancel_requested,
                    br.error_message
                FROM backtest_runs br
                WHERE br.id = :run_id
                LIMIT 1
            """),
                {"run_id": run_id}
            ).first()

        header = _fetch_header()
        if not header:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")

        st_pre = str(header[3] or "").upper()
        if st_pre in ("QUEUED", "RUNNING", "FETCHING"):
            try:
                started_pre = _coerce_utc_dt(header[6])
                if _maybe_reconcile_persist_checkpoint(db, run_id, started_pre):
                    header = _fetch_header()
                    if not header:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
                elif _maybe_reconcile_from_run_summary(db, run_id, started_pre):
                    header = _fetch_header()
                    if not header:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
                elif _maybe_reconcile_zombie_failed_job(db, run_id):
                    header = _fetch_header()
                    if not header:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
            except HTTPException:
                raise
            except Exception:
                logger.exception("summary.json reconcile failed run_id=%s", run_id)
                db.rollback()

        run_uid = header[2]
        robot_pk = header[1]
        authorized = False
        if run_uid is not None and int(run_uid) == int(user_id):
            authorized = True
        elif robot_pk is not None:
            try:
                await self.get_robot_by_id(db, int(robot_pk), user_id)
                authorized = True
            except HTTPException:
                authorized = False
        if not authorized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к прогону")

        run_phase = str(header[15]) if header[15] is not None else None
        st = str(header[3] or "UNKNOWN").upper()
        progress_percent = float(header[10]) if header[10] is not None else None
        if st in ("SUCCESS", "FAILED", "CANCELLED") and progress_percent is None:
            progress_percent = 100.0 if st == "SUCCESS" else progress_percent

        req_from = _coerce_utc_dt(header[4]) or datetime.now(timezone.utc)
        req_to = _coerce_utc_dt(header[5]) or req_from
        started_at = _coerce_utc_dt(header[6]) or req_from

        return {
            "run_id": int(header[0]),
            "robot_id": int(robot_pk) if robot_pk is not None else None,
            "status": st,
            "requested_from": req_from,
            "requested_to": req_to,
            "started_at": started_at,
            "finished_at": header[7],
            "initial_capital": float(header[8] or 0),
            "partial_result": bool(header[9]) if header[9] is not None else None,
            "progress_percent": progress_percent,
            "eta_seconds": int(header[11]) if header[11] is not None else None,
            "eta_confidence": str(header[12]) if header[12] is not None else None,
            "phase_units_done": int(header[13]) if header[13] is not None else None,
            "phase_units_total": int(header[14]) if header[14] is not None else None,
            "run_phase": run_phase,
            "phase_label": phase_label_ru(run_phase),
            "current_trade_date": header[16],
            "trade_dates_total": int(header[17]) if header[17] is not None else None,
            "trade_dates_remaining": int(header[18]) if header[18] is not None else None,
            "cancel_requested": bool(header[19]) if header[19] is not None else None,
            "error_message": str(header[20]) if header[20] else None,
        }

    async def get_backtest_run_details(
            self,
            db: Session,
            run_id: int,
            user_id: int
    ) -> Dict[str, Any]:
        header = db.execute(
            text(f"""
                SELECT
                    br.id,
                    br.robot_id,
                    br.user_id,
                    br.status,
                    br.requested_from,
                    br.requested_to,
                    br.started_at,
                    br.finished_at,
                    br.initial_capital,
                    bm.total_return_percent,
                    bm.max_drawdown_percent,
                    bm.final_equity,
                    bm.trades_total,
                    COALESCE(bm.payload, '{{}}'::jsonb) AS result_payload,
                    br.partial_result,
                    br.run_phase,
                    br.current_trade_date,
                    br.trade_dates_total,
                    br.trade_dates_remaining,
                    br.cancel_requested,
                    br.progress_percent,
                    br.eta_seconds,
                    br.eta_confidence,
                    br.phase_units_done,
                    br.phase_units_total
                FROM backtest_runs br
                LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
                WHERE br.id = :run_id
                LIMIT 1
            """),
            {"run_id": run_id}
        ).first()
        if not header:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
        run_uid = header[2]
        robot_pk = header[1]
        authorized = False
        if run_uid is not None and int(run_uid) == int(user_id):
            authorized = True
        elif robot_pk is not None:
            try:
                await self.get_robot_by_id(db, int(robot_pk), user_id)
                authorized = True
            except HTTPException:
                authorized = False
        if not authorized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к прогону")

        from app.modules.robots.backtest_progress import phase_label_ru

        robot_id = int(robot_pk) if robot_pk is not None else None
        run_phase_hdr = str(header[15]) if header[15] is not None else None
        st_hdr = str(header[3] or "UNKNOWN").upper()
        progress_hdr = float(header[20]) if header[20] is not None else None
        if st_hdr == "SUCCESS" and progress_hdr is None:
            progress_hdr = 100.0

        signals_rows = db.execute(
            text(f"""
                SELECT id, signal_time, figi, signal_type, price, was_executed, payload
                FROM backtest_signals
                WHERE run_id = :run_id
                ORDER BY id ASC
            """),
            {"run_id": run_id}
        ).fetchall()
        orders_rows = db.execute(
            text(f"""
                SELECT id, signal_time, figi, side, status, quantity, requested_price, executed_price, slippage_pct, commission, tax, pnl_net, payload
                FROM backtest_orders
                WHERE run_id = :run_id
                ORDER BY id ASC
            """),
            {"run_id": run_id}
        ).fetchall()
        portfolio_rows = db.execute(
            text(f"""
                SELECT id, snapshot_time, cash_balance, equity, positions_payload
                FROM backtest_portfolio_snapshots
                WHERE run_id = :run_id
                ORDER BY snapshot_time ASC
            """),
            {"run_id": run_id}
        ).fetchall()
        decisions_rows = db.execute(
            text(f"""
                SELECT trade_date, result
                FROM backtest_decisions
                WHERE run_id = :run_id
            """),
            {"run_id": run_id}
        ).fetchall()

        payload_obj = header[13] or {}
        payload_daily_summary = []
        if isinstance(payload_obj, dict):
            payload_daily_summary = list(payload_obj.get("daily_summary") or [])
        daily_summary = payload_daily_summary
        if not daily_summary:
            day_map: Dict[str, Dict[str, int]] = {}
            for dr in decisions_rows:
                d = str(dr[0])
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                if str(dr[1] or "").upper() == "ACCEPT":
                    day_map[d]["candidates_accept"] += 1
                else:
                    day_map[d]["candidates_reject"] += 1
            for r in signals_rows:
                d = str(r[1])[:10] if r[1] else ""
                if not d:
                    continue
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                day_map[d]["signals_total"] += 1
                if bool(r[5]):
                    day_map[d]["signals_executed"] += 1
            for r in orders_rows:
                d = str(r[1])[:10] if r[1] else ""
                if not d:
                    continue
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                day_map[d]["trades_total"] += 1
            daily_summary = [{"date": d, **vals} for d, vals in sorted(day_map.items(), key=lambda x: x[0])]

        return {
            "run_id": int(header[0]),
            "robot_id": robot_id,
            "status": str(header[3] or "UNKNOWN"),
            "requested_from": header[4],
            "requested_to": header[5],
            "started_at": header[6],
            "finished_at": header[7],
            "initial_capital": float(header[8] or 0),
            "total_return_percent": float(header[9]) if header[9] is not None else None,
            "max_drawdown_percent": float(header[10]) if header[10] is not None else None,
            "final_equity": float(header[11]) if header[11] is not None else None,
            "trades_total": int(header[12] or 0),
            "result_payload": payload_obj,
            "partial_result": bool(header[14]) if header[14] is not None else None,
            "run_phase": str(header[15]) if header[15] is not None else None,
            "current_trade_date": header[16],
            "trade_dates_total": int(header[17]) if header[17] is not None else None,
            "trade_dates_remaining": int(header[18]) if header[18] is not None else None,
            "cancel_requested": bool(header[19]) if header[19] is not None else None,
            "progress_percent": progress_hdr,
            "eta_seconds": int(header[21]) if header[21] is not None else None,
            "eta_confidence": str(header[22]) if header[22] is not None else None,
            "phase_units_done": int(header[23]) if header[23] is not None else None,
            "phase_units_total": int(header[24]) if header[24] is not None else None,
            "phase_label": phase_label_ru(run_phase_hdr),
            "signals": [
                {
                    "id": int(r[0]),
                    "signal_time": r[1],
                    "figi": r[2],
                    "signal_type": r[3],
                    "price": float(r[4]) if r[4] is not None else None,
                    "was_executed": bool(r[5]),
                    "payload": r[6] or {},
                }
                for r in signals_rows
            ],
            "orders": [
                {
                    "id": int(r[0]),
                    "signal_time": r[1],
                    "figi": r[2],
                    "side": r[3],
                    "status": r[4],
                    "quantity": float(r[5] or 0),
                    "requested_price": float(r[6]) if r[6] is not None else None,
                    "executed_price": float(r[7]) if r[7] is not None else None,
                    "slippage_pct": float(r[8] or 0),
                    "commission": float(r[9]) if r[9] is not None else None,
                    "tax": float(r[10]) if r[10] is not None else None,
                    "pnl_net": float(r[11]) if r[11] is not None else None,
                    "payload": r[12] or {},
                }
                for r in orders_rows
            ],
            "portfolio_snapshots": [
                {
                    "id": int(r[0]),
                    "snapshot_time": r[1],
                    "cash_balance": float(r[2] or 0),
                    "equity": float(r[3] or 0),
                    "positions_payload": r[4] or [],
                }
                for r in portfolio_rows
            ],
            "daily_summary": daily_summary,
        }

    async def compare_backtest_runs(
            self,
            db: Session,
            base_run_id: int,
            compare_run_id: int,
            user_id: int,
            name: Optional[str] = None
    ) -> Dict[str, Any]:
        def _run_header(run_id: int):
            row = db.execute(
                text(
                    f"""
                    SELECT br.id, br.robot_id, br.requested_from, br.requested_to, br.config_snapshot,
                           bm.total_return_percent, bm.max_drawdown_percent, bm.final_equity, bm.trades_total, bm.win_rate_percent
                    FROM backtest_runs br
                    LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
                    WHERE br.id=:run_id
                    LIMIT 1
                    """
                ),
                {"run_id": run_id}
            ).first()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Прогон {run_id} не найден")
            return row

        base = _run_header(base_run_id)
        comp = _run_header(compare_run_id)
        await self.get_robot_by_id(db, int(base[1]), user_id)
        await self.get_robot_by_id(db, int(comp[1]), user_id)

        def _as_float(v: Any) -> Optional[float]:
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        base_metrics = {
            "total_return_percent": _as_float(base[5]),
            "max_drawdown_percent": _as_float(base[6]),
            "final_equity": _as_float(base[7]),
            "trades_total": int(base[8] or 0),
            "win_rate_percent": _as_float(base[9]),
        }
        comp_metrics = {
            "total_return_percent": _as_float(comp[5]),
            "max_drawdown_percent": _as_float(comp[6]),
            "final_equity": _as_float(comp[7]),
            "trades_total": int(comp[8] or 0),
            "win_rate_percent": _as_float(comp[9]),
        }
        metrics_diff = {}
        for k in base_metrics.keys():
            bv = base_metrics[k]
            cv = comp_metrics[k]
            if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
                metrics_diff[k] = cv - bv
            else:
                metrics_diff[k] = None

        base_cfg = base[4] if isinstance(base[4], dict) else {}
        comp_cfg = comp[4] if isinstance(comp[4], dict) else {}
        keys = sorted(set(base_cfg.keys()) | set(comp_cfg.keys()))
        cfg_diff = {
            k: {"base": base_cfg.get(k), "compare": comp_cfg.get(k)}
            for k in keys
            if base_cfg.get(k) != comp_cfg.get(k)
        }

        cmp_id = int(
            db.execute(
                text(
                    """
                    INSERT INTO backtest_comparisons
                    (name, base_run_id, compare_run_id, config_diff)
                    VALUES (:name, :base_run_id, :compare_run_id, CAST(:config_diff AS jsonb))
                    RETURNING id
                    """
                ),
                {
                    "name": name or f"run-{base_run_id}-vs-{compare_run_id}",
                    "base_run_id": base_run_id,
                    "compare_run_id": compare_run_id,
                    "config_diff": json.dumps(cfg_diff, ensure_ascii=False),
                }
            ).scalar()
            or 0
        )
        db.commit()

        return {
            "comparison_id": cmp_id,
            "name": name or f"run-{base_run_id}-vs-{compare_run_id}",
            "base_run_id": base_run_id,
            "compare_run_id": compare_run_id,
            "metrics_base": base_metrics,
            "metrics_compare": comp_metrics,
            "metrics_diff": metrics_diff,
            "config_diff": cfg_diff,
        }

    async def list_backtest_comparisons(
            self,
            db: Session,
            user_id: int,
            limit: int = 30,
            offset: int = 0
    ) -> Dict[str, Any]:
        total = int(
            db.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM backtest_comparisons c
                    JOIN backtest_runs b ON b.id = c.base_run_id
                    JOIN backtest_runs r ON r.id = c.compare_run_id
                    JOIN robots rb ON rb.id = b.robot_id
                    JOIN robots rr ON rr.id = r.robot_id
                    WHERE rb.user_id = :user_id AND rr.user_id = :user_id
                    """
                ),
                {"user_id": user_id}
            ).scalar()
            or 0
        )
        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.name, c.base_run_id, c.compare_run_id, c.config_diff, c.created_at
                FROM backtest_comparisons c
                JOIN backtest_runs b ON b.id = c.base_run_id
                JOIN backtest_runs r ON r.id = c.compare_run_id
                JOIN robots rb ON rb.id = b.robot_id
                JOIN robots rr ON rr.id = r.robot_id
                WHERE rb.user_id = :user_id AND rr.user_id = :user_id
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"user_id": user_id, "limit": limit, "offset": offset}
        ).fetchall()
        items = [
            {
                "id": int(r[0]),
                "name": str(r[1] or ""),
                "base_run_id": int(r[2]),
                "compare_run_id": int(r[3]),
                "config_diff": r[4] or {},
                "created_at": r[5],
            }
            for r in rows
        ]
        return {"total": total, "items": items}

    async def get_backtest_comparison(
            self,
            db: Session,
            comparison_id: int,
            user_id: int
    ) -> Dict[str, Any]:
        row = db.execute(
            text(
                f"""
                SELECT c.id, c.name, c.base_run_id, c.compare_run_id
                FROM backtest_comparisons c
                JOIN backtest_runs b ON b.id = c.base_run_id
                JOIN backtest_runs r ON r.id = c.compare_run_id
                JOIN robots rb ON rb.id = b.robot_id
                JOIN robots rr ON rr.id = r.robot_id
                WHERE c.id = :comparison_id
                  AND rb.user_id = :user_id
                  AND rr.user_id = :user_id
                LIMIT 1
                """
            ),
            {"comparison_id": comparison_id, "user_id": user_id}
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сравнение не найдено")
        return await self.compare_backtest_runs(
            db=db,
            base_run_id=int(row[2]),
            compare_run_id=int(row[3]),
            user_id=user_id,
            name=str(row[1] or f"cmp-{comparison_id}")
        )

    async def run_backtest(self, request: schemas.BacktestRequest) -> Dict[str, Any]:
        returns = request.returns or []
        equity = float(request.initial_capital)
        equity_curve = [equity]
        fee_mult = float(request.fee_bps) / 10000.0

        for r in returns:
            pnl = equity * float(r)
            fees = abs(equity * float(r)) * fee_mult
            equity = max(0.0, equity + pnl - fees)
            equity_curve.append(equity)

        total_return_pct = ((equity / request.initial_capital) - 1.0) * 100.0 if request.initial_capital > 0 else 0.0
        max_dd = self._calc_drawdown_percent(equity_curve)
        sharpe = self._calc_sharpe_from_returns(returns)
        return {
            "initial_capital": round(request.initial_capital, 4),
            "final_equity": round(equity, 4),
            "total_return_percent": round(total_return_pct, 4),
            "max_drawdown_percent": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "trades_count": len(returns),
            "equity_curve": [round(v, 4) for v in equity_curve],
        }

    async def run_walk_forward(self, request: schemas.WalkForwardRequest) -> Dict[str, Any]:
        returns = request.returns or []
        if len(returns) < request.folds * 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недостаточно точек returns для walk-forward"
            )
        chunk = max(2, len(returns) // request.folds)
        folds = []
        for idx in range(request.folds):
            start = idx * chunk
            end = min(len(returns), start + chunk)
            segment = returns[start:end]
            if len(segment) < 2:
                continue
            train_len = max(1, int(len(segment) * request.train_ratio))
            test = segment[train_len:]
            if not test:
                continue
            bt = await self.run_backtest(
                schemas.BacktestRequest(
                    returns=test,
                    initial_capital=request.initial_capital,
                    fee_bps=request.fee_bps
                )
            )
            folds.append({
                "fold": idx + 1,
                "train_points": train_len,
                "test_points": len(test),
                "final_equity": bt["final_equity"],
                "total_return_percent": bt["total_return_percent"],
                "max_drawdown_percent": bt["max_drawdown_percent"],
                "sharpe_ratio": bt["sharpe_ratio"],
            })
        if not folds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Walk-forward не удалось построить")
        avg_return = sum(f["total_return_percent"] for f in folds) / len(folds)
        sharpes = [f["sharpe_ratio"] for f in folds if f.get("sharpe_ratio") is not None]
        avg_sharpe = (sum(sharpes) / len(sharpes)) if sharpes else None
        return {
            "folds": folds,
            "avg_total_return_percent": round(avg_return, 4),
            "avg_sharpe_ratio": round(avg_sharpe, 4) if avg_sharpe is not None else None,
        }

    async def set_paper_mode(self, db: Session, user_id: int, robot_id: int, enabled: bool) -> Dict[str, Any]:
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        config = dict(robot.get("config") or {})
        config["paper_mode"] = bool(enabled)
        await self.update_robot_config(db, robot_id, user_id, config)
        return {"robot_id": robot_id, "paper_mode": bool(enabled)}

    @staticmethod
    def _calc_drawdown_percent(curve: List[float]) -> float:
        if not curve:
            return 0.0
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            if peak > 0:
                dd = ((peak - v) / peak) * 100.0
                max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _calc_sharpe_from_returns(returns: List[float]) -> Optional[float]:
        if not returns:
            return None
        n = len(returns)
        mean = sum(float(r) for r in returns) / n
        if n < 2:
            return None
        var = sum((float(r) - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(var)
        if std <= 0:
            return None
        return (mean / std) * math.sqrt(n)

    def _validate_robot_config(self, config: Dict[str, Any]) -> None:
        """Валидирует конфиг v2 (П1/П2/П3) + legacy-зеркало."""
        from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config

        known_fields = set(schemas.GrainSeedConfig.model_fields.keys())
        extra_fields = {k: v for k, v in (config or {}).items() if k not in known_fields}
        try:
            validated = validate_robot_config(
                robot_type=2,
                raw=config or {},
                broker_type=str((config or {}).get("broker_type") or "tinvest")
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Некорректный config: {e}"
            )

        broker = str(validated.broker_type or "").lower()
        if validated.signal_generation is not None:
            ds = str(getattr(validated.signal_generation, "data_source", "") or "").lower()
            if ds in ("tinvest", "moex", "moex_iss"):
                broker = ds
        from app.modules.robots.trading.brokers.routing import is_supported_live_broker, normalize_broker_type

        if not is_supported_live_broker(normalize_broker_type(broker)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"broker_type '{broker}' не поддерживается"
            )

        config.clear()
        config.update(dump_robot_config(validated))
        config.update(extra_fields)


# Создаем экземпляр сервиса
robot_service = RobotService()
