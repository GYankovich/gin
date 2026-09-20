"""Heal policy for standalone lane workers spawned by `run.py all`."""

from __future__ import annotations

WORKER_EXIT_LEASE_CONFLICT = 2
WORKER_EXIT_LEASE_LOST = 3


def plan_worker_heal(
    *,
    exit_code: int,
    newly_exited: bool,
    now: float,
    next_restart_at: float,
    force_lease: bool,
    conflict_backoff_sec: float = 95.0,
    restart_backoff_sec: float = 3.0,
) -> tuple[float, bool, bool]:
    """Decide when to respawn a dead lane worker.

    Returns (next_restart_at, force_lease, should_spawn).

    Lease conflict (exit 2) waits until the previous heartbeat is stale, but
    only on the first observation — postponing every poll would delay forever.
    Lease lost (exit 3) restarts quickly with --force-lease.
    """
    nxt = float(next_restart_at)
    force = bool(force_lease)
    if newly_exited and int(exit_code) == WORKER_EXIT_LEASE_CONFLICT:
        force = True
        nxt = max(nxt, now + float(conflict_backoff_sec))
    elif newly_exited and int(exit_code) == WORKER_EXIT_LEASE_LOST:
        force = True
        nxt = max(nxt, now + float(restart_backoff_sec))
    should_spawn = now >= nxt
    return nxt, force, should_spawn
