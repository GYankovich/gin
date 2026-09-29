"""Thin compute facade over robots_v2 backtest + optimization batches (ARCH-05 C)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.background_jobs.repository import (
    count_lane_jobs_by_status,
    find_background_job_for_backtest_run,
)
from app.core.background_jobs.worker import LANE_HEAVY
from app.core.config import settings
from app.modules.compute.schemas import (
    ComputeBatchAccepted,
    ComputeBatchCreateRequest,
    ComputeBatchStatusResponse,
    ComputeCancelResponse,
    ComputeQueueMetrics,
    ComputeRunAccepted,
    ComputeRunCreateRequest,
)
from app.modules.robots_v2.backtest.quotas import assert_can_start_optimization_batch
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestCompareResponse,
    RobotV2BacktestDetailsResponse,
    RobotV2BacktestListResponse,
    RobotV2BacktestRequest,
    RobotV2BacktestStatusResponse,
)
from app.modules.robots_v2.backtest.service import backtest_service
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4

logger = logging.getLogger(__name__)


class ComputeService:
    async def create_run(
        self,
        db: Session,
        user_id: int,
        body: ComputeRunCreateRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ComputeRunAccepted:
        if idempotency_key:
            logger.info(
                "event=COMPUTE_RUN_IDEMPOTENCY user_id=%s key=%s",
                user_id,
                idempotency_key[:80],
            )
        request = RobotV2BacktestRequest(
            config=body.config,
            from_date=body.from_date,
            to_date=body.to_date,
            initial_capital=body.initial_capital,
            robot_id=body.robot_id,
            token_id=body.token_id,
            async_execution=True,
        )
        rec, enqueued = await backtest_service.start(
            db,
            user_id,
            request,
            priority=body.priority,
        )
        if not enqueued:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to enqueue backtest_run",
            )
        job_id = None
        try:
            job = find_background_job_for_backtest_run(db, int(rec.run_id))
            if job and job.get("id") is not None:
                job_id = str(job["id"])
        except Exception:
            pass
        return ComputeRunAccepted(
            run_id=int(rec.run_id),
            status="queued",
            job_id=job_id,
            message=f"Poll GET /api/compute/v1/runs/{rec.run_id}",
        )

    async def get_run_status(
        self, run_id: int, *, user_id: int, db: Session
    ) -> RobotV2BacktestStatusResponse:
        return await backtest_service.get_status(run_id, user_id=user_id, db=db)

    async def get_run_details(
        self, run_id: int, *, user_id: int, db: Session
    ) -> RobotV2BacktestDetailsResponse:
        return await backtest_service.get_details(run_id, user_id=user_id, db=db)

    async def list_runs(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> RobotV2BacktestListResponse:
        _ = offset  # persist list API is limit-only today
        return await backtest_service.list_runs(
            db, user_id=user_id, robot_id=robot_id, limit=limit,
        )

    async def compare_runs(
        self,
        db: Session,
        *,
        user_id: int,
        base_run_id: int,
        compare_run_id: int,
    ) -> RobotV2BacktestCompareResponse:
        return await backtest_service.compare(
            db,
            user_id=user_id,
            base_run_id=base_run_id,
            compare_run_id=compare_run_id,
        )

    async def cancel_run(
        self, run_id: int, *, user_id: int, db: Session
    ) -> ComputeCancelResponse:
        rec = await backtest_service.cancel(run_id, user_id=user_id, db=db)
        status_s = str(rec.status or "").lower()
        if status_s in {"success", "failed", "cancelled"}:
            return ComputeCancelResponse(
                ok=True,
                status=status_s,
                run_id=int(rec.run_id),
            )
        return ComputeCancelResponse(
            ok=True,
            status="cancel_requested",
            run_id=int(rec.run_id),
        )

    async def create_batch(
        self,
        db: Session,
        user_id: int,
        body: ComputeBatchCreateRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ComputeBatchAccepted:
        from app.modules.recommendations import optimization_batch_queries as batch_q
        from app.modules.recommendations.optimization_engine import param_summary_from_config

        if idempotency_key:
            logger.info(
                "event=COMPUTE_BATCH_IDEMPOTENCY user_id=%s key=%s",
                user_id,
                idempotency_key[:80],
            )

        schema = settings.DB_SCHEMA or "public"
        variants = list(body.variants)
        assert_can_start_optimization_batch(db, user_id=user_id, items=len(variants))

        if batch_q.has_active_batch(db, schema, body.robot_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active optimization batch already exists for this robot",
            )

        capital = body.initial_capital
        if capital is None and body.base_config:
            try:
                capital = float(
                    TradingRobotConfigV4.model_validate(body.base_config).risk.capital
                )
            except Exception:
                capital = 100_000.0
        if capital is None:
            capital = 100_000.0

        batch_id = batch_q.insert_batch(
            db,
            schema,
            robot_id=body.robot_id,
            user_id=user_id,
            goal=str(body.goal or "balanced"),
            mode="grid",
            total_candidates=len(variants),
            requested_from=body.from_date,
            requested_to=body.to_date,
            initial_capital=float(capital),
        )

        run_ids: list[int] = []
        for idx, variant in enumerate(variants):
            cfg = dict(variant.config)
            if body.base_config and not cfg.get("configVersion"):
                merged = dict(body.base_config)
                merged.update(cfg)
                cfg = merged
            try:
                TradingRobotConfigV4.model_validate(cfg)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid variant {variant.variant_key}: {exc}",
                ) from exc

            request = RobotV2BacktestRequest(
                config=cfg,
                from_date=body.from_date,
                to_date=body.to_date,
                initial_capital=float(capital),
                robot_id=body.robot_id,
                token_id=body.token_id,
                async_execution=True,
            )
            rec, enqueued = await backtest_service.start(
                db,
                user_id,
                request,
                priority=body.priority or "batch",
            )
            if not enqueued:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to enqueue variant {variant.variant_key}",
                )
            run_id = int(rec.run_id)
            run_ids.append(run_id)
            batch_q.insert_batch_item(
                db,
                schema,
                batch_id=batch_id,
                candidate_index=idx,
                run_id=run_id,
                param_summary={
                    "variant_key": variant.variant_key,
                    **(param_summary_from_config(cfg) or {}),
                },
            )

        db.commit()
        return ComputeBatchAccepted(
            batch_id=batch_id,
            status="queued",
            items_total=len(run_ids),
            run_ids=run_ids,
            message=f"Poll GET /api/compute/v1/batches/{batch_id}",
        )

    def get_batch(
        self, db: Session, *, batch_id: int, user_id: int
    ) -> ComputeBatchStatusResponse:
        from app.modules.recommendations.optimization_runner import get_optimization_batch_status

        schema = settings.DB_SCHEMA or "public"
        raw = get_optimization_batch_status(db, schema, batch_id=batch_id, user_id=user_id)
        if not raw:
            raise HTTPException(status_code=404, detail="Batch not found")

        progress = raw.get("progress") or {}
        items = list(raw.get("items") or [])
        done = int(progress.get("success") or 0)
        failed = int(progress.get("failed") or 0)
        cancelled = int(progress.get("cancelled") or 0)
        total = int(raw.get("total_candidates") or len(items) or 0)
        run_ids = [
            int(i["run_id"])
            for i in items
            if i.get("run_id") is not None
        ]
        return ComputeBatchStatusResponse(
            batch_id=int(raw.get("batch_id") or batch_id),
            status=str(raw.get("status") or "queued"),
            items_total=total,
            items_done=done,
            items_failed=failed,
            items_cancelled=cancelled,
            progress_percent=float(progress.get("percent") or 0.0),
            robot_id=int(raw["robot_id"]) if raw.get("robot_id") is not None else None,
            run_ids=run_ids,
        )

    async def cancel_batch(
        self, db: Session, *, batch_id: int, user_id: int
    ) -> ComputeCancelResponse:
        from app.modules.recommendations.optimization_runner import (
            cancel_optimization_batch,
        )

        schema = settings.DB_SCHEMA or "public"
        raw = await cancel_optimization_batch(
            db, schema, batch_id=batch_id, user_id=user_id,
        )
        if not raw:
            raise HTTPException(status_code=404, detail="Batch not found")
        return ComputeCancelResponse(
            ok=True,
            status="cancel_requested",
            batch_id=batch_id,
        )

    def queue_metrics(self, db: Session) -> ComputeQueueMetrics:
        depths = count_lane_jobs_by_status(db, lane=LANE_HEAVY)
        return ComputeQueueMetrics(
            lane=LANE_HEAVY,
            queued=int(depths.get("queued") or 0),
            running=int(depths.get("running") or 0),
            as_of=datetime.now(timezone.utc),
        )


compute_service = ComputeService()
