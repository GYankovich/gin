"""
Standalone heavy-lane worker for v2 backtests (gin-compute).

Usage:
  python -m app.workers.compute
  python -m app.workers.compute --force-lease

Equivalent to: python backend/run.py worker --lane heavy
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="GIN Compute heavy-lane worker")
    parser.add_argument(
        "--force-lease",
        action="store_true",
        help="Steal existing worker lease for this lane if present",
    )
    args = parser.parse_args(argv)

    from app.core.background_jobs.supervisor import WORKER_EXIT_LEASE_LOST
    from app.core.background_jobs.worker import LANE_HEAVY, run_standalone_lane_worker
    from app.core.background_jobs.worker_lease import WorkerLeaseConflictError, WorkerLeaseLostError
    from app.core.logging_config import setup_logging

    setup_logging()
    print(f"\n[START] gin-compute worker lane={LANE_HEAVY}")
    if args.force_lease:
        print("[WARN] --force-lease: will steal existing lease if present")
    print("Press Ctrl+C to stop\n")
    try:
        asyncio.run(run_standalone_lane_worker(LANE_HEAVY, force_lease=args.force_lease))
    except WorkerLeaseConflictError as exc:
        print(f"\n[ERR] {exc}")
        print("Уже крутится другой heavy worker. Остановите его или добавьте --force-lease")
        sys.exit(2)
    except WorkerLeaseLostError as exc:
        print(f"\n[ERR] {exc}")
        sys.exit(WORKER_EXIT_LEASE_LOST)
    except KeyboardInterrupt:
        print("\n[STOP] Worker stopped")


if __name__ == "__main__":
    main()
