"""Lane worker supervisor heal policy and standalone wait-loop."""

from __future__ import annotations

import asyncio

from app.core.background_jobs.supervisor import plan_worker_heal
from app.core.background_jobs.worker import LaneWorkerPool, run_standalone_lane_worker
from app.core.background_jobs.worker_lease import WorkerLeaseLostError


def test_plan_worker_heal_conflict_backoff_only_once():
    nxt, force, spawn = plan_worker_heal(
        exit_code=2,
        newly_exited=True,
        now=100.0,
        next_restart_at=0.0,
        force_lease=False,
        conflict_backoff_sec=95.0,
        restart_backoff_sec=3.0,
    )
    assert force is True
    assert spawn is False
    assert nxt == 195.0

    nxt2, force2, spawn2 = plan_worker_heal(
        exit_code=2,
        newly_exited=False,
        now=101.0,
        next_restart_at=nxt,
        force_lease=force,
        conflict_backoff_sec=95.0,
        restart_backoff_sec=3.0,
    )
    assert force2 is True
    assert spawn2 is False
    assert nxt2 == 195.0

    nxt3, force3, spawn3 = plan_worker_heal(
        exit_code=2,
        newly_exited=False,
        now=195.0,
        next_restart_at=nxt2,
        force_lease=force2,
        conflict_backoff_sec=95.0,
        restart_backoff_sec=3.0,
    )
    assert force3 is True
    assert spawn3 is True
    assert nxt3 == 195.0


def test_plan_worker_heal_lease_lost_restarts_quickly():
    nxt, force, spawn = plan_worker_heal(
        exit_code=3,
        newly_exited=True,
        now=10.0,
        next_restart_at=0.0,
        force_lease=False,
        conflict_backoff_sec=95.0,
        restart_backoff_sec=3.0,
    )
    assert force is True
    assert spawn is False
    assert nxt == 13.0

    _, _, spawn2 = plan_worker_heal(
        exit_code=3,
        newly_exited=False,
        now=13.0,
        next_restart_at=nxt,
        force_lease=force,
        conflict_backoff_sec=95.0,
        restart_backoff_sec=3.0,
    )
    assert spawn2 is True


def test_wait_while_running_exits_when_pool_stops():
    async def _run() -> None:
        pool = LaneWorkerPool("portfolio", 1)
        pool._running = True

        async def _stop_soon() -> None:
            await asyncio.sleep(0.05)
            pool._running = False

        await asyncio.gather(
            asyncio.wait_for(pool.wait_while_running(poll_seconds=0.02), timeout=1.0),
            _stop_soon(),
        )

    asyncio.run(_run())


def test_standalone_worker_raises_when_lease_lost(monkeypatch):
    async def _run() -> None:
        class FakePool:
            def __init__(self, lane, concurrency, *, force_lease=False):
                self.lane = lane
                self.lease_lost = True

            async def start(self):
                return None

            async def wait_while_running(self, *, poll_seconds=1.0):
                return None

            async def stop(self):
                return None

        monkeypatch.setattr(
            "app.core.background_jobs.worker.LaneWorkerPool",
            FakePool,
        )
        monkeypatch.setattr(
            "app.core.background_jobs.worker._lane_concurrency",
            lambda lane: 1,
        )
        try:
            await run_standalone_lane_worker("portfolio")
            raise AssertionError("expected WorkerLeaseLostError")
        except WorkerLeaseLostError as exc:
            assert exc.lane == "portfolio"

    asyncio.run(_run())
