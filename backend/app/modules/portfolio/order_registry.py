"""Unified portfolio_orders registry (T-Invest / Bybit) + Filled → portfolio_operations."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

SOURCE_ROBOT = "robot"
SOURCE_MANUAL = "manual"
SOURCE_EXTERNAL = "external"
VALID_SOURCES = frozenset({SOURCE_ROBOT, SOURCE_MANUAL, SOURCE_EXTERNAL})

# Live-normalized statuses
STATUS_PENDING = "pending"
STATUS_PARTIAL = "partial"
STATUS_FILLED = "filled"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"


def resolve_portfolio_account_pk(
    db: Session,
    *,
    user_id: int,
    broker_account_id: str,
    create_if_missing: bool = True,
    account_type: str = "broker",
) -> Optional[int]:
    """Resolve portfolio_accounts.id for (user_id, external account_id)."""
    aid = str(broker_account_id or "").strip()
    if not aid or not user_id:
        return None
    try:
        row = db.execute(
            text(
                f"""
                SELECT id FROM portfolio_accounts
                WHERE user_id = :user_id AND account_id = :account_id
                LIMIT 1
                """
            ),
            {"user_id": int(user_id), "account_id": aid},
        ).first()
        if row:
            return int(row[0])
        if not create_if_missing:
            return None
        now = datetime.now(timezone.utc)
        created = db.execute(
            text(
                f"""
                INSERT INTO portfolio_accounts
                (user_id, account_id, account_type, account_name, account_status,
                 opened_date, is_active, created_at)
                VALUES
                (:user_id, :account_id, :account_type, :account_name, :account_status,
                 :opened_date, 1, :now)
                RETURNING id
                """
            ),
            {
                "user_id": int(user_id),
                "account_id": aid,
                "account_type": str(account_type or "broker"),
                "account_name": aid,
                "account_status": "open",
                "opened_date": now,
                "now": now,
            },
        ).first()
        db.commit()
        return int(created[0]) if created else None
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(
            "resolve_portfolio_account_pk failed user_id=%s account_id=%s: %s",
            user_id,
            aid,
            exc,
        )
        return None


def normalize_live_order_status(status: str, *, closing: bool = False) -> str:
    """Map broker / EXECUTION_REPORT statuses to Live portfolio_orders statuses."""
    from app.modules.robots.trading.stages.stage6_orders import Stage6Orders

    raw = str(status or "").strip()
    if not raw:
        return STATUS_PENDING
    if raw.startswith("EXECUTION_REPORT_"):
        mapped = Stage6Orders.map_execution_status_to_trade_status(raw, closing=closing)
        # Entry FILL was "open" (position) — for order registry use filled.
        if mapped == "open":
            return STATUS_FILLED
        if mapped == "closed":
            return STATUS_FILLED
        if mapped in {STATUS_PENDING, STATUS_PARTIAL, STATUS_CANCELLED, STATUS_REJECTED, "failed"}:
            return STATUS_REJECTED if mapped == "failed" else mapped
        return STATUS_PENDING
    key = raw.lower().replace(" ", "").replace("_", "")
    bybit_map = {
        "new": STATUS_PENDING,
        "created": STATUS_PENDING,
        "untriggered": STATUS_PENDING,
        "triggered": STATUS_PENDING,
        "active": STATUS_PENDING,
        "pending": STATUS_PENDING,
        "partiallyfilled": STATUS_PARTIAL,
        "partialfill": STATUS_PARTIAL,
        "partial": STATUS_PARTIAL,
        "filled": STATUS_FILLED,
        "cancelled": STATUS_CANCELLED,
        "canceled": STATUS_CANCELLED,
        "deactivated": STATUS_CANCELLED,
        "rejected": STATUS_REJECTED,
    }
    if key in bybit_map:
        return bybit_map[key]
    if key in {STATUS_PENDING, STATUS_PARTIAL, STATUS_FILLED, STATUS_CANCELLED, STATUS_REJECTED}:
        return key
    if key in {"open", "closed"}:
        return STATUS_FILLED
    return STATUS_PENDING


def _merge_extra(
    existing: Optional[Dict[str, Any]],
    *,
    source: Optional[str] = None,
    robot_id: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
    preserve_source: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(existing or {})
    if extra:
        out.update(extra)
    if source and (not preserve_source or not out.get("source")):
        src = str(source).strip().lower()
        if src in VALID_SOURCES:
            out["source"] = src
    elif source and not preserve_source:
        src = str(source).strip().lower()
        if src in VALID_SOURCES:
            out["source"] = src
    if robot_id is not None and out.get("robot_id") is None:
        out["robot_id"] = int(robot_id)
    return out


def parse_broker_order_date(value: Any) -> Optional[datetime]:
    """Parse broker created_at / createdTime into aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    # epoch ms / s
    try:
        if raw.isdigit() or (raw.replace(".", "", 1).isdigit() and raw.count(".") <= 1):
            num = float(raw)
            if num > 1e12:  # ms
                return datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
            if num > 1e9:  # s
                return datetime.fromtimestamp(num, tz=timezone.utc)
    except Exception:
        pass
    try:
        # ISO from Bybit facade normalize
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _direction_from_side(side: str) -> str:
    s = str(side or "").strip().lower()
    if s in {"sell", "short", "order_direction_sell"}:
        return "sell"
    return "buy"


