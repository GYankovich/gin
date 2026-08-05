#!/usr/bin/env python3
"""
Finish backtest persist from on-disk persist_checkpoint.json (after DB outage).

Usage:
  set PYTHONPATH=backend
  python backend/scripts/repersist_backtest_run.py 189
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots.service import robot_service
from app.modules.robots.trading.backtest.persist_checkpoint import (
    checkpoint_run_started_at,
    find_persist_checkpoint,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: repersist_backtest_run.py <run_id>", file=sys.stderr)
        return 1

    run_id = int(sys.argv[1])
    found = find_persist_checkpoint(run_id)
    if not found:
        print(f"run_id={run_id}: persist_checkpoint.json not found — re-run simulation required")
        return 1

    checkpoint, started_at = found
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"SELECT status FROM backtest_runs WHERE id = :rid"
            ),
            {"rid": run_id},
        ).mappings().first()
        if not row:
            print(f"run_id={run_id} not found in DB")
            return 1
        st = str(row.get("status") or "").upper()
        print(f"run_id={run_id} db_status={st} checkpoint_started_at={started_at.isoformat()}")

        terminal = robot_service.finish_from_persist_checkpoint(
            db,
            run_id,
            checkpoint,
            started_at or checkpoint_run_started_at(checkpoint),
        )
        print(f"done status={terminal}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
