"""Stop robot 4 session."""
from __future__ import annotations

import asyncio
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
    db = SessionLocal()
    try:
        token = _token(db)
    finally:
        db.close()

    h = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "http://127.0.0.1:8000/api/v2/robots/4/stop",
            headers=h,
            params={"stop_mode": "soft"},
        )
        print("stop", r.status_code, r.text[:400])
        st = await c.get("http://127.0.0.1:8000/api/v2/robots/4/status", headers=h)
        d = st.json()
        print("sessionState", d.get("sessionState"))
        print("cash", d.get("cash"))
        print("positions", d.get("openPositions"))


if __name__ == "__main__":
    asyncio.run(main())