def normalize_order_reason(
    reason: Optional[str] = None,
    *,
    intent_source: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[str]:
    """Normalize create/exit reason for portfolio_orders.reason (max 64 chars)."""
    raw = str(reason or "").strip()
    if raw:
        key = raw.lower().replace(" ", "_").replace("-", "_")
        # grain_seed_force_flatten → flatten
        if key in {"grain_seed_force_flatten", "force_flatten"}:
            return "flatten"
        return key[:64]
    intent = str(intent_source or "").strip().lower()
    intent_map = {
        "entry": "entry",
        "exit_strategy": "exit_strategy",
        "exit_sl_tp": "exit_sl_tp",
        "flatten": "flatten",
    }
    if intent in intent_map:
        return intent_map[intent]
    src = str(source or "").strip().lower()
    if src == SOURCE_MANUAL:
        return "manual"
    if src == SOURCE_EXTERNAL:
        return "external"
    return None


def insert_pending_order(
    db: Session,
    *,
    portfolio_account_id: int,
    figi: str,
    side: str,
    quantity: float,
    source: str,
    price: Optional[float] = None,
    robot_id: Optional[int] = None,
    order_kind: str = "limit",
    reason: Optional[str] = None,
    commit: bool = True,
) -> Optional[int]:
    """Insert a local pending row with temporary order_id; returns portfolio_orders.id."""
    now = datetime.now(timezone.utc)
    temp_oid = f"pending:{uuid.uuid4().hex[:20]}"
    src = str(source or SOURCE_EXTERNAL).lower()
    if src not in VALID_SOURCES:
        src = SOURCE_EXTERNAL
    extra = _merge_extra(None, source=src, robot_id=robot_id, preserve_source=False)
    reason_norm = normalize_order_reason(reason, source=src)
    try:
        row = db.execute(
            text(
                f"""
                INSERT INTO portfolio_orders
                (account_id, order_id, figi, order_type, order_direction, order_date,
                 lots_requested, lots_executed, price, execution_price, status, reason,
                 extra_data, created_at)
                VALUES
                (:account_id, :order_id, :figi, :order_type, :order_direction, :order_date,
                 :lots_requested, :lots_executed, :price, :execution_price, :status, :reason,
                 CAST(:extra_data AS jsonb), :now)
                RETURNING id
                """
            ),
            {
                "account_id": int(portfolio_account_id),
                "order_id": temp_oid,
                "figi": str(figi or "").strip().upper(),
                "order_type": str(order_kind or "limit"),
                "order_direction": _direction_from_side(side),
                "order_date": now,
                "lots_requested": float(quantity),
                "lots_executed": 0,
                "price": float(price) if price is not None else None,
                "execution_price": None,
                "status": STATUS_PENDING,
                "reason": reason_norm,
                "extra_data": json.dumps(extra, ensure_ascii=False),
                "now": now,
            },
        ).first()
        if commit:
            db.commit()
        return int(row[0]) if row else None
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("insert_pending_order failed account=%s: %s", portfolio_account_id, exc)
        return None


def update_order_by_pk(
    db: Session,
    *,
    row_id: int,
    order_id: Optional[str] = None,
    status: Optional[str] = None,
    quantity: Optional[float] = None,
    filled_qty: Optional[float] = None,
    price: Optional[float] = None,
    avg_price: Optional[float] = None,
    commit: bool = True,
) -> bool:
    now = datetime.now(timezone.utc)
    try:
        db.execute(
            text(
                f"""
                UPDATE portfolio_orders
                SET order_id = COALESCE(:order_id, order_id),
                    status = COALESCE(:status, status),
                    lots_requested = COALESCE(:lots_requested, lots_requested),
                    lots_executed = COALESCE(:lots_executed, lots_executed),
                    price = COALESCE(:price, price),
                    execution_price = COALESCE(:execution_price, execution_price)
                WHERE id = :id
                """
            ),
            {
                "id": int(row_id),
                "order_id": str(order_id).strip() if order_id else None,
                "status": status,
                "lots_requested": quantity,
                "lots_executed": filled_qty,
                "price": price if price is not None and price > 0 else None,
                "execution_price": avg_price,
            },
        )
        if commit:
            db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("update_order_by_pk failed id=%s: %s", row_id, exc)
        return False


def find_order_by_broker_id(
    db: Session,
    *,
    portfolio_account_id: int,
    order_id: str,
) -> Optional[Dict[str, Any]]:
    oid = str(order_id or "").strip()
    if not oid:
        return None
    try:
        row = db.execute(
            text(
                f"""
                SELECT id, status, extra_data, order_direction, reason
                FROM portfolio_orders
                WHERE account_id = :account_id AND order_id = :order_id
                LIMIT 1
                """
            ),
            {"account_id": int(portfolio_account_id), "order_id": oid},
        ).first()
        if not row:
            return None
        extra = row[2] if isinstance(row[2], dict) else {}
        if isinstance(row[2], str):
            try:
                extra = json.loads(row[2])
            except Exception:
                extra = {}
        return {
            "id": int(row[0]),
            "status": str(row[1]),
            "extra_data": extra or {},
            "source": str((extra or {}).get("source") or SOURCE_EXTERNAL),
            "side": str(row[3] or "buy"),
            "reason": str(row[4]).strip() if len(row) > 4 and row[4] else None,
        }
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


def upsert_broker_order(
    db: Session,
    *,
    portfolio_account_id: int,
    order_id: str,
    figi: str,
    side: str,
    quantity: float,
    status: str,
    price: Optional[float] = None,
    filled_qty: Optional[float] = None,
    avg_price: Optional[float] = None,
    source: str = SOURCE_EXTERNAL,
    robot_id: Optional[int] = None,
    order_kind: str = "limit",
    order_date: Optional[datetime] = None,
    reason: Optional[str] = None,
    intent_source: Optional[str] = None,
    commit: bool = False,
    promote_filled: bool = True,
    broker_prefix: str = "bybit",
) -> str:
    """Insert or update portfolio_orders. Returns 'inserted' | 'updated' | 'skipped'.

    Never overwrites existing extra_data.source when already robot/manual.
    Never clears an existing reason when the new reason is empty.
    """
    oid = str(order_id or "").strip()
    if not oid or not figi:
        return "skipped"
    now = order_date or datetime.now(timezone.utc)
    live_status = normalize_live_order_status(status)
    reason_norm = normalize_order_reason(reason, intent_source=intent_source, source=source)
    existing = find_order_by_broker_id(
        db, portfolio_account_id=int(portfolio_account_id), order_id=oid
    )
    if existing is not None:
        prev_extra = dict(existing.get("extra_data") or {})
        # Preserve robot/manual source
        preserve = str(prev_extra.get("source") or "") in {SOURCE_ROBOT, SOURCE_MANUAL}
        extra = _merge_extra(
            prev_extra,
            source=None if preserve else source,
            robot_id=robot_id,
            preserve_source=preserve,
        )
        # Keep prior reason unless we have a new one
        reason_to_set = reason_norm or existing.get("reason")
        try:
            db.execute(
                text(
                    f"""
                    UPDATE portfolio_orders
                    SET status = :status,
                        lots_requested = COALESCE(:lots_requested, lots_requested),
                        lots_executed = COALESCE(:lots_executed, lots_executed),
                        price = COALESCE(:price, price),
                        execution_price = COALESCE(:execution_price, execution_price),
                        figi = COALESCE(:figi, figi),
                        order_direction = COALESCE(:order_direction, order_direction),
                        order_date = COALESCE(:order_date, order_date),
                        reason = COALESCE(:reason, reason),
                        extra_data = CAST(:extra_data AS jsonb)
                    WHERE account_id = :account_id AND order_id = :order_id
                    """
                ),
                {
                    "status": live_status,
                    "lots_requested": quantity if quantity > 0 else None,
                    "lots_executed": filled_qty,
                    "price": price if price is not None and price > 0 else None,
                    "execution_price": avg_price,
                    "figi": str(figi).strip().upper(),
                    "order_direction": _direction_from_side(side),
                    "order_date": order_date,
                    "reason": reason_to_set,
                    "extra_data": json.dumps(extra, ensure_ascii=False),
                    "account_id": int(portfolio_account_id),
                    "order_id": oid,
                },
            )
            if commit:
                db.commit()
            if promote_filled and live_status == STATUS_FILLED:
                promote_filled_order_to_operation(
                    db,
                    portfolio_account_id=int(portfolio_account_id),
                    order_id=oid,
                    figi=str(figi).strip().upper(),
                    side=_direction_from_side(side),
                    quantity=float(filled_qty if filled_qty is not None else quantity or 0),
                    price=float(avg_price or price or 0),
                    order_date=now,
                    broker_prefix=broker_prefix,
                    commit=commit,
                )
            return "updated"
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("upsert_broker_order update failed oid=%s: %s", oid, exc)
            return "skipped"

    src = str(source or SOURCE_EXTERNAL).lower()
    if src not in VALID_SOURCES:
        src = SOURCE_EXTERNAL
    if reason_norm is None:
        reason_norm = normalize_order_reason(None, intent_source=intent_source, source=src)
    extra = _merge_extra(None, source=src, robot_id=robot_id, preserve_source=False)
    try:
        db.execute(
            text(
                f"""
                INSERT INTO portfolio_orders
                (account_id, order_id, figi, order_type, order_direction, order_date,
                 lots_requested, lots_executed, price, execution_price, status, reason,
                 extra_data, created_at)
                VALUES
                (:account_id, :order_id, :figi, :order_type, :order_direction, :order_date,
                 :lots_requested, :lots_executed, :price, :execution_price, :status, :reason,
                 CAST(:extra_data AS jsonb), :now)
                """
            ),
            {
                "account_id": int(portfolio_account_id),
                "order_id": oid,
                "figi": str(figi).strip().upper(),
                "order_type": str(order_kind or "limit"),
                "order_direction": _direction_from_side(side),
                "order_date": now,
                "lots_requested": float(quantity or 0),
                "lots_executed": filled_qty,
                "price": price if price is not None and price > 0 else None,
                "execution_price": avg_price,
                "status": live_status,
                "reason": reason_norm,
                "extra_data": json.dumps(extra, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
            },
        )
        if commit:
            db.commit()
        if promote_filled and live_status == STATUS_FILLED:
            promote_filled_order_to_operation(
                db,
                portfolio_account_id=int(portfolio_account_id),
                order_id=oid,
                figi=str(figi).strip().upper(),
                side=_direction_from_side(side),
                quantity=float(filled_qty if filled_qty is not None else quantity or 0),
                price=float(avg_price or price or 0),
                order_date=now,
                broker_prefix=broker_prefix,
                commit=commit,
            )
        return "inserted"
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("upsert_broker_order insert skip oid=%s: %s", oid, exc)
        return "skipped"


def promote_filled_order_to_operation(
    db: Session,
    *,
    portfolio_account_id: int,
    order_id: str,
    figi: str,
    side: str,
    quantity: float,
    price: float,
    order_date: datetime,
    broker_prefix: str = "bybit",
    commit: bool = False,
) -> bool:
    """Upsert ORDER_BUY/SELL into portfolio_operations (does not delete period range)."""
    oid = str(order_id or "").strip()
    if not oid:
        return False
    op_id = f"{broker_prefix}_order:{oid}"
    direction = _direction_from_side(side)
    op_type = "ORDER_BUY" if direction == "buy" else "ORDER_SELL"
    qty = float(quantity or 0)
    px = float(price or 0)
    payment = qty * px
    if direction == "sell":
        payment = abs(payment)
    else:
        payment = -abs(payment) if payment else 0.0
    type_text = f"{'Buy' if direction == 'buy' else 'Sell'} · Filled"
    extra = {
        "type_text": type_text,
        "source": "order_history",
        "broker_order_id": oid,
    }
    try:
        db.execute(
            text(
                f"""
                INSERT INTO portfolio_operations
                (account_id, operation_id, parent_operation_id, figi, instrument_type,
                 instrument_uid, position_uid, operation_type, operation_date,
                 quantity, quantity_rest, price, price_currency, payment, payment_currency,
                 commission, commission_currency, status, trades, extra_data, created_at)
                VALUES
                (:account_id, :operation_id, NULL, :figi, :instrument_type,
                 :instrument_uid, NULL, :operation_type, :operation_date,
                 :quantity, 0, :price, :price_currency, :payment, :payment_currency,
                 NULL, NULL, :status, CAST(:trades AS jsonb), CAST(:extra_data AS jsonb), :now)
                ON CONFLICT (operation_id) DO UPDATE SET
                    figi = EXCLUDED.figi,
                    operation_type = EXCLUDED.operation_type,
                    operation_date = EXCLUDED.operation_date,
                    quantity = EXCLUDED.quantity,
                    price = EXCLUDED.price,
                    payment = EXCLUDED.payment,
                    status = EXCLUDED.status,
                    extra_data = EXCLUDED.extra_data
                """
            ),
            {
                "account_id": int(portfolio_account_id),
                "operation_id": op_id[:120],
                "figi": str(figi or "").strip().upper() or None,
                "instrument_type": "crypto" if broker_prefix == "bybit" else "share",
                "instrument_uid": f"{broker_prefix.upper()}:{figi}" if figi else None,
                "operation_type": op_type,
                "operation_date": order_date,
                "quantity": qty,
                "price": px,
                "price_currency": "USDT" if broker_prefix == "bybit" else "RUB",
                "payment": payment,
                "payment_currency": "USDT" if broker_prefix == "bybit" else "RUB",
                "status": "Filled",
                "trades": "[]",
                "extra_data": json.dumps(extra, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
            },
        )
        if commit:
            db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("promote_filled_order_to_operation failed oid=%s: %s", oid, exc)
        return False


def _portfolio_order_label_maps(db: Session) -> Dict[str, Dict[str, str]]:
    """Load PORTFOLIO_ORDERS dictionary labels: column → {string_value → name}."""
    maps: Dict[str, Dict[str, str]] = {
        "ORDER_DIRECTION": {},
        "STATUS": {},
        "SOURCE": {},
        "REASON": {},
    }
    try:
        rows = db.execute(
            text(
                f"""
                SELECT column_name, string_value, name
                FROM dictionary
                WHERE table_name = 'PORTFOLIO_ORDERS'
                  AND column_name IN ('ORDER_DIRECTION', 'STATUS', 'SOURCE', 'REASON')
                  AND hide_from_ui = 0
                """
            )
        ).fetchall()
    except Exception as exc:
        logger.debug("portfolio order labels load failed: %s", exc)
        return maps
    for col, string_value, name in rows:
        key = str(col or "").strip().upper()
        if key not in maps:
            continue
        sv = str(string_value or "").strip().lower()
        label = str(name or "").strip()
        if sv and label:
            maps[key][sv] = label
    return maps


def load_portfolio_orders(
    db: Session,
    *,
    portfolio_account_id: int,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, figi, order_direction, lots_requested, price, order_id, status,
                       order_date, lots_executed, execution_price, extra_data, order_type,
                       reason
                FROM portfolio_orders
                WHERE account_id = :account_id
                ORDER BY order_date DESC
                LIMIT :limit
                """
            ),
            {"account_id": int(portfolio_account_id), "limit": int(limit)},
        ).fetchall()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("load_portfolio_orders failed account=%s: %s", portfolio_account_id, exc)
        return []
    labels = _portfolio_order_label_maps(db)
    dir_map = labels.get("ORDER_DIRECTION") or {}
    status_map = labels.get("STATUS") or {}
    source_map = labels.get("SOURCE") or {}
    reason_map = labels.get("REASON") or {}
    out: List[Dict[str, Any]] = []
    for r in rows:
        extra = r[10] if isinstance(r[10], dict) else {}
        if isinstance(r[10], str):
            try:
                extra = json.loads(r[10])
            except Exception:
                extra = {}
        source = str((extra or {}).get("source") or SOURCE_ROBOT).strip().lower()
        side = str(r[2] or "buy").strip().lower()
        status = str(r[6] or "").strip().lower()
        reason = str(r[12]).strip() if len(r) > 12 and r[12] else None
        reason_key = reason.lower() if reason else ""
        out.append(
            {
                "id": int(r[0]),
                "figi": str(r[1] or ""),
                "side": side or "buy",
                "side_name": dir_map.get(side) or side or "buy",
                "quantity": float(r[3] or 0),
                "price": float(r[4] or 0) if r[4] is not None else 0.0,
                "order_id": r[5],
                "status": status,
                "status_name": status_map.get(status) or status,
                "created_at": r[7],
                "filled_qty": float(r[8]) if r[8] is not None else None,
                "avg_price": float(r[9]) if r[9] is not None else None,
                "updated_at": r[7],
                "source": source,
                "source_name": source_map.get(source) or source,
                "order_type": source,
                "broker_order_type": str(r[11] or "limit"),
                "robot_id": (extra or {}).get("robot_id"),
                "reason": reason,
                "reason_name": reason_map.get(reason_key) or reason,
            }
        )
    return out


def insert_robot_orders_batch(
    db: Session,
    *,
    portfolio_account_id: int,
    robot_id: int,
    trades: List[Dict[str, Any]],
    broker_prefix: str = "bybit",
) -> int:
    if not trades or not portfolio_account_id:
        return 0
    n = 0
    for t in trades:
        st = str(t.get("status") or "").strip().lower()
        if st in {"failed", "skipped"}:
            continue
        oid = str(t.get("order_id") or "").strip()
        if not oid:
            continue
        try:
            qty = float(t.get("quantity") or 0)
        except Exception:
            qty = 0.0
        result = upsert_broker_order(
            db,
            portfolio_account_id=int(portfolio_account_id),
            order_id=oid,
            figi=str(t.get("figi") or ""),
            side=str(t.get("side") or "buy"),
            quantity=qty,
            status=str(t.get("execution_status") or t.get("status") or STATUS_PENDING),
            price=float(t.get("price") or 0) or None,
            filled_qty=t.get("filled_quantity"),
            avg_price=t.get("avg_fill_price"),
            source=SOURCE_ROBOT,
            robot_id=int(robot_id),
            reason=t.get("reason"),
            intent_source=t.get("intent_source") or t.get("intent_kind"),
            commit=False,
            promote_filled=True,
            broker_prefix=broker_prefix,
        )
        if result in {"inserted", "updated"}:
            n += 1
    if n:
        try:
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("insert_robot_orders_batch commit failed: %s", exc)
            return 0
    return n
