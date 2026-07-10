from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.analytics.service import analytics_service
from app.modules.robots.service import robot_service
from app.modules.robots.trading.strategies import get_strategy_info, list_strategies

from . import queries
from .context import AnalysisContext
from .rules import generate_recommendations, strategy_static_tips
from .optimization_engine import (
    generate_grid_configs,
    rank_backtest_rows,
    check_overfitting_warnings,
    param_summary_from_config,
)
from .optimization_failure_hints import build_failure_insights
from .optimization_runner import (
    cancel_optimization_batch as cancel_optimization_batch_runner,
    get_optimization_batch_status,
    start_optimization_batch,
)
from .schemas import (
    BacktestRunInsight,
    LiveSituationSummary,
    OptimizationBatchCancelResponse,
    OptimizationBatchProgress,
    OptimizationBatchStartedResponse,
    OptimizationBatchStatusResponse,
    OptimizationBatchItem,
    OptimizationFailedRunItem,
    OptimizationGoal,
    OptimizationMode,
    OptimizationParamSuggestion,
    OptimizationPlanCandidate,
    OptimizationPlanResponse,
    OptimizationRankItem,
    OptimizationRankResponse,
    OptimizationRunRequest,
    OptimizationSessionFailuresResponse,
    RobotRecommendationsResponse,
    StrategyTipsResponse,
)


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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


def _failed_run_items_from_rows(
    rows: List[Any],
    *,
    default_strategy: str,
) -> List[OptimizationFailedRunItem]:
    out: List[OptimizationFailedRunItem] = []
    seen: set[int] = set()
    for row in rows:
        run_id = int(row[0])
        if run_id in seen:
            continue
        seen.add(run_id)
        snap = _coerce_config_snapshot(row[4])
        err = str(row[6] or "") if row[6] is not None else ""
        if not err.strip():
            continue
        insights = build_failure_insights(err, snap)
        if insights.get("failure_category") not in ("no_universe",) and not insights.get("suggested_changes"):
            continue
        strategy_name = str((snap or {}).get("strategy") or default_strategy)
        out.append(
            OptimizationFailedRunItem(
                run_id=run_id,
                error_message=err or None,
                failure_category=str(insights.get("failure_category") or "unknown"),
                failure_summary=insights.get("failure_summary"),
                top_rejects=insights.get("top_rejects") or {},
                suggested_changes=[
                    OptimizationParamSuggestion(**ch)
                    for ch in (insights.get("suggested_changes") or [])
                ],
                param_summary=param_summary_from_config(snap, strategy_name) if snap else {},
                requested_from=row[2],
                requested_to=row[3],
                started_at=row[5],
            )
        )
    return out


def _row_to_insight(row: Any) -> BacktestRunInsight:
    ret = _safe_float(row[6])
    dd = _safe_float(row[7])
    score = None
    if ret is not None:
        score = ret - 0.5 * (dd or 0.0)
    return BacktestRunInsight(
        run_id=int(row[0]),
        status=str(row[1] or ""),
        requested_from=row[2],
        requested_to=row[3],
        created_at=row[5],
        total_return_percent=ret,
        max_drawdown_percent=dd,
        win_rate_percent=_safe_float(row[8]),
        trades_total=int(row[9] or 0) if row[9] is not None else None,
        sharpe_ratio=_safe_float(row[10]),
        score=round(score, 4) if score is not None else None,
    )


def _pick_best(insights: List[BacktestRunInsight]) -> Optional[BacktestRunInsight]:
    if not insights:
        return None
    scored = [i for i in insights if i.score is not None]
    if scored:
        return max(scored, key=lambda x: x.score or -1e9)
    return insights[0]


