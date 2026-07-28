"""Live event bus: Postgres NOTIFY + DB fetch, or in-memory fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import select
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.live_hub import live_event_hub

logger = logging.getLogger(__name__)

LIVE_EVENT_TYPES = frozenset({"signal", "order", "log", "skipped", "error"})

# Inline NOTIFY payloads (no DB row) — used to fan-out session market ticks to Live UI.
INLINE_LIVE_PAYLOAD_TYPES = frozenset({"price", "prices", "error", "orders_refresh"})


def uses_postgres_live_events() -> bool:
    return str(getattr(settings, "LIVE_EVENTS_BACKEND", "postgres") or "postgres").strip().lower() == "postgres"


def live_robot_channel(robot_id: int) -> str:
    return f"live_robot_{int(robot_id)}"


def _pg_connect():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=int(settings.DB_PORT),
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        sslmode=settings.DB_SSL_MODE,
        connect_timeout=int(settings.DB_CONNECT_TIMEOUT_SECONDS),
    )


# One long-lived Autocommit connection per process for pg_notify.
# Opening a fresh TCP socket on every price tick (~3 Hz) exhausts Postgres
# max_connections (FATAL: remaining connection slots are reserved for SUPERUSER).
_notify_lock = threading.Lock()
_notify_conn = None


def _pg_notify(channel: str, payload: str) -> None:
    """Reuse a single psycopg2 connection for NOTIFY (thread-safe)."""
    global _notify_conn
    with _notify_lock:
        last_exc: Optional[BaseException] = None
        for _attempt in range(2):
            try:
                if _notify_conn is None or getattr(_notify_conn, "closed", 1):
                    _notify_conn = _pg_connect()
                    _notify_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = _notify_conn.cursor()
                try:
                    cur.execute("SELECT pg_notify(%s, %s)", (channel, payload))
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
                return
            except Exception as exc:
                last_exc = exc
                try:
                    if _notify_conn is not None:
                        _notify_conn.close()
                except Exception:
                    pass
                _notify_conn = None
        if last_exc is not None:
            raise last_exc


def notify_robot_live_event(db: Session, robot_id: int, event_type: str, row_id: int) -> None:
    """SELECT pg_notify + commit — NOTIFY уходит только после COMMIT."""
    if not uses_postgres_live_events():
        return
    channel = live_robot_channel(robot_id)
    payload = json.dumps({"type": str(event_type), "id": int(row_id)}, ensure_ascii=False)
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": channel, "payload": payload},
    )
    db.commit()


def insert_session_log(
    db: Session,
    *,
    robot_id: int,
    message: str,
    level: str = "INFO",
    execution_log_id: Optional[int] = None,
) -> Optional[int]:
    schema = settings.DB_SCHEMA
    row = db.execute(
        text(
            f"""
            INSERT INTO {schema}.robot_session_logs
                (robot_id, execution_log_id, level, message, created_at)
            VALUES
                (:robot_id, :execution_log_id, :level, :message, :now)
            RETURNING id
            """
        ),
        {
            "robot_id": int(robot_id),
            "execution_log_id": execution_log_id,
            "level": str(level or "INFO")[:16],
            "message": str(message or "")[:8000],
            "now": datetime.now(timezone.utc),
        },
    ).first()
    if not row:
        return None
    log_id = int(row[0])
    # Один commit: INSERT + NOTIFY (иначе LISTEN на API не получает log-события).
    notify_robot_live_event(db, robot_id, "log", log_id)
    return log_id


def fetch_recent_session_logs(
    db: Session,
    robot_id: int,
    *,
    limit: int = 150,
) -> List[Dict[str, Any]]:
    schema = settings.DB_SCHEMA
    lim = max(1, min(int(limit or 150), 500))
    rows = db.execute(
        text(
            f"""
            SELECT id, level, message, created_at
            FROM {schema}.robot_session_logs
            WHERE robot_id = :robot_id
            ORDER BY id DESC
            LIMIT :lim
            """
        ),
        {"robot_id": int(robot_id), "lim": lim},
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in reversed(rows):
        created = row[3]
        out.append(
            {
                "type": "log",
                "robot_id": int(robot_id),
                "id": int(row[0]),
                "level": row[1] or "INFO",
                "message": row[2] or "",
                "time": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
            }
        )
    return out


def fetch_live_event_payload(db: Session, robot_id: int, ref: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map DB row to WebSocket JSON (same contract as live_event_hub)."""
    schema = settings.DB_SCHEMA
    event_type = str(ref.get("type") or "").strip().lower()
    row_id = ref.get("id")
    if not event_type or row_id is None:
        return None
    try:
        row_id = int(row_id)
    except (TypeError, ValueError):
        return None

    if event_type == "log":
        row = db.execute(
            text(
                f"""
                SELECT id, robot_id, level, message, created_at
                FROM {schema}.robot_session_logs
                WHERE id = :id AND robot_id = :robot_id
                """
            ),
            {"id": row_id, "robot_id": int(robot_id)},
        ).first()
        if not row:
            return None
        created = row[4]
        return {
            "type": "log",
            "id": int(row[0]),
            "robot_id": int(row[1]),
            "level": row[2] or "INFO",
            "message": row[3] or "",
            "time": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
        }

    if event_type == "signal":
        row = db.execute(
            text(
                f"""
                SELECT id, robot_id, figi, signal_type, signal_strength,
                       price_at_signal, indicators, created_at
                FROM {schema}.robot_signals
                WHERE id = :id AND robot_id = :robot_id
                """
            ),
            {"id": row_id, "robot_id": int(robot_id)},
        ).first()
        if not row:
            return None
        indicators = row[6] if isinstance(row[6], dict) else {}
        price = float(row[5]) if row[5] is not None else None
        created = row[7]
        return {
            "type": "signal",
            "id": int(row[0]),
            "robot_id": int(row[1]),
            "figi": row[2],
            "signal_type": str(row[3] or "").lower(),
            "price": price,
            "target_price": indicators.get("target_price") if isinstance(indicators, dict) else None,
            "indicators": indicators if isinstance(indicators, dict) else {},
            "time": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
        }

    if event_type in {"order", "skipped"}:
        row = db.execute(
            text(
                f"""
                SELECT e.id, e.robot_id, e.order_id, e.status, e.event_type, e.payload, e.created_at,
                       e.trade_id, t.figi, t.side, t.quantity, t.price
                FROM {schema}.robot_order_events e
                LEFT JOIN {schema}.robot_trades t ON t.id = e.trade_id
                WHERE e.id = :id AND e.robot_id = :robot_id
                """
            ),
            {"id": row_id, "robot_id": int(robot_id)},
        ).first()
        if not row:
            return None
        payload = row[5] if isinstance(row[5], dict) else {}
        created = row[6]
        status = str(row[3] or payload.get("status") or "unknown")
        ws_type = "skipped" if status == "skipped" or event_type == "skipped" else "order"
        trade_id = row[7] if row[7] is not None else payload.get("trade_id")
        signal_id = payload.get("signal_id") if isinstance(payload, dict) else None
        qty = row[10]
        if qty is None and isinstance(payload, dict):
            qty = payload.get("quantity")
            if qty is None:
                qty = payload.get("lots_requested")
        return {
            "type": ws_type,
            "id": int(row[0]),
            "robot_id": int(row[1]),
            "figi": row[8] or payload.get("figi"),
            "side": row[9] or payload.get("side"),
            "quantity": qty,
            "price": float(row[11]) if row[11] is not None else payload.get("price"),
            "status": status,
            "order_id": row[2],
            "trade_id": int(trade_id) if trade_id is not None and str(trade_id).strip() != "" else None,
            "signal_id": int(signal_id) if signal_id is not None and str(signal_id).strip() != "" else None,
            "reason": payload.get("error") or payload.get("reason"),
            "time": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
        }

    return None


