"""Helpers: освобождение lease после завершения бэктеста."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def release_osengine_leases_for_run(
    db: Session,
    *,
    run_id: int,
    success: bool,
) -> None:
    """Пометить lease run в cooling (TTL). Ошибки глотаем — статус бэктеста важнее."""
    if not run_id:
        return
    try:
        from app.modules.osengine import get_osengine_facade

        stats = get_osengine_facade().release_backtest_leases(
            db, run_id=int(run_id), success=success
        )
        if stats.leases_touched:
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.warning(
                    "osengine lease release commit failed run_id=%s",
                    run_id,
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            "osengine lease release failed run_id=%s success=%s",
            run_id,
            success,
            exc_info=True,
        )


__all__ = ["release_osengine_leases_for_run"]
