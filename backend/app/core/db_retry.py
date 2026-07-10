from __future__ import annotations

import time
from typing import Callable, TypeVar

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.core.database import try_dispose_pool_on_connectivity_error

T = TypeVar("T")


def _rollback_quiet(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def run_db_with_retry(
    db: Session,
    fn: Callable[[], T],
    *,
    max_attempts: int = 1,
    delay_sec: float = 5.0,
    max_delay_sec: float = 60.0,
) -> T:
    """
    Retry callable on PG connectivity errors with exponential backoff.

    Used for backtest persist and reconcile when remote DB may be temporarily unreachable.
    """
    if max_attempts < 1:
        max_attempts = 1
    delay = max(0.0, float(delay_sec))
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except (OperationalError, InterfaceError) as exc:
            last_exc = exc
            _rollback_quiet(db)
            try_dispose_pool_on_connectivity_error(exc)
            if attempt + 1 >= max_attempts:
                raise
            if delay > 0:
                time.sleep(delay)
            delay = min(delay * 1.5 if delay > 0 else delay_sec, max_delay_sec)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_db_with_retry exhausted without result")


def run_db_read_with_retry(db: Session, fn: Callable[[], T]) -> T:
    """
    One retry after connectivity errors (server closed connection, reset, etc.).
    Used in long backtest loops where a single session may outlive PG idle limits.
    """
    return run_db_with_retry(db, fn, max_attempts=2, delay_sec=0.0)