async def publish_live_event(robot_id: int, payload: Dict[str, Any]) -> None:
    """Publish to in-memory hub (single-process / memory backend)."""
    if uses_postgres_live_events():
        return
    await live_event_hub.publish(int(robot_id), payload)


def notify_live_prices(
    robot_id: int,
    items: List[Dict[str, Any]],
    *,
    time_iso: Optional[str] = None,
) -> None:
    """Fan-out market ticks from the trading session to Live UI (same stream).

    Uses PG NOTIFY with an inline payload (no DB insert) so the WS gateway can
    relay prices without opening a second broker WebSocket.
    """
    cleaned: List[Dict[str, Any]] = []
    for it in items or []:
        figi = str((it or {}).get("figi") or "").strip().upper()
        try:
            price = float((it or {}).get("price"))
        except Exception:
            continue
        if not figi or not (price == price):  # NaN guard
            continue
        cleaned.append({"figi": figi, "price": price})
    if not cleaned:
        return

    ts = time_iso or datetime.now(timezone.utc).isoformat()
    robot_id = int(robot_id)
    if len(cleaned) == 1:
        payload: Dict[str, Any] = {
            "type": "price",
            "figi": cleaned[0]["figi"],
            "price": cleaned[0]["price"],
            "time": ts,
            "source": "session",
            "robot_id": robot_id,
        }
    else:
        payload = {
            "type": "prices",
            "items": cleaned,
            "time": ts,
            "source": "session",
            "robot_id": robot_id,
        }

    if uses_postgres_live_events():
        channel = live_robot_channel(robot_id)
        raw = json.dumps(payload, ensure_ascii=False)
        try:
            _pg_notify(channel, raw)
        except Exception as exc:
            logger.warning("notify_live_prices failed robot_id=%s: %s", robot_id, exc)
        return

    # Memory backend (same process only): expand to per-symbol price events.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for item in cleaned:
        loop.create_task(
            live_event_hub.publish(
                robot_id,
                {
                    "type": "price",
                    "figi": item["figi"],
                    "price": item["price"],
                    "time": ts,
                    "source": "session",
                    "robot_id": robot_id,
                },
            )
        )


