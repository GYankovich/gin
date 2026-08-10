"""
WebSocket endpoint for live robot monitoring.

When a background trading session is running, attaches to that session's
Stage2 price fan-out (via live_events) instead of opening a second broker WS.
Falls back to a dedicated broker stream only if the robot is idle.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsLiveWs [1]
#/// Исходный модуль `backend/app/modules/robots/live_ws.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import resolve_session_user_id
from app.core.logging_config import get_logger
from app.modules.robots.service import robot_service
from app.modules.robots.live_events import (
    build_orders_snapshot_payload,
    fetch_recent_session_logs,
    subscribe_live_events,
    unsubscribe_live_events
)
from app.modules.robots.trading.brokers.factory import create_broker_facade

logger = get_logger("live_ws")

router = APIRouter()


def _trading_session_active(robot_id: int) -> bool:
    """True when heavy worker already runs live_trading_session for this robot."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT 1
                FROM background_jobs
                WHERE job_type = 'live_trading_session'
                  AND (payload->>'robot_id')::text = :robot_id
                  AND status IN ('queued', 'running')
                LIMIT 1
                """
            ),
            {"robot_id": str(int(robot_id))}
        ).first()
        return bool(row)
    except Exception as exc:
        logger.warning("trading_session_active check failed robot_id=%s: %s", robot_id, exc)
        return False
    finally:
        db.close()


def _normalize_instruments(config: dict) -> list[str]:
    cfg = config if isinstance(config, dict) else {}
    broker_type = str(cfg.get("broker_type") or "tinvest").strip().lower()
    if broker_type == "bybit":
        raw = cfg.get("allowed_symbols") or cfg.get("instruments") or []
    else:
        raw = cfg.get("figis") or cfg.get("allowed_figis") or cfg.get("strategy_params", {}).get("figis") or []
    return [str(x).strip().upper() for x in list(raw or []) if str(x).strip()]


def _resolve_live_ws_instruments(user_id: int, robot_id: int, config: dict) -> list[str]:
    """WS price stream = portfolio ∪ accepted screening (no full config dump)."""
    from datetime import date

    from app.modules.robots.service import _load_portfolio_positions_from_db

    cfg = config if isinstance(config, dict) else {}
    out: list[str] = []
    seen: set[str] = set()

    def _add(value) -> None:
        s = str(value or "").strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    account_id = str(cfg.get("account_id") or "").strip()
    broker_type = str(cfg.get("broker_type") or "").strip().lower()
    is_crypto = (
        broker_type == "bybit"
        or isinstance(cfg.get("bybit"), dict)
        or isinstance(cfg.get("crypto_universe"), dict)
    )
    im = cfg.get("instrument_map") if isinstance(cfg.get("instrument_map"), dict) else {}
    figi_by_ticker = im.get("figi_by_ticker") if isinstance(im.get("figi_by_ticker"), dict) else {}

    db = SessionLocal()
    try:
        if account_id:
            try:
                for pos in _load_portfolio_positions_from_db(db, int(user_id), account_id):
                    _add(pos.get("figi") or pos.get("ticker"))
            except Exception as exc:
                logger.warning(
                    "live_ws portfolio instruments failed robot_id=%s: %s",
                    robot_id,
                    exc
                )

        td = date.today()
        try:
            if is_crypto:
                rows = db.execute(
                    text(
                        f"""
                        SELECT symbol
                        FROM crypto_universe_daily
                        WHERE robot_id = :rid AND trade_date = :td
                          AND LOWER(COALESCE(filter_result, '')) IN ('accept', 'accepted')
                        ORDER BY created_at DESC
                        LIMIT 1000
                        """
                    ),
                    {"rid": int(robot_id), "td": td}
                ).fetchall()
                for r in rows:
                    _add(r[0])
            else:
                rows = db.execute(
                    text(
                        f"""
                        SELECT ticker
                        FROM daily_universe
                        WHERE robot_id = :rid AND trade_date = :td
                          AND LOWER(COALESCE(filter_result, '')) IN ('accept', 'accepted')
                        ORDER BY created_at DESC
                        LIMIT 1000
                        """
                    ),
                    {"rid": int(robot_id), "td": td}
                ).fetchall()
                for r in rows:
                    ticker = str(r[0] or "").strip().upper()
                    if not ticker:
                        continue
                    mapped = (
                        figi_by_ticker.get(ticker)
                        or figi_by_ticker.get(ticker.lower())
                        or figi_by_ticker.get(str(r[0]))
                    )
                    _add(mapped or ticker)
        except Exception as exc:
            logger.warning(
                "live_ws screening instruments failed robot_id=%s: %s",
                robot_id,
                exc
            )
    finally:
        db.close()

    # Never fall back to full allowed_symbols / config universe (hundreds of coins).
    return out


def _build_ws_init_payload(robot_id: int, broker_type: str, instruments: list[str]) -> dict:
    return {
        "type": "init",
        "robot_id": robot_id,
        "broker_type": broker_type,
        "instruments": list(instruments),
        # backward compatibility for old FE clients
        "figis": list(instruments),
    }


def _normalize_figis(payload: dict) -> list[str]:
    """Single figi or figis[] from client subscribe/unsubscribe message."""
    raw_list = payload.get("figis")
    if isinstance(raw_list, list):
        return [str(f).strip() for f in raw_list if f and str(f).strip()]
    figi = payload.get("figi")
    if figi and str(figi).strip():
        return [str(figi).strip()]
    return []


def _put_nowait_drop_oldest(queue: asyncio.Queue, item) -> None:
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except Exception:
        pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


def _get_robot_data(user_id: int, robot_id: int) -> Optional[dict]:
    """Fetch robot + token from DB synchronously (new session)."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT r.id, r.config, t.token, r.type, r.status, t.extra_data, t.token_type
                FROM robots r
                JOIN api_tokens t ON r.token_id = t.id
                WHERE r.id = :robot_id AND r.user_id = :user_id AND r.status != 0
            """.format(schema=settings.DB_SCHEMA)),
            {"robot_id": robot_id, "user_id": user_id}
        ).first()
        if not row:
            return None
        return {
            "id": row[0],
            "config": row[1] if row[1] else {},
            "token": str(row[2]),
            "type": int(row[3]),
            "status": int(row[4]),
            "token_extra_data": row[5] if isinstance(row[5], dict) else {},
            "token_type": int(row[6]) if row[6] is not None else None,
        }
    finally:
        db.close()


def _authenticate_ws(token_str: str) -> Optional[int]:
    """Return user_id from bearer token or None (session checked in DB, not JWT exp)."""
    db = SessionLocal()
    try:
        return resolve_session_user_id(db, token_str, slide=False)
    finally:
        db.close()


async def _autofill_figis_from_pipeline(user_id: int, robot_id: int) -> list[str]:
    """Try to populate allowed_figis from today's DMS universe."""
    db = SessionLocal()
    try:
        result = await robot_service.sync_live_universe_from_pipeline(
            db,
            robot_id=robot_id,
            user_id=user_id,
            force_refresh_snapshot=False
        )
        return list((result or {}).get("allowed_figis") or [])
    except Exception as ex:
        logger.warning("live_ws universe autofill failed robot_id=%s: %s", robot_id, ex)
        return []
    finally:
        db.close()


