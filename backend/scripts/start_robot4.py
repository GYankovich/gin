"""Start robot 4 without stopping first."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.modules.robots_v2.engine.session_manager import session_manager


def _token(db) -> str:
    token, exp = create_access_token({"sub": "1"}, expires_delta=timedelta(hours=2))
    db.execute(
        text(
            "INSERT INTO user_token (user_id, token, status, created_at, expires_at) "
            "VALUES (1,:t,1,:c,:e)"
        ),
        {"t": token, "c": datetime.now(timezone.utc), "e": exp},
    )
    db.commit()
    return token


async def main() -> None:
    snap = session_manager.status(4)
    if snap is not None:
        print("already running:", snap.session_state.value)
        return

    db = SessionLocal()
    try:
        token = _token(db)
    finally:
        db.close()

    h = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "http://127.0.0.1:8000/api/v2/robots/4/start",
            headers=h,
            json={"stopMode": "soft"},
        )
        print("start", r.status_code, r.text[:300])
        await asyncio.sleep(10)
        st = await c.get("http://127.0.0.1:8000/api/v2/robots/4/status", headers=h)
        d = st.json()
        print(json.dumps({
            "sessionState": d.get("sessionState"),
            "cash": d.get("cash"),
            "equity": d.get("equity"),
            "universe": d.get("universe"),
            "positions": d.get("openPositions"),
            "message": d.get("message"),
        }, ensure_ascii=True, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
