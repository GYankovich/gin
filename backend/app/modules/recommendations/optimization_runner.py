from __future__ import annotations

import logging
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.background_jobs.repository import enqueue_background_job
from app.core.background_jobs.worker import LANE_HEAVY
from app.modules.robots import schemas as robot_schemas

from . import optimization_batch_queries as batch_q
from .optimization_engine import (
    BacktestScoreInput,
    calculate_score,
    check_overfitting_warnings,
    generate_grid_configs,
    param_summary_from_config,
)
from .optimization_failure_hints import build_failure_insights
from .schemas import OptimizationGoal, OptimizationMode

logger = logging.getLogger(__name__)


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_token_id(robot: Dict[str, Any]) -> Optional[int]:
    tok = robot.get("token") if isinstance(robot.get("token"), dict) else {}
    if tok.get("id") is not None:
        return int(tok["id"])
    if robot.get("token_id") is not None:
        return int(robot["token_id"])
    return None


async def _enqueue_variant_backtest(
    db: Session,
    schema: str,
    *,
    user_id: int,
    robot_id: int,
    variant_config: Dict[str, Any],
    requested_from: datetime,
    requested_to: datetime,
    initial_capital: float,
    token_id: Optional[int],
) -> int:
    from app.modules.robots.service import robot_service

    request = robot_schemas.RobotHistoryBacktestRequest(
        robot_id=robot_id,
        from_date=requested_from,
        to_date=requested_to,
        initial_capital=initial_capital,
        token_id=token_id,
        config=variant_config,
        async_execution=True,
    )
    out = await robot_service.run_robot_history_backtest(db, user_id, request)
    if not isinstance(out, dict) or not out.get("__async_enqueue__"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось поставить вариант бэктеста в очередь",
        )
    run_id = int(out["run_id"])
    job_id = enqueue_background_job(
        db,
        lane=LANE_HEAVY,
        job_type="history_backtest",
        payload={
            "run_id": run_id,
            "user_id": user_id,
            "body": request.model_dump(mode="json"),
        },
        idempotency_key=f"history_backtest:{run_id}",
    )
    if job_id is None:
        db.execute(
            text(f"""
                UPDATE backtest_runs
                SET status = 'FAILED',
                    finished_at = CURRENT_TIMESTAMP,
                    error_message = :err
                WHERE id = :rid AND status = 'QUEUED'
            """),
            {
                "rid": run_id,
                "err": "enqueue-failed: optimization batch variant",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Очередь heavy занята (run_id={run_id})",
        )
    return run_id


def _sync_items_from_runs(
    db: Session,
    schema: str,
    batch_id: int,
    goal: str,
    items: List[Dict[str, Any]],
) -> Dict[str, int]:
    counts = {"queued": 0, "running": 0, "success": 0, "failed": 0, "cancelled": 0}
    for item in items:
        run_status = str(item.get("run_status") or item.get("item_status") or "queued").upper()
        if run_status == "QUEUED":
            counts["queued"] += 1
            norm = "queued"
        elif run_status == "RUNNING":
            counts["running"] += 1
            norm = "running"
        elif run_status == "SUCCESS":
            counts["success"] += 1
            norm = "success"
        elif run_status == "CANCELLED":
            counts["cancelled"] += 1
            norm = "cancelled"
        else:
            counts["failed"] += 1
            norm = "failed"

        score = None
        if run_status == "SUCCESS":
            metrics = BacktestScoreInput(
                total_return_pct=item.get("total_return_percent"),
                max_drawdown_pct=item.get("max_drawdown_percent"),
                win_rate_pct=item.get("win_rate_percent"),
                trades_total=int(item.get("trades_total") or 0) if item.get("trades_total") is not None else None,
                sharpe=item.get("sharpe_ratio"),
            )
            score = calculate_score(metrics, goal)  # type: ignore[arg-type]

        run_id = item.get("run_id")
        if run_id is not None:
            batch_q.update_batch_item_from_run(
                db,
                schema,
                batch_id=batch_id,
                run_id=int(run_id),
                status=norm,
                score=score,
            )
    return counts


def _coerce_config_snapshot(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _batch_item_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    run_status = str(item.get("run_status") or item.get("item_status") or "queued").lower()
    payload: Dict[str, Any] = {
        "candidate_index": int(item["candidate_index"]),
        "run_id": int(item["run_id"]) if item.get("run_id") is not None else None,
        "status": run_status,
        "score": item.get("score"),
        "param_summary": item.get("param_summary") or {},
        "total_return_percent": item.get("total_return_percent"),
        "max_drawdown_percent": item.get("max_drawdown_percent"),
        "sharpe_ratio": item.get("sharpe_ratio"),
        "trades_total": item.get("trades_total"),
        "error_message": item.get("error_message"),
        "failure_category": None,
        "failure_summary": None,
        "top_rejects": {},
        "suggested_changes": [],
    }
    if run_status == "failed" and item.get("error_message"):
        snap = _coerce_config_snapshot(item.get("config_snapshot"))
        insights = build_failure_insights(str(item.get("error_message")), snap)
        payload["failure_category"] = insights.get("failure_category")
        payload["failure_summary"] = insights.get("failure_summary")
        payload["top_rejects"] = insights.get("top_rejects") or {}
        payload["suggested_changes"] = insights.get("suggested_changes") or []
    return payload


def _build_ranked_from_items(items: List[Dict[str, Any]], goal: str) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for item in items:
        if str(item.get("run_status") or "").upper() != "SUCCESS":
            continue
        run_id = item.get("run_id")
        if run_id is None:
            continue
        metrics = BacktestScoreInput(
            total_return_pct=item.get("total_return_percent"),
            max_drawdown_pct=item.get("max_drawdown_percent"),
            win_rate_pct=item.get("win_rate_percent"),
            trades_total=int(item.get("trades_total") or 0) if item.get("trades_total") is not None else None,
            sharpe=item.get("sharpe_ratio"),
        )
        ranked.append(
            {
                "run_id": int(run_id),
                "score": calculate_score(metrics, goal),  # type: ignore[arg-type]
                "total_return_percent": metrics.total_return_pct,
                "max_drawdown_percent": metrics.max_drawdown_pct,
                "win_rate_percent": metrics.win_rate_pct,
                "trades_total": metrics.trades_total,
                "sharpe_ratio": metrics.sharpe,
                "param_summary": item.get("param_summary") if isinstance(item.get("param_summary"), dict) else {},
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked


async def start_optimization_batch(
    db: Session,
    schema: str,
    *,
    robot_id: int,
    user_id: int,
    goal: OptimizationGoal,
    mode: OptimizationMode,
    requested_from: datetime,
    requested_to: datetime,
    initial_capital: float,
) -> Dict[str, Any]:
    from app.modules.robots.service import robot_service

    robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
    if int(robot.get("type") or 0) != 2:
        return {}

    if batch_q.has_active_batch(db, schema, robot_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У робота уже есть активная оптимизация. Дождитесь завершения или отмените.",
        )

    config = dict(robot.get("config") or {})
    strategy = str(config.get("strategy") or "grain_seed")
    variants = generate_grid_configs(config, strategy, mode=mode.value)
    if not variants:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нет оптимизируемых параметров для текущего конфига",
        )

    requested_from = _coerce_utc(requested_from)
    requested_to = _coerce_utc(requested_to)
    token_id = _resolve_token_id(robot)

    batch_id = batch_q.insert_batch(
        db,
        schema,
        robot_id=robot_id,
        user_id=user_id,
        goal=goal.value,
        mode=mode.value,
        total_candidates=len(variants),
        requested_from=requested_from,
        requested_to=requested_to,
        initial_capital=initial_capital,
    )

    run_ids: List[int] = []
    errors: List[str] = []
    for idx, variant in enumerate(variants, start=1):
        summary = param_summary_from_config(variant, strategy)
        try:
            run_id = await _enqueue_variant_backtest(
                db,
                schema,
                user_id=user_id,
                robot_id=robot_id,
                variant_config=variant,
                requested_from=requested_from,
                requested_to=requested_to,
                initial_capital=initial_capital,
                token_id=token_id,
            )
            batch_q.insert_batch_item(
                db,
                schema,
                batch_id=batch_id,
                candidate_index=idx,
                run_id=run_id,
                param_summary=summary,
            )
            run_ids.append(run_id)
        except HTTPException as exc:
            errors.append(f"#{idx}: {exc.detail}")
            logger.warning("optimization batch variant %s failed: %s", idx, exc.detail)
        except Exception as exc:
            errors.append(f"#{idx}: {exc}")
            logger.exception("optimization batch variant %s failed", idx)

    if not run_ids:
        batch_q.update_batch_status(
            db,
            schema,
            batch_id,
            status="failed",
            error_message="; ".join(errors) or "Не удалось поставить ни одного прогона",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось поставить прогоны в очередь",
        )

    if errors:
        batch_q.update_batch_status(
            db,
            schema,
            batch_id,
            status="running",
            error_message=f"Часть вариантов пропущена: {'; '.join(errors)}",
        )

    db.commit()
    return {
        "batch_id": batch_id,
        "robot_id": robot_id,
        "goal": goal.value,
        "mode": mode.value,
        "total_candidates": len(variants),
        "enqueued": len(run_ids),
        "run_ids": run_ids,
        "status": "running",
    }


def get_optimization_batch_status(
    db: Session,
    schema: str,
    *,
    batch_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    header = batch_q.fetch_batch_header(db, schema, batch_id, user_id)
    if not header:
        return None

    items = batch_q.fetch_batch_items(db, schema, batch_id)
    counts = _sync_items_from_runs(db, schema, batch_id, str(header["goal"]), items)
    items = batch_q.fetch_batch_items(db, schema, batch_id)

    total = int(header.get("total_candidates") or 0)
    done = counts["success"] + counts["failed"] + counts["cancelled"]
    batch_status = str(header.get("status") or "running")
    if done >= total and total > 0:
        batch_status = "completed"
    elif counts["running"] > 0 or counts["queued"] > 0:
        batch_status = "running"

    ranked: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if batch_status == "completed":
        ranked = _build_ranked_from_items(items, str(header["goal"]))
        warnings = check_overfitting_warnings(ranked)
        batch_q.update_batch_status(
            db,
            schema,
            batch_id,
            status="completed",
            overfitting_warnings=warnings,
        )
        db.commit()
        header = batch_q.fetch_batch_header(db, schema, batch_id, user_id) or header
    else:
        db.commit()

    progress_pct = round(done / total * 100.0, 1) if total else 0.0
    return {
        "batch_id": int(header["id"]),
        "robot_id": int(header["robot_id"]),
        "goal": header["goal"],
        "mode": header["mode"],
        "status": batch_status,
        "total_candidates": total,
        "progress": {**counts, "done": done, "percent": progress_pct},
        "requested_from": header.get("requested_from"),
        "requested_to": header.get("requested_to"),
        "initial_capital": header.get("initial_capital"),
        "overfitting_warnings": header.get("overfitting_warnings") or warnings,
        "error_message": header.get("error_message"),
        "created_at": header.get("created_at"),
        "started_at": header.get("started_at"),
        "finished_at": header.get("finished_at"),
        "items": [_batch_item_payload(it) for it in items],
        "ranked": ranked,
    }


async def cancel_optimization_batch(
    db: Session,
    schema: str,
    *,
    batch_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    from app.modules.robots.service import robot_service

    header = batch_q.fetch_batch_header(db, schema, batch_id, user_id)
    if not header:
        return None

    run_ids = batch_q.fetch_batch_run_ids(db, schema, batch_id)
    cancelled = 0
    for run_id in run_ids:
        try:
            await robot_service.request_backtest_cancel(db=db, run_id=run_id, user_id=user_id)
            cancelled += 1
        except Exception:
            logger.warning("cancel batch run_id=%s failed", run_id, exc_info=True)

    batch_q.update_batch_status(db, schema, batch_id, status="cancelled")
    db.commit()
    return {"batch_id": batch_id, "cancelled_runs": cancelled, "status": "cancelled"}
