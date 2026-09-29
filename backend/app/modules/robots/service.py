# app/modules/robots/service.py
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime, timezone, timedelta, date, time
import json
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

# Cancel flags live in robots_v2 (shared by OsEngine / leftover callers).
from app.modules.trading_core.cancel import (  # noqa: E402
    clear_backtest_cancel,
    is_backtest_cancelled,
    signal_backtest_cancel,
)


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
    from app.modules.trading_core.broker_position_sync import extract_account_position_meta

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
    from app.modules.trading_core.brokers.routing import normalize_broker_type

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
        from app.modules.trading_core.data.providers.moex_snapshots import log_moex_external_api_isolated

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
        from app.modules.trading_core.brokers.routing import normalize_broker_type

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
        from app.modules.trading_core.brokers.routing import normalize_broker_type
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
        from app.modules.trading_core.brokers.routing import (
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
        from app.modules.trading_core.brokers.routing import normalize_broker_type

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
        from app.modules.trading_core.brokers.routing import normalize_broker_type

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
            from app.modules.trading_core.brokers.routing import normalize_broker_type

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
            current_broker = _normalized_broker(current_cfg.get("broker_type"))
            if "broker_type" in incoming_cfg:
                requested_broker = _normalized_broker(incoming_cfg.get("broker_type"))
                if current_broker and requested_broker and requested_broker != current_broker:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "broker_type нельзя изменить для существующего робота. "
                            "Создайте нового робота (или используйте duplicate workflow)."
                        ),
                    )
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
        from app.modules.trading_core.brokers.routing import normalize_broker_type

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
        from app.modules.trading_core.brokers.routing import normalize_broker_type

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
        from app.modules.trading_core.intervals import resolve_candle_interval_roles

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

    #/// Legacy history-backtest HTTP orchestration removed; prod path is robots_v2.backtest.
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
        from app.modules.trading_core.brokers.routing import (
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
                        robot_config=config,
                        user_id=user_id,
                        token_id=int(token_id) if token_id is not None else None,
                        context_type="robots_service",
                        context_ref=str(robot_id),
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
        from app.modules.trading_core.brokers.routing import (
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
            robot_config=config,
            user_id=user_id,
            token_id=token_id,
            context_type="robots_service",
            context_ref=str(robot_id),
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
        from app.modules.trading_core.brokers.routing import (
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
            robot_config=config,
            user_id=user_id,
            token_id=int(token_meta["id"]),
            context_type="robots_service",
            context_ref=str(robot_id),
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
        from app.modules.trading_core.brokers.routing import is_supported_live_broker, normalize_broker_type

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