class RecommendationsService:
    async def get_robot_recommendations(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        schema: str,
        backtest_limit: int = 15,
    ) -> Optional[RobotRecommendationsResponse]:
        robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            return None

        config = dict(robot.get("config") or {})
        strategy = str(config.get("strategy") or "grain_seed")
        strategy_info = get_strategy_info(strategy) or {}
        strategy_title = strategy_info.get("title")

        successful_rows = queries.fetch_successful_backtests(
            db, schema, robot_id, limit=backtest_limit
        )
        successful = [_row_to_insight(r) for r in successful_rows]
        best = _pick_best(successful)

        best_config_snapshot: Optional[Dict[str, Any]] = None
        best_backtest_payload: Optional[Dict[str, Any]] = None
        if best and successful_rows:
            for r in successful_rows:
                if int(r[0]) == best.run_id:
                    snap = r[4]
                    best_config_snapshot = snap if isinstance(snap, dict) else None
                    payload = r[11] if len(r) > 11 else None
                    best_backtest_payload = payload if isinstance(payload, dict) else None
                    break

        latest_row = queries.fetch_latest_backtest_any_status(db, schema, robot_id)
        latest = _row_to_insight(latest_row) if latest_row else None

        live_metrics_raw = analytics_service.get_robot_metrics(
            db, robot_id=robot_id, recent_limit=10, schema=schema, user_id=user_id
        )
        live_metrics = (live_metrics_raw or {}).get("metrics")

        try:
            live_snapshot = await robot_service.get_live_snapshot(db, robot_id, user_id)
        except Exception:
            live_snapshot = {"stream_health": {}, "active_positions": []}

        sig_stats = queries.fetch_signal_execution_stats(db, schema, robot_id)
        exec_rate = None
        if sig_stats["total"] > 0:
            exec_rate = round(sig_stats["executed"] / sig_stats["total"] * 100.0, 1)

        risk_events_7d = queries.fetch_risk_events_count(db, schema, robot_id, days=7)

        ctx = AnalysisContext(
            robot_id=robot_id,
            strategy=strategy,
            strategy_title=strategy_title,
            config=config,
            strategy_params=dict(config.get("strategy_params") or {}),
            risk=dict(config.get("risk") or {}),
            robot_status=int(robot.get("status") or 0),
            live_metrics=live_metrics,
            live_snapshot=live_snapshot,
            signal_execution_rate_pct=exec_rate,
            risk_events_7d=risk_events_7d,
            successful_backtests=successful,
            latest_backtest=latest,
            best_backtest=best,
            best_config_snapshot=best_config_snapshot,
            best_backtest_payload=best_backtest_payload,
        )
        recommendations = generate_recommendations(ctx)

        stream = live_snapshot.get("stream_health") or {}
        live_summary = LiveSituationSummary(
            robot_status=int(robot.get("status") or 0),
            stream_connected_hint=bool(stream.get("connected_hint")),
            last_event_at=stream.get("last_event_at"),
            open_positions=len(live_snapshot.get("active_positions") or []),
            signal_execution_rate_pct=exec_rate,
            risk_events_7d=risk_events_7d,
            metrics=live_metrics,
        )

        config_summary = {
            "strategy": strategy,
            "interval": ctx.strategy_params.get("interval"),
            "candle_days": ctx.strategy_params.get("candle_days"),
            "figis_count": len(config.get("allowed_figis") or config.get("figis") or []),
            "broker_type": config.get("broker_type"),
        }

        return RobotRecommendationsResponse(
            robot_id=robot_id,
            strategy=strategy,
            strategy_title=strategy_title,
            generated_at=datetime.now(timezone.utc),
            backtest_runs_analyzed=len(successful),
            best_backtest_run_id=best.run_id if best else None,
            best_backtest=best,
            latest_backtest=latest,
            live=live_summary,
            recommendations=recommendations,
            config_snapshot_summary=config_summary,
        )

    def get_strategy_tips(self, strategy: str) -> Optional[StrategyTipsResponse]:
        info = get_strategy_info(strategy)
        if not info:
            return None
        tips = strategy_static_tips(strategy, info.get("params_schema") or {})
        return StrategyTipsResponse(
            strategy=strategy,
            strategy_title=info.get("title"),
            tips=tips,
        )

    def list_strategies_with_tips(self) -> List[Dict[str, Any]]:
        return [
            {"name": s["name"], "title": s.get("title"), "description": s.get("description")}
            for s in list_strategies()
        ]

    async def rank_backtest_runs(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        schema: str,
        goal: OptimizationGoal = OptimizationGoal.BALANCED,
        limit: int = 50,
    ) -> Optional[OptimizationRankResponse]:
        robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            return None

        config = dict(robot.get("config") or {})
        strategy = str(config.get("strategy") or "grain_seed")

        rows = queries.fetch_successful_backtests(db, schema, robot_id, limit=limit)
        ranked_raw = rank_backtest_rows(rows, goal=goal.value)
        warnings = check_overfitting_warnings(ranked_raw)

        ranked = [
            OptimizationRankItem(
                rank=item["rank"],
                run_id=item["run_id"],
                score=item["score"],
                total_return_percent=item.get("total_return_percent"),
                max_drawdown_percent=item.get("max_drawdown_percent"),
                win_rate_percent=item.get("win_rate_percent"),
                trades_total=item.get("trades_total"),
                sharpe_ratio=item.get("sharpe_ratio"),
                requested_from=item.get("requested_from"),
                requested_to=item.get("requested_to"),
                started_at=item.get("started_at"),
                param_summary=item.get("param_summary") or {},
            )
            for item in ranked_raw
        ]

        failed_rows = queries.fetch_failed_backtests(
            db,
            schema,
            user_id=user_id,
            robot_id=robot_id,
            limit=limit,
        )
        failed_runs = _failed_run_items_from_rows(failed_rows, default_strategy=strategy)

        return OptimizationRankResponse(
            robot_id=robot_id,
            strategy=strategy,
            goal=goal,
            runs_analyzed=len(ranked),
            ranked=ranked,
            failed_runs=failed_runs,
            overfitting_warnings=warnings,
        )

    async def session_optimization_failures(
        self,
        db: Session,
        user_id: int,
        schema: str,
        limit: int = 20,
    ) -> OptimizationSessionFailuresResponse:
        rows = queries.fetch_failed_backtests(
            db,
            schema,
            user_id=user_id,
            robot_id=None,
            limit=limit,
        )
        strategy = "grain_seed"
        if rows:
            snap = _coerce_config_snapshot(rows[0][4])
            strategy = str((snap or {}).get("strategy") or strategy)
        failed_runs = _failed_run_items_from_rows(rows, default_strategy=strategy)
        return OptimizationSessionFailuresResponse(failed_runs=failed_runs)

    async def plan_optimization(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        goal: OptimizationGoal = OptimizationGoal.BALANCED,
        mode: OptimizationMode = OptimizationMode.SPEED,
    ) -> Optional[OptimizationPlanResponse]:
        robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            return None

        config = dict(robot.get("config") or {})
        strategy = str(config.get("strategy") or "grain_seed")
        variants = generate_grid_configs(config, strategy, mode=mode.value)
        candidates = [
            OptimizationPlanCandidate(
                index=i + 1,
                param_summary=param_summary_from_config(v, strategy),
                config_snapshot=v,
            )
            for i, v in enumerate(variants)
        ]
        return OptimizationPlanResponse(
            robot_id=robot_id,
            strategy=strategy,
            goal=goal,
            mode=mode,
            total_candidates=len(candidates),
            candidates=candidates,
        )

    async def run_optimization_batch(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        schema: str,
        body: OptimizationRunRequest,
    ) -> Optional[OptimizationBatchStartedResponse]:
        raw = await start_optimization_batch(
            db,
            schema,
            robot_id=robot_id,
            user_id=user_id,
            goal=body.goal,
            mode=body.mode,
            requested_from=body.from_date,
            requested_to=body.to_date,
            initial_capital=body.initial_capital,
        )
        if not raw:
            return None
        return OptimizationBatchStartedResponse(
            batch_id=int(raw["batch_id"]),
            robot_id=int(raw["robot_id"]),
            goal=body.goal,
            mode=body.mode,
            total_candidates=int(raw["total_candidates"]),
            enqueued=int(raw["enqueued"]),
            run_ids=[int(x) for x in raw.get("run_ids") or []],
            status=str(raw.get("status") or "running"),
        )

    def get_optimization_batch(
        self,
        db: Session,
        batch_id: int,
        user_id: int,
        schema: str,
    ) -> Optional[OptimizationBatchStatusResponse]:
        raw = get_optimization_batch_status(
            db,
            schema,
            batch_id=batch_id,
            user_id=user_id,
        )
        if not raw:
            return None
        progress = raw.get("progress") or {}
        return OptimizationBatchStatusResponse(
            batch_id=int(raw["batch_id"]),
            robot_id=int(raw["robot_id"]),
            goal=OptimizationGoal(str(raw["goal"])),
            mode=OptimizationMode(str(raw["mode"])),
            status=str(raw["status"]),
            total_candidates=int(raw["total_candidates"]),
            progress=OptimizationBatchProgress(**progress),
            requested_from=raw.get("requested_from"),
            requested_to=raw.get("requested_to"),
            initial_capital=raw.get("initial_capital"),
            overfitting_warnings=list(raw.get("overfitting_warnings") or []),
            error_message=raw.get("error_message"),
            created_at=raw.get("created_at"),
            started_at=raw.get("started_at"),
            finished_at=raw.get("finished_at"),
            items=[OptimizationBatchItem(**it) for it in raw.get("items") or []],
            ranked=[OptimizationRankItem(**r) for r in raw.get("ranked") or []],
        )

    def get_active_optimization_batch(
        self,
        db: Session,
        robot_id: int,
        user_id: int,
        schema: str,
    ) -> Optional[OptimizationBatchStatusResponse]:
        from . import optimization_batch_queries as batch_q

        header = batch_q.fetch_active_batch_for_robot(db, schema, robot_id, user_id)
        if not header:
            return None
        return self.get_optimization_batch(db, int(header["id"]), user_id, schema)

    async def cancel_optimization_batch(
        self,
        db: Session,
        batch_id: int,
        user_id: int,
        schema: str,
    ) -> Optional[OptimizationBatchCancelResponse]:
        raw = await cancel_optimization_batch_runner(
            db,
            schema,
            batch_id=batch_id,
            user_id=user_id,
        )
        if not raw:
            return None
        return OptimizationBatchCancelResponse(**raw)


recommendations_service = RecommendationsService()
