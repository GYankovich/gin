"""Quick status dump for a robots v2 instance."""
from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots_v2.engine.session_manager import session_manager
from app.modules.robots_v2.service import RobotsV2Service

ROBOT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
schema = settings.DB_SCHEMA or "public"


async def api_status(db, user_id: int) -> dict:
    svc = RobotsV2Service()
    return await svc.get_status(db, user_id, ROBOT_ID)


def main() -> None:
    snap = session_manager.status(ROBOT_ID)
    print("=== IN-MEMORY SESSION ===")
    if snap is None:
        print("No active session in RAM")
    else:
        d = {
            "session_state": snap.session_state.value,
            "mode": snap.mode,
            "cycle_number": snap.cycle_number,
            "equity": snap.equity,
            "cash": snap.cash,
            "cycle_stage": snap.cycle_stage,
            "cycle_progress": snap.cycle_progress,
            "cycle_skip_reason": snap.cycle_skip_reason,
            "last_triggered_by": snap.last_triggered_by,
            "bootstrap_ready": getattr(snap, "bootstrap_ready", None),
            "ws_healthy": snap.ws_healthy,
            "message": snap.message,
            "positions": len(snap.open_positions or []),
            "open_orders": len(getattr(snap, "open_orders", None) or []),
            "universe": len(snap.universe or []),
            "last_cycle_at": str(snap.last_cycle_at),
        }
        print(json.dumps(d, ensure_ascii=False, indent=2))
        if snap.open_positions:
            print("position tickers:", [p.get("ticker") for p in snap.open_positions[:10]])

    db = SessionLocal()
    try:
        robot = db.execute(
            text(
                f"SELECT id, name, status, token_id, user_id, config, metadata "
                f"FROM {schema}.robots_v2 WHERE id = :id"
            ),
            {"id": ROBOT_ID},
        ).fetchone()
        print("\n=== ROBOT DB ===")
        if robot:
            cfg = robot.config or {}
            core = cfg.get("core") or {}
            mode = core.get("mode")
            print(f"name={robot.name} status={robot.status} mode={mode} token_id={robot.token_id}")
            meta = robot.metadata or {}
            if isinstance(meta, dict):
                print(f"lastVirtualCapital={meta.get('lastVirtualCapital')} sessionStopMode={meta.get('sessionStopMode')}")
        else:
            print("Robot not found")
            return

        user_id = int(robot.user_id)
        api = asyncio.run(api_status(db, user_id))
        slim = dict(api)
        if slim.get("equityCurve"):
            slim["equityCurve"] = f"[{len(slim['equityCurve'])} points]"
        if slim.get("tickerScan"):
            slim["tickerScan"] = f"[{len(slim['tickerScan'])} items]"
        if slim.get("openPositions"):
            slim["openPositions"] = [
                {k: p.get(k) for k in ("ticker", "side", "quantity", "entry_price", "current_price")}
                for p in slim["openPositions"][:10]
            ]
        print("\n=== API /status (as Monitor sees) ===")
        print(json.dumps(slim, ensure_ascii=False, indent=2, default=str))

        sessions = db.execute(
            text(
                f"""
                SELECT id, mode, started_at, ended_at, stop_reason, virtual_capital, account_id
                FROM {schema}.robots_v2_sessions
                WHERE robot_id = :rid ORDER BY started_at DESC LIMIT 3
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print("\n=== LAST SESSIONS ===")
        for s in sessions:
            print(
                f"  {s.id} mode={s.mode} start={s.started_at} end={s.ended_at} "
                f"stop={s.stop_reason} cap={s.virtual_capital} acc={s.account_id}"
            )

        cycles = db.execute(
            text(
                f"""
                SELECT cycle_number, status, skip_reason, triggered_by, equity, started_at, finished_at
                FROM {schema}.robots_v2_cycles
                WHERE robot_id = :rid ORDER BY cycle_number DESC LIMIT 5
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print("\n=== LAST CYCLES ===")
        for c in cycles:
            print(
                f"  #{c.cycle_number} status={c.status} skip={c.skip_reason} by={c.triggered_by} "
                f"eq={c.equity} start={c.started_at} end={c.finished_at}"
            )

        logs = db.execute(
            text(
                f"""
                SELECT created_at, message FROM {schema}.robot_logs
                WHERE robot_id = :rid ORDER BY created_at DESC LIMIT 20
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print("\n=== LAST LOGS ===")
        for lg in logs:
            msg = (lg.message or "")[:140]
            print(f"  {lg.created_at} {msg}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
