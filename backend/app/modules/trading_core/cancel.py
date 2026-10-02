"""Cancel helpers for backtest runs (DB cancel_requested + optional in-proc flags)."""

from __future__ import annotations

from sqlalchemy import text

_cancel_flags: dict[int, bool] = {}


def signal_backtest_cancel(run_id: int) -> None:
    _cancel_flags[int(run_id)] = True


def clear_backtest_cancel(run_id: int) -> None:
    _cancel_flags.pop(int(run_id), None)


def is_backtest_cancelled(run_id: int) -> bool:
    """True if in-proc flag set or DB cancel_requested."""
    rid = int(run_id)
    if _cancel_flags.get(rid):
        return True
    try:
        from app.core.database import get_db_context

        with get_db_context() as db:
            val = db.execute(
                text("SELECT cancel_requested FROM backtest_runs WHERE id = :rid LIMIT 1"),
                {"rid": rid},
            ).scalar()
            if bool(val):
                _cancel_flags[rid] = True
                return True
    except Exception:
        pass
    return False
