"""Job type handlers executed by lane workers."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

logger = logging.getLogger(__name__)

JobHandler = Callable[[Dict[str, Any]], Awaitable[None]]


async def handle_portfolio_sync(payload: Dict[str, Any]) -> None:
    from app.core.database import SessionLocal
    from app.modules.robots.portfolio_updater.scheduler import portfolio_scheduler

    db = SessionLocal()
    try:
        robot_data = dict(payload or {})
        portfolio_scheduler.robot.db = db
        result = await portfolio_scheduler.robot.run(
            robot_id=int(robot_data["robot_id"]),
            user_id=int(robot_data["user_id"]),
            token_id=int(robot_data["token_id"]),
            token=str(robot_data.get("token") or ""),
            broker_type=robot_data.get("broker_type"),
            token_extra_data=robot_data.get("token_extra_data") or {},
        )
        db.commit()
        logger.info(
            "portfolio_sync robot_id=%s status=%s",
            robot_data.get("robot_id"),
            result.get("status"),
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def handle_live_trading_session(payload: Dict[str, Any]) -> None:
    from app.modules.robots.trading.scheduler import trading_scheduler

    robot = dict(payload or {})
    await trading_scheduler._run_session(robot)


async def handle_history_backtest(payload: Dict[str, Any]) -> None:
    from app.modules.robots.router import _continue_history_backtest_async

    run_id = int(payload["run_id"])
    user_id = int(payload["user_id"])
    body = dict(payload.get("body") or {})
    if payload.get("skip_crypto_prefetch"):
        body["skip_crypto_prefetch"] = True
    screening_symbols = payload.get("crypto_screening_symbols")
    if screening_symbols:
        body["crypto_screening_symbols"] = list(screening_symbols)
    await _continue_history_backtest_async(run_id, user_id, body)


async def handle_crypto_screening_prefetch(payload: Dict[str, Any]) -> None:
    from app.modules.robots.trading.backtest.crypto_screening_prefetch import (
        run_crypto_screening_prefetch,
    )

    await run_crypto_screening_prefetch(dict(payload or {}))


async def handle_corporate_actions_dividend_etl(_payload: Dict[str, Any]) -> None:
    from app.core.database import SessionLocal
    from app.modules.corporate_actions import etl as corp_etl

    db = SessionLocal()
    try:
        n_tq = await corp_etl.sync_tqbr_securities_reference(db)
        db.commit()
        logger.info("background dividend ETL: tqbr upserted=%s", n_tq)
    except Exception as e:
        logger.warning("background tqbr sync failed: %s", e)
        db.rollback()
    finally:
        db.close()

    db = SessionLocal()
    try:
        info = await corp_etl.run_scheduled_dividend_etl(db)
        db.commit()
        logger.info("background dividend ETL: %s", info)
    except Exception as e:
        logger.warning("background dividend ETL failed: %s", e)
        db.rollback()
    finally:
        db.close()


JOB_HANDLERS: Dict[str, JobHandler] = {
    "portfolio_sync": handle_portfolio_sync,
    "live_trading_session": handle_live_trading_session,
    "history_backtest": handle_history_backtest,
    "crypto_screening_prefetch": handle_crypto_screening_prefetch,
    "corporate_actions_dividend_etl": handle_corporate_actions_dividend_etl,
}


async def execute_job_handler(job_type: str, payload: Dict[str, Any]) -> None:
    handler = JOB_HANDLERS.get(job_type)
    if handler is None:
        raise RuntimeError(f"Unknown background job type: {job_type}")
    await handler(payload)
