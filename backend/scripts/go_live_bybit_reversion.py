"""Switch robot 4 (or --robot-id) to Bybit live with 6 USDT budget.

  cd backend
  set PYTHONPATH=.
  python scripts/go_live_bybit_reversion.py --robot-id 4 --budget 6
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

DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "bybit_reversion_live_6usdt.json"


def _bearer(db, *, user_id: int) -> str:
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
    p.add_argument("--robot-id", type=int, default=4)
    p.add_argument("--budget", type=float, default=6.0)
    p.add_argument("--token-id", type=int, default=25)
    p.add_argument("--user-id", type=int, default=1)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--api", type=str, default="http://127.0.0.1:8000")
    p.add_argument(
        "--flatten-first",
        action="store_true",
        help="Start briefly, hard-stop to flatten broker positions, then start clean.",
    )
    p.add_argument("--no-start", action="store_true", help="Update config only; do not start session.")
    args = p.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    cfg["core"]["mode"] = "live"
    cfg["risk"]["capital"] = float(args.budget)
    cfg["risk"]["allocatedCapital"] = float(args.budget)
    cfg["risk"]["maxDailyLoss"] = max(0.5, round(float(args.budget) * 0.25, 2))

    db = SessionLocal()
    try:
        updated = robots_v2_service.create_or_update(
            db,
            args.user_id,
            RobotV2CreateRequest(
                id=int(args.robot_id),
                name="Bybit Reversion DOGE 6U LIVE",
                type=2,
                tokenId=int(args.token_id),
                config=cfg,
            ),
        )
        uni = cfg.get("universe") or {}
        uni_desc = uni.get("mode")
        if uni.get("fixedList"):
            uni_desc = f"{uni_desc}:{uni.get('fixedList')}"
        elif uni.get("screener"):
            uni_desc = f"{uni_desc}:{(uni.get('screener') or {}).get('preset')}"
        elif uni.get("index"):
            uni_desc = f"{uni_desc}:{uni.get('index')}"
        print(
            f"updated id={updated.id} mode={cfg['core']['mode']} "
            f"allocated={cfg['risk']['allocatedCapital']} universe={uni_desc}"
        )
        bearer = _bearer(db, user_id=args.user_id)
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {bearer}"}
    base = args.api.rstrip("/")

    async def _stop(client: httpx.AsyncClient, *, mode: str = "soft") -> None:
        r = await client.post(
            f"{base}/api/v2/robots/{args.robot_id}/stop",
            headers=headers,
            params={"stop_mode": mode},
        )
        print(f"stop({mode}) HTTP {r.status_code}")
        if r.status_code >= 400:
            print(r.text[:800])

    async def _start(client: httpx.AsyncClient) -> bool:
        r = await client.post(
            f"{base}/api/v2/robots/{args.robot_id}/start",
            headers=headers,
            json={"stopMode": "soft"},
        )
        print(f"start HTTP {r.status_code}")
        if r.status_code >= 400:
            print(r.text[:1500])
            return False
        return True

    async with httpx.AsyncClient(timeout=120.0) as client:
        await _stop(client, mode="soft")

        if args.flatten_first:
            if not await _start(client):
                return 1
            await asyncio.sleep(8)
            st = await client.get(f"{base}/api/v2/robots/{args.robot_id}/status", headers=headers)
            pos = (st.json() or {}).get("openPositions") or []
            print(f"pre-flatten positions={pos}")
            if pos:
                await _stop(client, mode="hard")
                await asyncio.sleep(5)
            else:
                await _stop(client, mode="soft")

        if args.no_start:
            print("config updated, session not started (--no-start)")
            return 0

        if not await _start(client):
            return 1

        await asyncio.sleep(3)
        st = await client.get(
            f"{base}/api/v2/robots/{args.robot_id}/status",
            headers=headers,
        )
        data = st.json()
        keep = {
            k: data.get(k)
            for k in (
                "sessionState",
                "mode",
                "equity",
                "cash",
                "universe",
                "cycleNumber",
                "lastError",
                "statusMessage",
                "message",
            )
        }
        print(json.dumps(keep, ensure_ascii=True, default=str))
        if str(data.get("sessionState") or "").upper() == "ERROR":
            return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