@router.websocket("/ws/live")
async def live_websocket(
    ws: WebSocket,
    robot_id: int = Query(...),
    token: str = Query("")
):
    await ws.accept()

    user_id = _authenticate_ws(token)
    if not user_id:
        await ws.send_json({"type": "error", "message": "Unauthorized"})
        await ws.close(code=4001)
        return

    robot = _get_robot_data(user_id, robot_id)
    if not robot:
        await ws.send_json({"type": "error", "message": "Robot not found"})
        await ws.close(code=4004)
        return

    if robot["type"] != 2:
        await ws.send_json({"type": "error", "message": "Robot is not a trading robot"})
        await ws.close(code=4003)
        return

    config = robot["config"] if isinstance(robot["config"], dict) else {}
    from app.modules.robots.trading.brokers.routing import (
        BrokerTokenMismatchError,
        enforce_broker_for_token
    )
    try:
        broker_type = enforce_broker_for_token(
            config,
            token_type=robot.get("token_type"),
            mutate=True,
            require_token=True
        )
    except (BrokerTokenMismatchError, ValueError) as exc:
        await ws.send_json({"type": "error", "message": str(exc)})
        await ws.close(code=4006)
        return

    figis = _resolve_live_ws_instruments(user_id, robot_id, config)

    # Empty is OK: Live still streams logs/orders; client may subscribe after portfolio/screening load.
    # Do NOT autofill allowed_symbols / full universe into the figi bar.

    await ws.send_json(_build_ws_init_payload(robot_id, broker_type, figis))
    try:
        seed_db = SessionLocal()
        try:
            for log_payload in fetch_recent_session_logs(seed_db, robot_id, limit=120):
                await ws.send_json(log_payload)
            orders_seed = build_orders_snapshot_payload(
                seed_db,
                robot_id=int(robot_id),
                user_id=int(user_id),
                account_id=str(config.get("account_id") or "").strip() or None
            )
            if orders_seed:
                await ws.send_json(orders_seed)
        finally:
            seed_db.close()
    except Exception as seed_exc:
        logger.warning("Failed to seed recent session logs robot_id=%s: %s", robot_id, seed_exc)

    # Prefer the background trading session's Stage2 price stream (fan-out via
    # live_events NOTIFY). Open a dedicated broker WS only when the robot is idle.
    attach_session_stream = _trading_session_active(robot_id)
    broker = None
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    event_queue = await subscribe_live_events(robot_id)
    outbound_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)

    if attach_session_stream:
        _put_nowait_drop_oldest(outbound_queue, {
            "type": "log",
            "level": "INFO",
            "message": (
                "Live monitor attached to background trading session price stream "
                "(no second broker WebSocket)."
            ),
            "time": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("live_ws robot_id=%s mode=session_fanout", robot_id)
    else:
        broker = create_broker_facade(
            broker_type,
            robot["token"],
            token_extra_data=robot.get("token_extra_data"),
            robot_config=config
        )
        try:
            connected = await broker.connect_websocket(user_id)
            if not connected:
                raise RuntimeError("WebSocket connection failed")
            await broker.subscribe_prices(user_id, figis, queue)
        except Exception as e:
            logger.error("Broker WS connect failed: %s", e)
            await ws.send_json({"type": "error", "message": f"Broker WS error: {e}"})
            await ws.close(code=4010)
            await unsubscribe_live_events(robot_id, event_queue)
            try:
                await broker.close()
            except Exception:
                pass
            return
        _put_nowait_drop_oldest(outbound_queue, {
            "type": "log",
            "level": "INFO",
            "message": (
                "Trading session idle — Live opened a dedicated broker WebSocket "
                "for prices (fallback)."
            ),
            "time": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("live_ws robot_id=%s mode=broker_fallback", robot_id)

    async def relay_prices():
        if attach_session_stream:
            # Prices arrive via event_queue (session fan-out). Keep task alive.
            while True:
                await asyncio.sleep(3600)
            return
        last_poll_ts = 0.0
        last_polled_prices: dict[str, float] = {}
        last_ws_price_ts: dict[str, float] = {}
        is_bybit = str(broker_type).strip().lower() == "bybit"
        poll_interval_sec = 5.0
        stale_after_sec = 12.0
        while True:
            now_ts = time.monotonic()
            should_poll = is_bybit and (now_ts - last_poll_ts >= poll_interval_sec)
            if should_poll:
                last_poll_ts = now_ts
                for figi in figis:
                    last_ws_ts = last_ws_price_ts.get(figi, 0.0)
                    if last_ws_ts > 0.0 and (now_ts - last_ws_ts) < stale_after_sec:
                        continue
                    try:
                        p = await broker.get_last_price(user_id, figi, force_refresh=True)
                    except Exception:
                        p = None
                    if p is None:
                        continue
                    rounded = round(float(p), 6)
                    if last_polled_prices.get(figi) == rounded:
                        continue
                    last_polled_prices[figi] = rounded
                    _put_nowait_drop_oldest(outbound_queue, {
                        "type": "price",
                        "figi": figi,
                        "price": rounded,
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
            try:
                data = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.05)
                continue
            if not data:
                continue
            event_type = str(data.get("type") or "").strip().lower()
            if event_type in {"price", "candle", "candle_closed"}:
                figi = str(data.get("figi") or "").strip().upper()
                if figi:
                    last_ws_price_ts[figi] = time.monotonic()
                raw_price = data.get("price")
                if raw_price is None:
                    candle = data.get("candle") if isinstance(data.get("candle"), dict) else {}
                    raw_price = candle.get("close")
                try:
                    price = float(raw_price)
                except Exception:
                    continue
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "price",
                    "figi": figi or data.get("figi"),
                    "price": round(price, 6),
                    "time": datetime.now(timezone.utc).isoformat(),
                })

    async def relay_events():
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.05)
                continue
            _put_nowait_drop_oldest(outbound_queue, event)

    async def writer():
        event_seq = 0
        while True:
            payload = await outbound_queue.get()
            if isinstance(payload, dict):
                event_seq += 1
                payload.setdefault("event_id", event_seq)
                payload.setdefault("run_id", None)
                payload.setdefault("cycle_id", None)
                payload.setdefault("decision_id", None)
            await ws.send_json(payload)

    relay_task = None
    event_task = None
    writer_task = None
    try:
        relay_task = asyncio.create_task(relay_prices())
        event_task = asyncio.create_task(relay_events())
        writer_task = asyncio.create_task(writer())
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                _put_nowait_drop_oldest(outbound_queue, {"type": "ping"})
                continue
            try:
                payload = json.loads(msg) if msg else {}
            except Exception:
                payload = {}
            action = payload.get("action")
            figis_batch = _normalize_figis(payload)
            if attach_session_stream:
                if action in {"subscribe", "unsubscribe"}:
                    _put_nowait_drop_oldest(outbound_queue, {
                        "type": "log",
                        "level": "INFO",
                        "message": (
                            f"Ignore {action}: prices come from the background session stream."
                        ),
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                continue
            if action == "subscribe" and figis_batch and broker is not None:
                await broker.subscribe_prices(user_id, figis_batch, queue)
                if len(figis_batch) == 1:
                    msg_txt = f"Subscribed to {figis_batch[0]}"
                else:
                    msg_txt = f"Subscribed to {len(figis_batch)} instruments"
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "log",
                    "level": "INFO",
                    "message": msg_txt,
                    "time": datetime.now(timezone.utc).isoformat(),
                })
            elif action == "unsubscribe" and figis_batch and broker is not None:
                await broker.unsubscribe_prices(user_id, figis_batch, queue)
                if len(figis_batch) == 1:
                    msg_txt = f"Unsubscribed from {figis_batch[0]}"
                else:
                    msg_txt = f"Unsubscribed from {len(figis_batch)} instruments"
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "log",
                    "level": "INFO",
                    "message": msg_txt,
                    "time": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        logger.info("Client disconnected from live WS, robot_id=%s", robot_id)
    except Exception as e:
        logger.error("Live WS error: %s", e)
    finally:
        if relay_task:
            relay_task.cancel()
        if event_task:
            event_task.cancel()
        if writer_task:
            writer_task.cancel()
        await unsubscribe_live_events(robot_id, event_queue)
        if broker is not None:
            try:
                await broker.close_websocket(user_id, queue=queue)
            except Exception:
                pass
            try:
                await broker.close()
            except Exception:
                pass
