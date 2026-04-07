# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging_config import setup_logging, get_logger
setup_logging()

system_log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    system_log.info("=" * 60)
    system_log.info("🚀 ПРИЛОЖЕНИЕ ЗАПУСКАЕТСЯ")
    system_log.info("=" * 60)

    # Запуск портфельного планировщика
    try:
        from app.modules.robots.portfolio_updater.scheduler import start_portfolio_scheduler
        await start_portfolio_scheduler()
        system_log.info("✅ Портфельный планировщик запущен")
    except Exception as e:
        system_log.error(f"❌ Ошибка запуска портфельного планировщика: {e}")

    # Запуск торгового планировщика
    try:
        from app.modules.robots.trading.scheduler import start_trading_scheduler
        await start_trading_scheduler()
        system_log.info("✅ Торговый планировщик запущен")
    except Exception as e:
        system_log.error(f"❌ Ошибка запуска торгового планировщика: {e}")

    yield

    # Shutdown
    system_log.info("=" * 60)
    system_log.info("🛑 ПРИЛОЖЕНИЕ ОСТАНАВЛИВАЕТСЯ")
    system_log.info("=" * 60)

    # Остановка планировщиков
    try:
        from app.modules.robots.portfolio_updater.scheduler import stop_portfolio_scheduler
        await stop_portfolio_scheduler()
    except Exception as e:
        system_log.error(f"Ошибка остановки портфельного планировщика: {e}")

    try:
        from app.modules.robots.trading.scheduler import stop_trading_scheduler
        await stop_trading_scheduler()
    except Exception as e:
        system_log.error(f"Ошибка остановки торгового планировщика: {e}")

    system_log.info("✅ Приложение остановлено")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ganaly API",
        description="API для торговых роботов",
        version="2.0.0",
        lifespan=lifespan
    )

    # REST logging middleware (до CORS, чтобы логировать все запросы)
    from app.core.rest_logging_middleware import RestLoggingMiddleware
    app.add_middleware(RestLoggingMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Регистрация роутеров
    from app.modules.auth.router import router as auth_router
    from app.modules.tinvest.router import router as tinvest_router
    from app.modules.robots.router import router as robots_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.robots.live_ws import router as live_ws_router
    from app.modules.market_data.router import router as market_router

    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(tinvest_router, prefix="/api/tinvest", tags=["tinvest"])
    app.include_router(robots_router, prefix="/api", tags=["robots"])
    app.include_router(analytics_router, prefix="/api", tags=["analytics"])
    app.include_router(live_ws_router, tags=["live"])
    app.include_router(market_router, prefix="/api", tags=["market"])

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "2.0.0"}

    @app.get("/api/scheduler/portfolio/run")
    async def force_portfolio_update():
        """Принудительный запуск портфельного обновления"""
        from app.modules.robots.portfolio_updater.scheduler import run_portfolio_update_once
        result = await run_portfolio_update_once()
        return result

    @app.get("/api/scheduler/trading/run/{robot_id}")
    async def force_trading_robot(robot_id: int):
        """Принудительный запуск торгового робота"""
        from app.modules.robots.trading.scheduler import force_run_trading_robot
        result = await force_run_trading_robot(robot_id)
        return result

    return app


app = create_app()
