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

LIVE_EVENT_TYPES = frozenset({"signal", "order", "log", "skipped"})


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


def notify_robot_live_event(db: Session, robot_id: int, event_type: str, row_id: int) -> None:
    """Fire NOTIFY after COMMIT on the same connection/session."""
    if not uses_postgres_live_events():
        return
    channel = live_robot_channel(robot_id)
    payload = json.dumps({"type": str(event_type), "id": int(row_id)}, ensure_ascii=False)
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": channel, "payload": payload},
    )


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
    db.commit()
    notify_robot_live_event(db, robot_id, "log", log_id)
    return log_id


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
                       t.figi, t.side, t.quantity, t.price
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
        return {
            "type": ws_type,
            "robot_id": int(row[1]),
            "figi": row[7] or payload.get("figi"),
            "side": row[8] or payload.get("side"),
            "quantity": row[9] or payload.get("quantity"),
            "price": float(row[10]) if row[10] is not None else payload.get("price"),
            "status": status,
            "order_id": row[2],
            "reason": payload.get("error") or payload.get("reason"),
            "time": created.isoformat() if created else datetime.now(timezone.utc).isoformat(),
        }

    return None


async def publish_live_event(robot_id: int, payload: Dict[str, Any]) -> None:
    """Publish to in-memory hub (single-process / memory backend)."""
    if uses_postgres_live_events():
        return
    await live_event_hub.publish(int(robot_id), payload)


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
        channel = live_robot_channel(robot_id)
        conn = None
        try:
            conn = _pg_connect()
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f"LISTEN {channel}")
            logger.info("PG LISTEN started channel=%s", channel)
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
                    db = None
                    try:
                        from app.core.database import SessionLocal

                        db = SessionLocal()
                        event = fetch_live_event_payload(db, robot_id, ref)
                        if event:
                            self._dispatch(robot_id, event)
                    except Exception as exc:
                        logger.warning("PG live fetch failed robot_id=%s ref=%s: %s", robot_id, ref, exc)
                    finally:
                        if db is not None:
                            db.close()
        except Exception as exc:
            logger.error("PG LISTEN loop error robot_id=%s: %s", robot_id, exc)
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