def expand_inline_live_payload(robot_id: int, ref: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert inline NOTIFY price payload(s) into UI price events."""
    et = str(ref.get("type") or "").strip().lower()
    ts = ref.get("time") or datetime.now(timezone.utc).isoformat()
    rid = int(ref.get("robot_id") or robot_id)
    if et == "price":
        figi = str(ref.get("figi") or "").strip().upper()
        try:
            price = float(ref.get("price"))
        except Exception:
            return []
        if not figi:
            return []
        return [{
            "type": "price",
            "figi": figi,
            "price": price,
            "time": ts,
            "source": str(ref.get("source") or "session"),
            "robot_id": rid,
        }]
    if et == "prices":
        out: List[Dict[str, Any]] = []
        for it in list(ref.get("items") or []):
            figi = str((it or {}).get("figi") or "").strip().upper()
            try:
                price = float((it or {}).get("price"))
            except Exception:
                continue
            if not figi:
                continue
            out.append({
                "type": "price",
                "figi": figi,
                "price": price,
                "time": ts,
                "source": str(ref.get("source") or "session"),
                "robot_id": rid,
            })
        return out
    if et == "error":
        message = str(ref.get("message") or "").strip()
        if not message:
            return []
        return [{
            "type": "error",
            "message": message,
            "robot_id": rid,
            "time": ts,
            "source": str(ref.get("source") or "session"),
        }]
    return []


def notify_live_alert(
    robot_id: int,
    message: str,
    *,
    time_iso: Optional[str] = None,
) -> None:
    """Fan-out a trading alert (HALT etc.) to Live UI as type=error."""
    text = str(message or "").strip()
    if not text:
        return
    ts = time_iso or datetime.now(timezone.utc).isoformat()
    robot_id = int(robot_id)
    payload: Dict[str, Any] = {
        "type": "error",
        "message": text[:4000],
        "time": ts,
        "source": "session",
        "robot_id": robot_id,
    }

    if uses_postgres_live_events():
        channel = live_robot_channel(robot_id)
        raw = json.dumps(payload, ensure_ascii=False)
        try:
            _pg_notify(channel, raw)
        except Exception as exc:
            logger.warning("notify_live_alert failed robot_id=%s: %s", robot_id, exc)
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(live_event_hub.publish(robot_id, payload))


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    return value


def _resolve_robot_user_account(
    db: Session,
    robot_id: int,
    *,
    user_id: Optional[int] = None,
    account_id: Optional[str] = None,
) -> tuple[Optional[int], Optional[str]]:
    uid = int(user_id) if user_id is not None else None
    acc = str(account_id).strip() if account_id else None
    if uid is not None and acc:
        return uid, acc
    row = db.execute(
        text(
            f"""
            SELECT user_id, NULLIF(TRIM(config->>'account_id'), '')
            FROM {settings.DB_SCHEMA}.robots
            WHERE id = :robot_id
            """
        ),
        {"robot_id": int(robot_id)},
    ).first()
    if not row:
        return uid, acc
    if uid is None and row[0] is not None:
        uid = int(row[0])
    if not acc and row[1]:
        acc = str(row[1]).strip()
    return uid, acc


def build_orders_snapshot_payload(
    db: Session,
    *,
    robot_id: int,
    user_id: Optional[int] = None,
    account_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Load open/history orders for Live UI (same source as REST snapshot)."""
    from app.modules.robots.service import _load_live_account_orders, _split_db_orders

    uid, acc = _resolve_robot_user_account(
        db, int(robot_id), user_id=user_id, account_id=account_id,
    )
    if uid is None or not acc:
        return {
            "type": "orders_snapshot",
            "robot_id": int(robot_id),
            "open_orders": [],
            "order_history": [],
            "orders_synced_at": None,
            "time": datetime.now(timezone.utc).isoformat(),
        }
    recent = _load_live_account_orders(db, user_id=int(uid), broker_account_id=str(acc))
    open_orders, order_history = _split_db_orders(recent)
    return _json_safe_value({
        "type": "orders_snapshot",
        "robot_id": int(robot_id),
        "open_orders": open_orders,
        "order_history": order_history,
        "orders_synced_at": datetime.now(timezone.utc).isoformat(),
        "time": datetime.now(timezone.utc).isoformat(),
    })


def notify_live_orders_refresh(
    robot_id: int,
    *,
    user_id: Optional[int] = None,
    account_id: Optional[str] = None,
) -> None:
    """Lightweight hint: LISTEN thread loads portfolio_orders → orders_snapshot.

    Avoids stuffing full order lists into pg_notify (8KB limit).
    """
    robot_id = int(robot_id)
    payload: Dict[str, Any] = {
        "type": "orders_refresh",
        "robot_id": robot_id,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    if user_id is not None:
        payload["user_id"] = int(user_id)
    if account_id:
        payload["account_id"] = str(account_id).strip()

    if uses_postgres_live_events():
        channel = live_robot_channel(robot_id)
        raw = json.dumps(payload, ensure_ascii=False)
        try:
            _pg_notify(channel, raw)
        except Exception as exc:
            logger.warning("notify_live_orders_refresh failed robot_id=%s: %s", robot_id, exc)
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _async_publish() -> None:
        db = None
        try:
            from app.core.database import SessionLocal

            db = SessionLocal()
            snap = build_orders_snapshot_payload(
                db,
                robot_id=robot_id,
                user_id=user_id,
                account_id=account_id,
            )
            if snap:
                await live_event_hub.publish(robot_id, snap)
        except Exception as exc:
            logger.warning("memory orders_snapshot failed robot_id=%s: %s", robot_id, exc)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    loop.create_task(_async_publish())


class PgLiveEventSubscriber:
    """LISTEN on live_robot_{id} in a background thread; fanout to asyncio queues."""

    def __init__(self) -> None:
        self._queues: Dict[int, List[asyncio.Queue]] = defaultdict(list)
        self._threads: Dict[int, threading.Thread] = {}
        self._stop_flags: Dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def subscribe(self, robot_id: int) -> asyncio.Queue:
        robot_id = int(robot_id)
        loop = asyncio.get_running_loop()
        self._loop = loop
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._queues[robot_id].append(queue)
            if robot_id not in self._threads or not self._threads[robot_id].is_alive():
                stop = threading.Event()
                self._stop_flags[robot_id] = stop
                thread = threading.Thread(
                    target=self._listen_loop,
                    args=(robot_id, stop),
                    name=f"pg-live-listen-{robot_id}",
                    daemon=True,
                )
                self._threads[robot_id] = thread
                thread.start()
        return queue

    async def unsubscribe(self, robot_id: int, queue: asyncio.Queue) -> None:
        robot_id = int(robot_id)
        with self._lock:
            qs = self._queues.get(robot_id, [])
            if queue in qs:
                qs.remove(queue)
            if not qs:
                stop = self._stop_flags.pop(robot_id, None)
                if stop:
                    stop.set()
                self._threads.pop(robot_id, None)
                self._queues.pop(robot_id, None)

    def _dispatch(self, robot_id: int, event: Dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            targets = list(self._queues.get(robot_id, []))

        def _put_all() -> None:
            for q in targets:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except Exception:
                        pass
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

        loop.call_soon_threadsafe(_put_all)

    def _listen_loop(self, robot_id: int, stop: threading.Event) -> None:
        """LISTEN with reconnect: SSL/idle drops must not kill the subscriber thread."""
        channel = live_robot_channel(robot_id)
        backoff_sec = 1.0
        max_backoff_sec = 30.0

        while not stop.is_set():
            conn = None
            try:
                conn = _pg_connect()
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = conn.cursor()
                cur.execute(f"LISTEN {channel}")
                logger.info("PG LISTEN started channel=%s", channel)
                backoff_sec = 1.0

                while not stop.is_set():
                    if select.select([conn], [], [], 1.0) == ([], [], []):
                        continue
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        try:
                            ref = json.loads(notify.payload)
                        except Exception:
                            continue
                        if not isinstance(ref, dict):
                            continue
                        inline_type = str(ref.get("type") or "").strip().lower()
                        if inline_type == "orders_refresh":
                            db = None
                            try:
                                from app.core.database import SessionLocal

                                db = SessionLocal()
                                snap = build_orders_snapshot_payload(
                                    db,
                                    robot_id=robot_id,
                                    user_id=ref.get("user_id"),
                                    account_id=ref.get("account_id"),
                                )
                                if snap:
                                    self._dispatch(robot_id, snap)
                            except Exception as exc:
                                logger.warning(
                                    "PG orders_refresh failed robot_id=%s: %s",
                                    robot_id,
                                    exc,
                                )
                            finally:
                                if db is not None:
                                    db.close()
                            continue
                        if inline_type in INLINE_LIVE_PAYLOAD_TYPES:
                            for event in expand_inline_live_payload(robot_id, ref):
                                self._dispatch(robot_id, event)
                            continue
                        db = None
                        try:
                            from app.core.database import SessionLocal

                            db = SessionLocal()
                            event = fetch_live_event_payload(db, robot_id, ref)
                            if event:
                                self._dispatch(robot_id, event)
                        except Exception as exc:
                            logger.warning(
                                "PG live fetch failed robot_id=%s ref=%s: %s",
                                robot_id,
                                ref,
                                exc,
                            )
                        finally:
                            if db is not None:
                                db.close()
            except Exception as exc:
                if stop.is_set():
                    break
                logger.error(
                    "PG LISTEN loop error robot_id=%s: %s — reconnect in %.1fs",
                    robot_id,
                    exc,
                    backoff_sec,
                )
                stop.wait(backoff_sec)
                backoff_sec = min(max_backoff_sec, backoff_sec * 2.0)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        logger.info("PG LISTEN stopped channel=%s", channel)


pg_live_subscriber = PgLiveEventSubscriber()


async def subscribe_live_events(robot_id: int) -> asyncio.Queue:
    if uses_postgres_live_events():
        return await pg_live_subscriber.subscribe(robot_id)
    return await live_event_hub.subscribe(robot_id)


async def unsubscribe_live_events(robot_id: int, queue: asyncio.Queue) -> None:
    if uses_postgres_live_events():
        await pg_live_subscriber.unsubscribe(robot_id, queue)
    else:
        await live_event_hub.unsubscribe(robot_id, queue)
