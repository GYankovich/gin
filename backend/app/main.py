# app/main.py
#///EPIC Platform.ITEM AppBootstrap.TOPIC FastAPI Composition [1]
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging_config import setup_logging, get_logger

setup_logging()

system_log = get_logger("app")


async def _stop_background_task(name: str, stop_coro) -> None:
    try:
        await stop_coro
    except asyncio.CancelledError:
        system_log.debug("%s: остановка прервана (shutdown)", name)
    except Exception as e:
        system_log.error("Ошибка остановки %s: %s", name, e)


async def _start_api_background() -> None:
    if settings.WORKER_EMBEDDED_ENABLED:
        try:
            from app.core.background_jobs.worker import start_embedded_lane_workers
            from app.core.background_jobs.worker_lease import WorkerLeaseConflictError

            await start_embedded_lane_workers()
            system_log.info("Lane workers запущены (embedded)")
        except WorkerLeaseConflictError as e:
            system_log.error(
                "Embedded workers не стартовали — lane уже занята: %s "
                "(остановите второй worker или WORKER_EMBEDDED_ENABLED=false)",
                e,
            )
        except Exception as e:
            system_log.error("Ошибка запуска lane workers: %s", e)
    else:
        system_log.info("Embedded lane workers отключены (WORKER_EMBEDDED_ENABLED=false)")

    schedulers = [
        ("portfolio", "app.modules.robots.portfolio_updater.scheduler", "start_portfolio_scheduler"),
        ("trading", "app.modules.robots.trading.scheduler", "start_trading_scheduler"),
        ("dms", "app.modules.dms.scheduler", "start_dms_scheduler"),
        ("candle_load", "app.modules.market_data_v1.scheduler", "start_candle_load_scheduler"),
        ("corporate_actions", "app.modules.corporate_actions.scheduler", "start_corporate_actions_scheduler"),
    ]
    for name, module_path, fn_name in schedulers:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            await getattr(mod, fn_name)()
            system_log.info("Планировщик %s запущен", name)
        except Exception as e:
            system_log.error("Ошибка запуска планировщика %s: %s", name, e)


async def _stop_api_background() -> None:
    from app.modules.robots.portfolio_updater.scheduler import stop_portfolio_scheduler
    from app.modules.robots.trading.scheduler import stop_trading_scheduler
    from app.modules.dms.scheduler import stop_dms_scheduler
    from app.modules.market_data_v1.scheduler import stop_candle_load_scheduler
    from app.modules.corporate_actions.scheduler import stop_corporate_actions_scheduler
    from app.core.background_jobs.worker import stop_embedded_lane_workers

    await _stop_background_task("portfolio", stop_portfolio_scheduler())
    await _stop_background_task("trading", stop_trading_scheduler())
    await _stop_background_task("dms", stop_dms_scheduler())
    await _stop_background_task("candle_load", stop_candle_load_scheduler())
    await _stop_background_task("corporate_actions", stop_corporate_actions_scheduler())
    if settings.WORKER_EMBEDDED_ENABLED:
        await _stop_background_task("lane_workers", stop_embedded_lane_workers())

    try:
        from app.modules.tinvest.http_client import close_shared_http_client
        await close_shared_http_client()
    except Exception as e:
        system_log.error("Ошибка закрытия shared HTTP client: %s", e)


@asynccontextmanager
async def api_lifespan(app: FastAPI) -> AsyncIterator[None]:
    system_log.info("API процесс запускается")
    await _start_api_background()
    system_log.info("API готов принимать запросы")
    yield
    system_log.info("API процесс останавливается")
    await _stop_api_background()


@asynccontextmanager
async def ws_lifespan(app: FastAPI) -> AsyncIterator[None]:
    system_log.info("WS процесс запускается (port=%s)", settings.WS_PORT)
    yield
    system_log.info("WS процесс остановлен")


def _apply_common_middleware(app: FastAPI) -> None:
    from app.core.exceptions import database_exception_handler, validation_exception_handler
    from app.core.rest_logging_middleware import RestLoggingMiddleware

    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_middleware(RestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_api_routers(app: FastAPI) -> None:
    from app.modules.auth.router import router as auth_router
    from app.modules.tinvest.router import router as tinvest_router
    from app.modules.robots.router import router as robots_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.recommendations.router import router as recommendations_router
    from app.modules.market_data.router import router as market_router
    from app.modules.settings.router import router as apikey_router
    from app.modules.dictionary.router import router as dictionary_router
    from app.modules.dashboard.router import router as dashboard_router
    from app.modules.dms.router import router as dms_router
    from app.modules.market_data_v1.router import router as market_data_v1_router
    from app.modules.bybit.router import router as bybit_router

    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(tinvest_router, prefix="/api/tinvest", tags=["tinvest"])
    app.include_router(robots_router, prefix="/api", tags=["robots"])
    app.include_router(analytics_router, prefix="/api", tags=["analytics"])
    app.include_router(recommendations_router, prefix="/api", tags=["recommendations"])
    app.include_router(market_router, prefix="/api", tags=["market"])
    app.include_router(apikey_router, prefix="/api", tags=["apikey"])
    app.include_router(dictionary_router, prefix="/api", tags=["dictionary"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    app.include_router(dms_router, prefix="/api", tags=["dms"])
    app.include_router(market_data_v1_router, prefix="/api")
    app.include_router(bybit_router, prefix="/api")


def create_api_app() -> FastAPI:
    app = FastAPI(
        title="Ganaly API",
        description="REST API для торговых роботов",
        version="2.0.0",
        lifespan=api_lifespan,
    )
    _apply_common_middleware(app)
    _register_api_routers(app)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "api", "version": "2.0.0"}

    @app.get("/api/scheduler/portfolio/run")
    async def force_portfolio_update():
        from app.modules.robots.portfolio_updater.scheduler import run_portfolio_update_once
        return await run_portfolio_update_once()

    @app.get("/api/scheduler/trading/run/{robot_id}")
    async def force_trading_robot(robot_id: int):
        from app.modules.robots.trading.scheduler import force_run_trading_robot
        return await force_run_trading_robot(robot_id)

    return app


def create_ws_app() -> FastAPI:
    from app.modules.robots.live_ws import router as live_ws_router

    app = FastAPI(
        title="Ganaly Live WS",
        description="WebSocket gateway для live-мониторинга роботов",
        version="2.0.0",
        lifespan=ws_lifespan,
    )
    _apply_common_middleware(app)
    app.include_router(live_ws_router, tags=["live"])

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "ws", "version": "2.0.0"}

    return app


def create_app() -> FastAPI:
    """Backward-compatible default: API-only app."""
    return create_api_app()


app = create_app()
