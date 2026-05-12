"""
WebSocket endpoint for live robot monitoring.
Proxies T-Invest price stream to the frontend for a given robot.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsLiveWs [1]
#/// Исходный модуль `backend/app/modules/robots/live_ws.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import decode_token
from app.core.logging_config import get_logger
from app.modules.robots.live_hub import live_event_hub
from app.modules.robots.trading.brokers.factory import create_broker_facade

logger = get_logger("live_ws")

router = APIRouter()


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
                SELECT r.id, r.config, t.token, r.type, r.status
                FROM {schema}.robots r
                JOIN {schema}.api_tokens t ON r.token_id = t.id
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
        }
    finally:
        db.close()


def _authenticate_ws(token_str: str) -> Optional[int]:
    """Return user_id from bearer token or None."""
    payload = decode_token(token_str)
    if not payload:
        return None
    sub = payload.get("sub")
    return int(sub) if sub else None


@router.websocket("/ws/live")
async def live_websocket(
    ws: WebSocket,
    robot_id: int = Query(...),
    token: str = Query(""),
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
    figis = (
        config.get("figis")
        or config.get("allowed_figis")
        or config.get("strategy_params", {}).get("figis")
        or []
    )

    if not figis:
        await ws.send_json({
            "type": "error",
            "message": "Robot has no instruments configured. Add FIGIs in robot settings → Instruments tab.",
        })
        await ws.close(code=4005)
        return

    broker_type = config.get("broker_type", "tinvest")
    await ws.send_json({"type": "init", "figis": figis, "robot_id": robot_id, "broker_type": broker_type})
    broker = create_broker_facade(broker_type, robot["token"])
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    event_queue = await live_event_hub.subscribe(robot_id)
    outbound_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    try:
        connected = await broker.connect_websocket(user_id)
        if not connected:
            raise RuntimeError("WebSocket connection failed")
        await broker.subscribe_prices(user_id, figis, queue)
    except Exception as e:
        logger.error("Broker WS connect failed: %s", e)
        await ws.send_json({"type": "error", "message": f"Broker WS error: {e}"})
        await ws.close(code=4010)
        return

    async def relay_prices():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.05)
                continue
            if data and data.get("type") == "price":
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "price",
                    "figi": data.get("figi"),
                    "price": round(float(data.get("price", 0.0)), 6),
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
            figi = payload.get("figi")
            if action == "subscribe" and figi:
                await broker.subscribe_prices(user_id, [figi], queue)
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "log",
                    "level": "INFO",
                    "message": f"Subscribed to {figi}",
                    "time": datetime.now(timezone.utc).isoformat(),
                })
            elif action == "unsubscribe" and figi:
                await broker.unsubscribe_prices(user_id, [figi], queue)
                _put_nowait_drop_oldest(outbound_queue, {
                    "type": "log",
                    "level": "INFO",
                    "message": f"Unsubscribed from {figi}",
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
        await live_event_hub.unsubscribe(robot_id, event_queue)
        await broker.close_websocket(user_id, queue=queue)
        await broker.close()
