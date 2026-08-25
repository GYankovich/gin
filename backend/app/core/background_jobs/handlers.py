"""Job type handlers executed by lane workers."""

from __future__ import annotations



import logging

from typing import Any, Awaitable, Callable, Dict



logger = logging.getLogger(__name__)



JobHandler = Callable[[Dict[str, Any]], Awaitable[None]]





async def handle_portfolio_sync(payload: Dict[str, Any]) -> None:

    from app.core.database import SessionLocal

    from app.modules.robots_v2.portfolio.runner import run_portfolio_sync_v2



    db = SessionLocal()

    try:

        result = await run_portfolio_sync_v2(db, dict(payload or {}))

        if result.get("status") != "skipped":

            db.commit()

        logger.info(

            "portfolio_sync robot_id=%s status=%s",

            payload.get("robot_id"),

            result.get("status"),

        )

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()





async def handle_corporate_actions_dividend_etl(_payload: Dict[str, Any]) -> None:

    from app.core.database import SessionLocal

    from app.modules.corporate_actions import etl as corp_etl

    from app.modules.robots.moex_securities_updater.robot import sync_moex_securities_reference



    db = SessionLocal()

    try:

        summary = await sync_moex_securities_reference(db)

        db.commit()

        logger.info("background dividend ETL: moex securities sync=%s", summary)

    except Exception as e:

        logger.warning("background moex securities sync failed: %s", e)

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

    "corporate_actions_dividend_etl": handle_corporate_actions_dividend_etl,

}





async def execute_job_handler(job_type: str, payload: Dict[str, Any]) -> None:

    handler = JOB_HANDLERS.get(job_type)

    if handler is None:

        raise RuntimeError(f"Unknown background job type: {job_type}")

    await handler(payload)

