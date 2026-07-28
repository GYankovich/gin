"""
LiveExecutionService — единая точка выставления заявок LIVE (BRD-ARCH-04 §4.3).

Оборачивает проверенную логику Stage6 (risk gates, slippage, post_order).
Backtest: тот же сервис, broker = SimBacktestBrokerFacade.

Все place (включая SL/TP exits) идут через submit_intents / submit_signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


@runtime_checkable
class ExecutionService(Protocol):
    async def submit_signals(
        self,
        signals: List[Dict[str, Any]],
        *,
        risk_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]: ...

    async def submit_intents(
        self,
        intents: List[OrderIntent],
        *,
        risk_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]: ...

    async def poll_order_status(self, order_id: str) -> Dict[str, Any]: ...


@dataclass
class LiveExecutionContext:
    """Параметры сессии для построения Stage6 / ExecutionService."""

    db: Any
    schema: str
    broker: Any
    account_id: str
    robot_id: int
    token_id: int
    user_id: int
    log_func: Optional[Callable[[str], None]] = None
    daily_trade_counter: Optional[Dict[str, int]] = None
    last_trade_by_figi: Optional[Dict[str, datetime]] = None
    in_flight_orders: Optional[Dict[str, str]] = None
    cost_params: Optional[Dict[str, float]] = None
    account_positions: Optional[Dict[str, float]] = None
    now_fn: Optional[Callable[[], datetime]] = None
    broker_type: str = "tinvest"


class LiveExecutionService:
    """LIVE (и BACKTEST-sim): submit_intents / submit_signals + poll_order_status."""

    def __init__(self, ctx: LiveExecutionContext):
        self._ctx = ctx
        self._stage6: Optional[Stage6Orders] = None

    @property
    def broker_type(self) -> str:
        return str(self._ctx.broker_type or "tinvest")

    def _stage(self) -> Stage6Orders:
        if self._stage6 is None:
            c = self._ctx
            self._stage6 = Stage6Orders(
                c.db,
                c.schema,
                c.broker,
                c.account_id,
                c.robot_id,
                c.token_id,
                c.user_id,
                c.log_func,
                daily_trade_counter=c.daily_trade_counter,
                last_trade_by_figi=c.last_trade_by_figi,
                in_flight_orders=c.in_flight_orders,
                cost_params=c.cost_params,
                account_positions=c.account_positions,
                now_fn=c.now_fn,
            )
        return self._stage6

    async def submit_signals(
        self,
        signals: List[Dict[str, Any]],
        *,
        risk_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not signals:
            return []
        intents = [OrderIntent.from_strategy_signal(s) for s in signals]
        return await self.submit_intents(intents, risk_params=risk_params)

    async def submit_intents(
        self,
        intents: List[OrderIntent],
        *,
        risk_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not intents:
            return []
        return await self._stage().execute_intents(intents, risk_params=risk_params or {})

    async def poll_order_status(self, order_id: str) -> Dict[str, Any]:
        return await self._stage().update_order_status(order_id)

    @staticmethod
    def map_execution_status_to_trade_status(execution_status: str, *, closing: bool = False) -> str:
        return Stage6Orders.map_execution_status_to_trade_status(execution_status, closing=closing)

    def sync_counters_from_stage(self) -> None:
        """После submit — перенести счётчики сделок обратно в сессию.

        Shared-by-reference maps (session book / counters) are already mutated
        in place by Stage6 — clearing them would wipe live updates.
        """
        st = self._stage6
        if st is None:
            return
        if (
            self._ctx.daily_trade_counter is not None
            and self._ctx.daily_trade_counter is not st._daily_trade_counter
        ):
            self._ctx.daily_trade_counter.clear()
            self._ctx.daily_trade_counter.update(st._daily_trade_counter)
        if (
            self._ctx.last_trade_by_figi is not None
            and self._ctx.last_trade_by_figi is not st._last_trade_by_figi
        ):
            self._ctx.last_trade_by_figi.clear()
            self._ctx.last_trade_by_figi.update(st._last_trade_by_figi)
        if (
            self._ctx.account_positions is not None
            and self._ctx.account_positions is not st.account_positions
        ):
            self._ctx.account_positions.clear()
            self._ctx.account_positions.update(st.account_positions)
        if (
            self._ctx.in_flight_orders is not None
            and self._ctx.in_flight_orders is not st._in_flight_orders
        ):
            self._ctx.in_flight_orders.clear()
            self._ctx.in_flight_orders.update(st._in_flight_orders)


def build_live_execution_service(
    *,
    db: Any,
    schema: str,
    broker: Any,
    account_id: str,
    robot_id: int,
    token_id: int,
    user_id: int,
    log_func: Optional[Callable[[str], None]] = None,
    daily_trade_counter: Optional[Dict[str, int]] = None,
    last_trade_by_figi: Optional[Dict[str, datetime]] = None,
    in_flight_orders: Optional[Dict[str, str]] = None,
    cost_params: Optional[Dict[str, float]] = None,
    account_positions: Optional[Dict[str, float]] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
    broker_type: str = "tinvest",
) -> LiveExecutionService:
    ctx = LiveExecutionContext(
        db=db,
        schema=schema,
        broker=broker,
        account_id=account_id,
        robot_id=robot_id,
        token_id=token_id,
        user_id=user_id,
        log_func=log_func,
        daily_trade_counter=daily_trade_counter,
        last_trade_by_figi=last_trade_by_figi,
        in_flight_orders=in_flight_orders,
        cost_params=cost_params,
        account_positions=account_positions,
        now_fn=now_fn,
        broker_type=broker_type,
    )
    return LiveExecutionService(ctx)


def execution_service_for_session(session: Any) -> LiveExecutionService:
    """Фабрика из TradingSession / BacktestTradingSession."""
    from app.modules.robots.trading.brokers.routing import normalize_broker_type

    broker_type = normalize_broker_type(
        (getattr(session, "config", None) or {}).get("broker_type")
        if getattr(session, "config", None)
        else getattr(session, "broker_type", None)
    )
    return build_live_execution_service(
        db=session.db,
        schema=session.schema,
        broker=session.broker,
        account_id=session.account_id or "",
        robot_id=int(session.robot_id),
        token_id=int(session.token_id),
        user_id=int(session.user_id),
        log_func=getattr(session, "_write_log", None),
        daily_trade_counter=getattr(session, "_daily_trade_counter", None),
        last_trade_by_figi=getattr(session, "_last_trade_by_figi", None),
        in_flight_orders=getattr(session, "_in_flight_orders", None),
        cost_params=getattr(session, "cost_params", None),
        account_positions=getattr(session, "account_positions", None),
        now_fn=getattr(session, "_now", None),
        broker_type=broker_type,
    )


__all__ = [
    "ExecutionService",
    "LiveExecutionContext",
    "LiveExecutionService",
    "build_live_execution_service",
    "execution_service_for_session",
]
