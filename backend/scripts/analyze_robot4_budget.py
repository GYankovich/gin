"""Where did robot 4 budget go? Fills, orders, round-trips."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.modules.robots_v2.audit_pnl import build_round_trips
from app.modules.robots_v2.service import robots_v2_service

schema = settings.DB_SCHEMA or "public"


def main() -> None:
    db = SessionLocal()
    try:
        fills = db.execute(
            text(f"""
                SELECT f.ticker, f.side, f.quantity, f.price, f.commission,
                       f.pnl, f.filled_at, f.kind, f.order_id
                FROM {schema}.robots_v2_fills f
                JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
                JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
                JOIN {schema}.robots_v2_sessions s ON s.id = c.session_id
                WHERE s.robot_id = 4
                ORDER BY f.filled_at
            """),
        ).mappings().all()
        print(f"=== FILLS ({len(fills)}) ===")
        total_comm = 0.0
        total_pnl = 0.0
        for f in fills:
            comm = float(f.get("commission") or 0)
            pnl = float(f.get("pnl") or 0)
            total_comm += comm
            total_pnl += pnl
            print(
                f"{f['filled_at']} {f['ticker']:12} {f['side']:4} qty={f['quantity']} "
                f"@ {float(f['price'] or 0):.6g} comm={comm:.4f} pnl={pnl:.4f} kind={f.get('kind')}"
            )
        print(f"total_commission={total_comm:.4f} total_realized_pnl={total_pnl:.4f}")

        fee_rate = 0.0006
        est_fee = sum(float(f["quantity"]) * float(f["price"] or 0) * fee_rate for f in fills)
        print(f"estimated_bybit_fees={est_fee:.4f} est_total_loss={total_pnl - est_fee:.4f}")

        from collections import defaultdict

        by: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "fills": 0, "notional": 0.0})
        for f in fills:
            t = str(f["ticker"])
            by[t]["pnl"] += float(f.get("pnl") or 0)
            by[t]["fills"] += 1
            by[t]["notional"] += float(f["quantity"]) * float(f["price"] or 0)
        print("\n=== BY TICKER ===")
        for t, v in sorted(by.items(), key=lambda x: -x[1]["notional"]):
            print(
                f"{t}: fills={v['fills']} pnl={v['pnl']:.4f} "
                f"notional={v['notional']:.2f} est_fee={v['notional'] * fee_rate:.4f}"
            )

        orders = db.execute(
            text(f"""
                SELECT o.ticker, o.side, o.quantity, o.status, o.submitted_at, o.kind, o.reject_reason
                FROM {schema}.robots_v2_orders o
                JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
                JOIN {schema}.robots_v2_sessions s ON s.id = c.session_id
                WHERE s.robot_id = 4
                ORDER BY o.submitted_at DESC
                LIMIT 30
            """),
        ).mappings().all()
        print(f"\n=== ORDERS ({len(orders)}) ===")
        for o in orders:
            print(dict(o))

        # round trips via service audit
        token, exp = create_access_token({"sub": "1"}, expires_delta=timedelta(hours=2))
        db.execute(
            text(
                "INSERT INTO user_token (user_id, token, status, created_at, expires_at) "
                "VALUES (1,:t,1,:c,:e)"
            ),
            {"t": token, "c": datetime.now(timezone.utc), "e": exp},
        )
        db.commit()
    finally:
        db.close()

    asyncio.run(_print_status(token))


async def _print_status(token: str) -> None:
    async with httpx.AsyncClient(timeout=60) as c:
        h = {"Authorization": f"Bearer {token}"}
        st = await c.get("http://127.0.0.1:8000/api/v2/robots/4/status", headers=h)
        d = st.json()
        print("\n=== LIVE STATUS ===")
        print(json.dumps({
            "sessionState": d.get("sessionState"),
            "equity": d.get("equity"),
            "cash": d.get("cash"),
            "positions": d.get("openPositions"),
            "universe": d.get("universe"),
        }, ensure_ascii=True, indent=2, default=str))
        aud = await c.post(
            "http://127.0.0.1:8000/api/v2/robots/audit",
            headers=h,
            json={"robotId": 4, "limit": 100, "types": ["fills", "roundTrips"]},
        )
        if aud.status_code == 200:
            body = aud.json()
            rts = body.get("roundTrips") or body.get("round_trips") or []
            print(f"\n=== ROUND TRIPS ({len(rts) if isinstance(rts, list) else '?'}) ===")
            if isinstance(rts, list):
                for rt in rts[:20]:
                    print(rt)


if __name__ == "__main__":
    main()
