"""
Фабрика торговых сессий — единая точка создания live/backtest ядра.

По mode выбираются источник данных и исполнение:
- LIVE: T-Invest broker + WebSocket replay в price_queue
- BACKTEST: SimBacktestBrokerFacade + historical bar replay
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.modules.robots.trading.contracts import ExecutionMode

if TYPE_CHECKING:
    from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
    from app.modules.robots.trading.session import TradingSession


def create_trading_session(
    mode: ExecutionMode = ExecutionMode.LIVE,
    *,
    sim_broker: Optional["SimBacktestBrokerFacade"] = None,
    allowed_figis_by_date: Optional[Dict[str, List[str]]] = None,
    **kwargs: Any,
) -> "TradingSession":
    """Создаёт TradingSession с нужным mode (live или backtest)."""
    if mode == ExecutionMode.BACKTEST:
        from app.modules.robots.trading.session_backtest import BacktestTradingSession

        if sim_broker is None:
            raise ValueError("sim_broker обязателен для mode=BACKTEST")
        return BacktestTradingSession(
            sim_broker=sim_broker,
            allowed_figis_by_date=allowed_figis_by_date or {},
            **kwargs,
        )

    from app.modules.robots.trading.session import TradingSession

    return TradingSession(mode=ExecutionMode.LIVE, **kwargs)


__all__ = ["create_trading_session"]
