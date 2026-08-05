#!/usr/bin/env python3
"""
Re-enqueue a stuck history-backtest run (status QUEUED).

Usage:
  set PYTHONPATH=backend
  python backend/scripts/requeue_backtest_run.py 142
"""
from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.background_jobs.repository import enqueue_background_job, find_background_job_for_backtest_run
from app.core.background_jobs.worker import LANE_HEAVY
from app.modules.robots import schemas
from app.modules.robots.router import _continue_history_backtest_async


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: requeue_backtest_run.py <run_id> [--sync]", file=sys.stderr)
        return 1

    run_id = int(sys.argv[1])
    sync = "--sync" in sys.argv[2:]

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT id, user_id, robot_id, status, config_snapshot, cancel_requested,
                       requested_from, requested_to, initial_capital
                FROM backtest_runs
                WHERE id = :rid
                """
            ),
            {"rid": run_id},
        ).mappings().first()
        if not row:
            print(f"run_id={run_id} not found")
            return 1

        st = str(row["status"] or "").upper()
        print(f"run_id={run_id} status={st} user_id={row['user_id']}")

        job = find_background_job_for_backtest_run(db, run_id)
        print("existing_job:", job)

        cfg = row["config_snapshot"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg or "{}")

        if sync:
            body = {
                "robot_id": row["robot_id"],
                "from_date": row["requested_from"],
                "to_date": row["requested_to"],
                "initial_capital": float(row["initial_capital"] or 10_000),
                "async_execution": True,
                "config": cfg,
            }
            print("running sync worker (_continue_history_backtest_async)...")
            asyncio.run(_continue_history_backtest_async(run_id, int(row["user_id"]), body))
            return 0

        if st not in ("QUEUED", "FAILED"):
            print(f"refuse: expected QUEUED/FAILED, got {st}")
            return 1

        if job and str(job.get("status")) in ("queued", "running"):
            print("job already active — wait for worker or restart backend with WORKER_EMBEDDED_ENABLED=true")
            return 0

        db.execute(
            text(
                f"""
                UPDATE backtest_runs
                SET status = 'QUEUED',
                    run_phase = 'queued',
                    finished_at = NULL,
                    error_message = NULL,
                    cancel_requested = false,
                    started_at = CURRENT_TIMESTAMP
                WHERE id = :rid
                """
            ),
            {"rid": run_id},
        )

        req = schemas.RobotHistoryBacktestRequest(
            robot_id=row["robot_id"],
            strategy=(cfg.get("strategy") or None) if row["robot_id"] is None else None,
            from_date=row["requested_from"],
            to_date=row["requested_to"],
            initial_capital=float(row["initial_capital"] or 10_000),
            async_execution=True,
            config=cfg,
        )
        job_id = enqueue_background_job(
            db,
            lane=LANE_HEAVY,
            job_type="history_backtest",
            payload={
                "run_id": run_id,
                "user_id": int(row["user_id"]),
                "body": req.model_dump(mode="json"),
            },
            idempotency_key=f"history_backtest:{run_id}:requeue",
        )
        db.commit()
        if not job_id:
            print("enqueue failed (duplicate active job?)")
            return 1
        print(f"requeued job_id={job_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
