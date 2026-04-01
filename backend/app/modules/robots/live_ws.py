"""
WebSocket endpoint for live robot monitoring.
Proxies T-Invest price stream to the frontend for a given robot.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import decode_token
from app.core.logging_config import get_logger
from app.modules.tinvest.websocket.price_manager import PriceStreamManager

logger = get_logger("live_ws")

router = APIRouter()


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

    await ws.send_json({"type": "init", "figis": figis, "robot_id": robot_id})

    price_mgr = PriceStreamManager(robot["token"])
    try:
        await price_mgr.connect()
        await price_mgr.subscribe(figis)
    except Exception as e:
        logger.error("T-Invest WS connect failed: %s", e)
        await ws.send_json({"type": "error", "message": f"T-Invest WS error: {e}"})
        await ws.close(code=4010)
        return

    async def relay_prices():
        while True:
            data = await price_mgr.receive_once(timeout=1.0)
            if data is None:
                await asyncio.sleep(0.05)
                continue
            if "lastPrice" in data:
                lp = data["lastPrice"]
                figi = lp.get("figi")
                price_raw = lp.get("price", {})
                units = int(price_raw.get("units", 0) or 0)
                nano = int(price_raw.get("nano", 0) or 0)
                price = units + nano / 1e9
                ts = lp.get("time", "")
                await ws.send_json({
                    "type": "price",
                    "figi": figi,
                    "price": round(price, 6),
                    "time": ts,
                })
            elif "ping" in data:
                pong_msg = {"pong": data["ping"]}
                if price_mgr.websocket:
                    await price_mgr.websocket.send(json.dumps(pong_msg))

    try:
        relay_task = asyncio.create_task(relay_prices())
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
                continue
    except WebSocketDisconnect:
        logger.info("Client disconnected from live WS, robot_id=%s", robot_id)
    except Exception as e:
        logger.error("Live WS error: %s", e)
    finally:
        relay_task.cancel()
        await price_mgr.close()
