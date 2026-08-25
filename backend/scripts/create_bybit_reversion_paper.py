"""Create + start Bybit reversion paper robot with small virtual capital.

Starts the session on the running API (uvicorn) so the robot keeps trading
after this script exits.

  cd backend
  set PYTHONPATH=.
  python scripts/create_bybit_reversion_paper.py --capital 6 --token-id 25
"""

from __future__ import annotations

import argparse
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
from app.modules.robots_v2.schemas import RobotV2CreateRequest
from app.modules.robots_v2.service import robots_v2_service

DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "bybit_reversion_paper_6usdt.json"


def _issue_bearer(db, *, user_id: int) -> str:
    token, expires_at = create_access_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(hours=2),
    )
    db.execute(
        text(
            """
            INSERT INTO user_token (user_id, token, status, created_at, expires_at)
            VALUES (:user_id, :token, 1, :created_at, :expires_at)
            """
        ),
        {
            "user_id": user_id,
            "token": token,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
        },
    )
    db.commit()
    return token


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capital", type=float, default=6.0)
    p.add_argument("--token-id", type=int, default=25)
    p.add_argument("--user-id", type=int, default=1)
    p.add_argument("--name", type=str, default="Bybit Reversion 6U")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--api", type=str, default="http://127.0.0.1:8000")
    p.add_argument("--no-start", action="store_true")
    args = p.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    cfg["risk"]["capital"] = float(args.capital)
    cfg["risk"]["maxDailyLoss"] = max(0.5, round(float(args.capital) * 0.25, 2))

    db = SessionLocal()
    try:
        created = robots_v2_service.create_or_update(
            db,
            args.user_id,
            RobotV2CreateRequest(
                name=args.name[:50],
                type=2,
                tokenId=int(args.token_id),
                config=cfg,
            ),
        )
        print(f"created robot id={created.id} name={created.name!r} status={created.status}")
        print(f"  tokenId={created.token_id} archetype={cfg['strategy']['archetype']}")
        print(f"  universe={cfg['universe']['fixedList']} capital={cfg['risk']['capital']}")

        if args.no_start:
            return 0

        bearer = _issue_bearer(db, user_id=args.user_id)
        url = f"{args.api.rstrip('/')}/api/v2/robots/{created.id}/start"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {bearer}"},
                json={"virtualCapital": float(args.capital), "stopMode": "soft"},
            )
        print(f"start HTTP {resp.status_code}")
        if resp.status_code >= 400:
            print(resp.text[:1000])
            return 1
        body = resp.json()
        print(f"started status={body.get('status')} id={body.get('id')}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
