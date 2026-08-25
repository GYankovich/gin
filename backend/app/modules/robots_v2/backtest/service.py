"""Backtest orchestration: candle load, universe resolve, async worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db_context
from app.modules.robots.trading.intervals import resolve_strategy_interval
from app.modules.robots.trading.runtime.orchestrator import get_trading_orchestrator
from app.modules.robots_v2.backtest.host import BacktestHost, dicts_to_candles
from app.modules.robots_v2.backtest.persist import (
    compare_runs,
    create_db_run,
    fetch_db_run,
    list_db_runs,
    persist_result_payload,
    update_db_run,
)
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestCompareResponse,
    RobotV2BacktestDetailsResponse,
    RobotV2BacktestListResponse,
    RobotV2BacktestRequest,
    RobotV2BacktestStatusResponse,
)
from app.modules.robots_v2.backtest.store import BacktestRunRecord, backtest_run_store
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.universe.service import universe_service

logger = logging.getLogger(__name__)

_V4_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "CANDLE_INTERVAL_1_MIN",
    "5m": "CANDLE_INTERVAL_5_MIN",
    "10m": "CANDLE_INTERVAL_10_MIN",
    "15m": "CANDLE_INTERVAL_15_MIN",
    "30m": "CANDLE_INTERVAL_30_MIN",
    "1h": "CANDLE_INTERVAL_HOUR",
    "4h": "CANDLE_INTERVAL_4_HOUR",
    "1d": "CANDLE_INTERVAL_DAY",
}


def v4_timeframe_to_interval_raw(timeframe: str) -> str:
    tf = str(timeframe or "").strip()
    if tf.startswith("CANDLE_INTERVAL"):
        return tf
    return _V4_TIMEFRAME_MAP.get(tf.lower(), "CANDLE_INTERVAL_5_MIN")


def _record_to_status(rec: BacktestRunRecord) -> dict[str, Any]:
    payload = rec.result_payload or {}
    return {
        "run_id": rec.run_id,
        "robot_id": rec.robot_id,
        "status": rec.status,
        "requested_from": rec.requested_from,
        "requested_to": rec.requested_to,
        "started_at": rec.started_at,
        "finished_at": rec.finished_at,
        "initial_capital": rec.initial_capital,
        "progress_percent": rec.progress_percent,
        "run_phase": rec.run_phase,
        "phase_label": rec.phase_label,
        "phase_units_done": rec.phase_units_done,
        "phase_units_total": rec.phase_units_total,
        "cancel_requested": rec.cancel_requested,
        "error_message": rec.error_message,
        "total_return_percent": payload.get("total_return_percent"),
        "max_drawdown_percent": payload.get("max_drawdown_percent"),
        "final_equity": payload.get("final_equity"),
        "trades_total": len(payload.get("trades") or []),
        "result_payload": payload,
        "signals": rec.signals,
        "orders": rec.orders,
        "portfolio_snapshots": rec.portfolio_snapshots,
        "daily_summary": rec.daily_summary,
    }


class BacktestService:
    def __init__(self) -> None:
        self._host = BacktestHost()
        self._tasks: dict[int, asyncio.Task] = {}
        self._cancel_flags: dict[int, bool] = {}

    async def start(
        self,
        db: Session,
        user_id: int,
        request: RobotV2BacktestRequest,
        *,
        robot_config: dict[str, Any] | None = None,
    ) -> tuple[BacktestRunRecord, bool]:
        """Returns (record, async_enqueued)."""
        raw_config = dict(request.config or robot_config or {})
        try:
            config = TradingRobotConfigV4.model_validate(raw_config)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid v4 config: {exc}") from exc

        if config.strategy.archetype == "scalper":
            raise HTTPException(
                status_code=422,
                detail="Scalper requires tick/order-flow data and cannot run on bar-close backtest",
            )

        capital = float(request.initial_capital or config.risk.capital)
        config.risk.capital = capital
        snap = config.model_dump(by_alias=True)

        db_id = create_db_run(
            db,
            user_id=user_id,
            robot_id=request.robot_id,
            requested_from=request.from_date,
            requested_to=request.to_date,
            initial_capital=capital,
            config_snapshot=snap,
        )

        rec = await backtest_run_store.create(
            user_id=user_id,
            robot_id=request.robot_id,
            requested_from=request.from_date,
            requested_to=request.to_date,
            initial_capital=capital,
            config_snapshot=snap,
        )
        if db_id is not None:
            rebound = await backtest_run_store.rebind_id(rec.run_id, db_id)
            if rebound is not None:
                rec = rebound

        if request.async_execution:
            task = asyncio.create_task(self._execute(user_id, rec.run_id, config, request))
            self._tasks[rec.run_id] = task
            return rec, True

        await self._execute(user_id, rec.run_id, config, request)
        updated = await backtest_run_store.get(rec.run_id, user_id=user_id)
        return updated or rec, False

    async def get_status(
        self, run_id: int, *, user_id: int, db: Session | None = None,
    ) -> RobotV2BacktestStatusResponse:
        rec = await backtest_run_store.get(run_id, user_id=user_id)
        if rec is not None:
            return RobotV2BacktestStatusResponse.model_validate(_record_to_status(rec))
        if db is not None:
            row = fetch_db_run(db, run_id, user_id=user_id)
            if row is not None:
                return RobotV2BacktestStatusResponse.model_validate(row)
        raise HTTPException(status_code=404, detail="Backtest run not found")

    async def get_details(
        self, run_id: int, *, user_id: int, db: Session | None = None,
    ) -> RobotV2BacktestDetailsResponse:
        rec = await backtest_run_store.get(run_id, user_id=user_id)
        if rec is not None:
            return RobotV2BacktestDetailsResponse.model_validate(_record_to_status(rec))
        if db is not None:
            row = fetch_db_run(db, run_id, user_id=user_id)
            if row is not None:
                return RobotV2BacktestDetailsResponse.model_validate(row)
        raise HTTPException(status_code=404, detail="Backtest run not found")

    async def list_runs(
        self, db: Session, *, user_id: int, robot_id: int | None = None, limit: int = 30,
    ) -> RobotV2BacktestListResponse:
        items = list_db_runs(db, user_id=user_id, robot_id=robot_id, limit=limit)
        return RobotV2BacktestListResponse(items=items, total=len(items))

    async def compare(
        self, db: Session, *, user_id: int, base_run_id: int, compare_run_id: int,
    ) -> RobotV2BacktestCompareResponse:
        base = fetch_db_run(db, base_run_id, user_id=user_id)
        other = fetch_db_run(db, compare_run_id, user_id=user_id)
        mem_base = await backtest_run_store.get(base_run_id, user_id=user_id)
        mem_other = await backtest_run_store.get(compare_run_id, user_id=user_id)
        if mem_base is not None:
            base = {**_record_to_status(mem_base), "config_snapshot": mem_base.config_snapshot}
        if mem_other is not None:
            other = {**_record_to_status(mem_other), "config_snapshot": mem_other.config_snapshot}
        if base is None or other is None:
            raise HTTPException(status_code=404, detail="One or both backtest runs were not found")
        return RobotV2BacktestCompareResponse.model_validate(compare_runs(base, other))

    async def cancel(self, run_id: int, *, user_id: int, db: Session | None = None) -> BacktestRunRecord:
        rec = await backtest_run_store.request_cancel(run_id, user_id=user_id)
        self._cancel_flags[run_id] = True
        if rec is None:
            if db is not None and fetch_db_run(db, run_id, user_id=user_id) is not None:
                update_db_run(db, run_id, cancel_requested=True)
                rec = await backtest_run_store.get(run_id, user_id=user_id)
            if rec is None:
                raise HTTPException(status_code=404, detail="Backtest run not found")
        if db is not None:
            update_db_run(db, run_id, cancel_requested=True)
        return rec

    async def _execute(
        self,
        user_id: int,
        run_id: int,
        config: TradingRobotConfigV4,
        request: RobotV2BacktestRequest,
    ) -> None:
        with get_db_context() as db:
            await self._execute_with_db(db, user_id, run_id, config, request)

    async def _execute_with_db(
        self,
        db: Session,
        user_id: int,
        run_id: int,
        config: TradingRobotConfigV4,
        request: RobotV2BacktestRequest,
    ) -> None:
        await backtest_run_store.update(
            run_id,
            status="RUNNING",
            run_phase="loading_candles",
            phase_label="Loading candles",
            started_at=datetime.now(timezone.utc),
        )
        update_db_run(db, run_id, status="RUNNING", run_phase="loading_candles")
        try:
            universe = await self._resolve_universe(db, user_id, config, request)
            if not universe:
                raise ValueError("Universe is empty after resolve")

            interval_raw = v4_timeframe_to_interval_raw(config.strategy.timeframe)
            resolved = resolve_strategy_interval(interval_raw)
            market = "bybit" if config.core.instrument_type in ("perpetual", "coin_futures") else "moex"

            from_dt = request.from_date.astimezone(timezone.utc)
            to_dt = request.to_date.astimezone(timezone.utc)
            from_date = from_dt.date()
            till_date = to_dt.date()

            from app.modules.robots_v2.engine.candle_seed import lookback_days_for_warmup, warmup_bars_needed

            need_warmup = warmup_bars_needed(config)
            warmup_days = lookback_days_for_warmup(
                timeframe=config.strategy.timeframe,
                need_bars=need_warmup,
            ) if need_warmup else 0
            load_from_date = from_date - timedelta(days=warmup_days)
            load_from_dt = datetime.combine(load_from_date, time.min, tzinfo=timezone.utc)

            if market == "moex":
                from app.modules.robots.trading.data.providers.moex_backtest import ensure_candles_moex_backtest
                from app.modules.robots_v2.universe.token_context import board_for_instrument_type

                board = board_for_instrument_type(config.core.instrument_type)
                await ensure_candles_moex_backtest(
                    db,
                    board=board,
                    tickers=universe,
                    resolved=resolved,
                    from_date=load_from_date,
                    till_date=till_date,
                    user_id=user_id,
                    run_id=run_id,
                    is_cancelled=lambda: self._is_cancelled(run_id),
                )
            else:
                # Bybit: prefetch klines into candles_cache when token credentials available
                if request.token_id:
                    from app.modules.robots_v2.universe.token_context import load_token_context

                    ctx = load_token_context(
                        db,
                        user_id=user_id,
                        token_id=request.token_id,
                        instrument_type=config.core.instrument_type,
                    )
                    if ctx.api_key:
                        category = "inverse" if config.core.instrument_type == "coin_futures" else "linear"
                        await get_trading_orchestrator().prefetch_crypto_candles_for_replay(
                            db,
                            symbols=universe,
                            resolved=resolved,
                            from_date=load_from_date,
                            till_date=till_date,
                            instrument_category=category,
                            testnet=ctx.testnet,
                            user_id=user_id,
                            run_id=run_id,
                            api_key=ctx.api_key,
                            api_secret=ctx.api_secret or "",
                            is_cancelled=lambda: self._is_cancelled(run_id),
                            load_cached_candles=False,
                        )

            await backtest_run_store.update(
                run_id,
                run_phase="simulating",
                phase_label="Simulating",
            )
            update_db_run(db, run_id, run_phase="simulating")

            to_dt_exclusive = datetime.combine(
                till_date + timedelta(days=1), time.min, tzinfo=timezone.utc,
            )
            raw_candles = get_trading_orchestrator().load_candles_by_symbol_from_cache(
                db,
                symbols=universe,
                interval_code=resolved.cache_label,
                interval_code_num=resolved.code_num,
                from_dt=load_from_dt,
                to_dt_exclusive=to_dt_exclusive,
                market=market,
            )

            candles_by_ticker = {
                t: dicts_to_candles(series, ticker=t, interval=interval_raw)
                for t, series in raw_candles.items()
            }

            from time import monotonic

            progress_state = {"done": 0, "total": 1}
            sim_done = False

            def on_progress(done: int, total: int) -> None:
                progress_state["done"] = done
                progress_state["total"] = total

            async def pump_progress() -> None:
                last_touch = 0.0
                while True:
                    done = int(progress_state["done"])
                    total = int(progress_state["total"] or 1)
                    now_m = monotonic()
                    if now_m - last_touch >= 0.25 or sim_done:
                        last_touch = now_m
                        pct = round(done / total * 100.0, 1) if total > 0 else 0.0
                        await backtest_run_store.update(
                            run_id,
                            progress_percent=pct,
                            phase_units_done=done,
                            phase_units_total=total,
                            run_phase="simulating",
                            phase_label="Simulating",
                        )
                    if sim_done:
                        return
                    await asyncio.sleep(0.25)

            session_id = 1_000_000 + run_id
            pump_task = asyncio.create_task(pump_progress())
            try:
                result = await asyncio.to_thread(
                    self._host.run_sync,
                    config=config,
                    universe=universe,
                    candles_by_ticker=candles_by_ticker,
                    initial_capital=float(request.initial_capital or config.risk.capital),
                    session_id=session_id,
                    robot_id=request.robot_id or 0,
                    user_id=user_id,
                    trade_from=from_dt,
                    is_cancelled=lambda: self._is_cancelled(run_id),
                    progress_callback=on_progress,
                )
            finally:
                sim_done = True
                await pump_task

            if self._is_cancelled(run_id):
                finished = datetime.now(timezone.utc)
                await backtest_run_store.update(
                    run_id,
                    status="CANCELLED",
                    run_phase="cancelled",
                    phase_label="Cancelled",
                    finished_at=finished,
                    progress_percent=100.0,
                )
                update_db_run(
                    db, run_id,
                    status="CANCELLED",
                    run_phase="cancelled",
                    finished_at=finished,
                    progress_percent=100,
                    cancel_requested=True,
                )
                return

            payload = {
                "initial_capital": result.initial_capital,
                "final_equity": result.final_equity,
                "total_return_percent": result.total_return_percent,
                "max_drawdown_percent": result.max_drawdown_percent,
                "trades": result.trades,
                "equity_curve": result.equity_curve,
                "stages": result.stages,
                "history_stats": result.history_stats,
                "engine_version": "v2",
            }
            finished = datetime.now(timezone.utc)
            await backtest_run_store.update(
                run_id,
                status="SUCCESS",
                run_phase="done",
                phase_label="Done",
                finished_at=finished,
                progress_percent=100.0,
                result_payload=payload,
                portfolio_snapshots=result.portfolio_snapshots,
                orders=result.orders,
            )
            update_db_run(
                db, run_id,
                status="SUCCESS",
                run_phase="completed",
                finished_at=finished,
                progress_percent=100,
            )
            persist_result_payload(db, run_id, payload)
        except Exception as exc:
            logger.exception("v2 backtest run_id=%s failed", run_id)
            finished = datetime.now(timezone.utc)
            await backtest_run_store.update(
                run_id,
                status="FAILED",
                run_phase="failed",
                phase_label="Failed",
                finished_at=finished,
                error_message=str(exc),
            )
            update_db_run(
                db, run_id,
                status="FAILED",
                run_phase="failed",
                finished_at=finished,
                error_message=str(exc)[:2000],
            )

    async def _resolve_universe(
        self,
        db: Session,
        user_id: int,
        config: TradingRobotConfigV4,
        request: RobotV2BacktestRequest,
    ) -> list[str]:
        u = config.universe
        if u.mode == "fixed":
            tickers = [t.upper() for t in (u.fixed_list or []) if t]
            excluded = {x.upper() for x in u.excluded}
            tickers = [t for t in tickers if t not in excluded]
            return tickers[: u.max_assets]

        token_id = request.token_id
        if token_id is None:
            raise HTTPException(
                status_code=422,
                detail="tokenId is required for index/screener universe in backtest",
            )
        resolved = await universe_service.resolve(
            db,
            user_id,
            token_id=token_id,
            instrument_type=config.core.instrument_type,
            universe_raw=config.universe.model_dump(by_alias=True),
            robot_id=request.robot_id,
            as_of=request.from_date,
        )
        tickers = [i.ticker.upper() for i in resolved.instruments]
        excluded = {x.upper() for x in u.excluded}
        tickers = [t for t in tickers if t not in excluded]
        return tickers[: u.max_assets]

    def _is_cancelled(self, run_id: int) -> bool:
        return self._cancel_flags.get(run_id, False)


backtest_service = BacktestService()
