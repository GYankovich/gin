"""Enqueue quotas for v2 backtest compute lane (ARCH-05)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots_v2.backtest.persist import count_v2_runs_by_status


def assert_can_enqueue_backtest(
    db: Session,
    *,
    user_id: int,
    from_date: datetime,
    to_date: datetime,
    skip_user_limits: bool = False,
) -> None:
    span_days = max(0, (to_date.date() - from_date.date()).days) + 1
    max_span = int(settings.COMPUTE_MAX_SPAN_DAYS)
    if span_days > max_span:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "span_too_long",
                "message": f"Период {span_days} дн. превышает лимит {max_span}",
                "limit": max_span,
                "span_days": span_days,
            },
        )

    if skip_user_limits:
        return

    running = count_v2_runs_by_status(db, user_id=user_id, statuses=("RUNNING",))
    max_running = int(settings.COMPUTE_MAX_USER_RUNNING)
    if running >= max_running:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "quota_user_running",
                "message": f"Уже выполняется {running} прогон(ов); лимит {max_running}",
                "limit": max_running,
                "running": running,
            },
            headers={"Retry-After": "30"},
        )

    queued = count_v2_runs_by_status(db, user_id=user_id, statuses=("QUEUED",))
    max_queued = int(settings.COMPUTE_MAX_USER_QUEUED)
    if queued >= max_queued:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "quota_user_queued",
                "message": f"В очереди уже {queued} прогон(ов); лимит {max_queued}",
                "limit": max_queued,
                "queued": queued,
            },
            headers={"Retry-After": "60"},
        )


def assert_can_start_optimization_batch(
    *,
    from_date: datetime,
    to_date: datetime,
    variants_count: int,
) -> None:
    """Batch-level gates (span + size). Active-batch check stays in runner."""
    span_days = max(0, (to_date.date() - from_date.date()).days) + 1
    max_span = int(settings.COMPUTE_MAX_SPAN_DAYS)
    if span_days > max_span:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "span_too_long",
                "message": f"Период {span_days} дн. превышает лимит {max_span}",
                "limit": max_span,
                "span_days": span_days,
            },
        )
    max_items = int(settings.COMPUTE_BATCH_MAX_ITEMS)
    if variants_count > max_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "batch_too_large",
                "message": f"Сетка {variants_count} вариантов превышает лимит {max_items}",
                "limit": max_items,
                "variants": variants_count,
            },
        )
