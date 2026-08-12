"""Single trading cycle for robots v2 (paper + live via ExecutionService)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.robots.trading.contracts import Candle, OrderIntent
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.execution import ExecutionService
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.strategy.runtime import strategy_runtime
from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot, StrategyContext


async def run_trading_cycle(
    *,
    robot_id: int,
    user_id: int,
    config: TradingRobotConfigV4,
    universe: list[str],
    ledger: PaperLedger,
    risk: RiskEngine,
    prices: dict[str, float],
    candle_history: dict[str, list[Candle]],
    session_id: int,
    cycle_number: int,
    triggered_by: str = "poll",
    allow_short: bool = False,
    execution: ExecutionService | None = None,
    order_flow: dict[str, OrderFlowSnapshot] | None = None,
    ws_healthy: bool = True,
) -> dict[str, Any]:
    _ = user_id
    decisions: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []

    exec_svc = execution or ExecutionService(
        mode="paper",
        robot_id=robot_id,
        ledger=ledger,
        slippage_pct=config.risk.slippage_pct,
    )

    positions_dict = ledger.positions_dict(prices)
    equity = ledger.mark_equity(prices)

    # 1. Exits-first (SL/TP)
    open_list = ledger.open_positions_list(prices)
    exit_intents = risk.evaluate_exits(open_list, prices)
    for intent in exit_intents:
        px = float(intent.price or prices.get(intent.figi, 0))
        result = await exec_svc.execute_intent(intent, last_price=px)
        if result.status in ("filled", "submitted"):
            risk.record_realized_pnl(result.pnl)
            fills.append({
                "ticker": result.ticker,
                "kind": "exit_sl_tp",
                "side": result.side,
                "reason": intent.reason,
                "pnl": result.pnl,
                "status": result.status,
            })

    positions_dict = ledger.positions_dict(prices)
    equity = ledger.mark_equity(prices)

    # 2. Strategy signals
    ctx = StrategyContext(
        robot_id=robot_id,
        cycle_id=uuid4(),
        config=config.strategy,
        universe=universe,
        last_price=prices,
        candles=candle_history,
        atr={},
        open_positions=list(positions_dict.values()),
        mode=config.core.mode,
        now=datetime.now(timezone.utc),
        triggered_by=triggered_by,  # type: ignore[arg-type]
        instrument_type=config.core.instrument_type,
        allow_short=allow_short,
        order_flow=order_flow,
        ws_healthy=ws_healthy,
    )
    signals = strategy_runtime.evaluate(session_id, ctx)

    for signal in signals:
        await event_bus.publish(robot_id, "signal", {
            "ticker": signal.secid,
            "side": signal.side,
            "reason": signal.reason,
        })

        if signal.side == "CLOSE":
            ticker = str(signal.secid or "").upper()
            pos = ledger.positions.get(ticker)
            if pos:
                px = prices.get(ticker, pos.avg_entry_price)
                intent = OrderIntent(
                    kind="exit_strategy",
                    figi=ticker,
                    side="SELL" if pos.is_long else "BUY",
                    quantity=float(pos.quantity),
                    price=px,
                    reduce_only=True,
                    reason=signal.reason or "exit_strategy",
                )
                result = await exec_svc.execute_intent(intent, last_price=px)
                if result.status in ("filled", "submitted"):
                    risk.record_realized_pnl(result.pnl)
                    fills.append({
                        "ticker": ticker,
                        "kind": "exit_strategy",
                        "side": result.side,
                        "reason": signal.reason,
                        "pnl": result.pnl,
                        "status": result.status,
                    })
            continue

        if not risk.session_state.accept_new_entries and signal.side in ("BUY", "SELL"):
            pos = ledger.positions.get(str(signal.secid or "").upper())
            is_reduce = (
                (signal.side == "SELL" and pos is not None and pos.is_long)
                or (signal.side == "BUY" and pos is not None and not pos.is_long)
            )
            if not is_reduce:
                decisions.append({
                    "code": "ENTRIES_PAUSED",
                    "message": "New entries paused",
                    "ticker": signal.secid,
                    "allow": False,
                })
                continue

        risk_decision, audit = risk.pre_trade(
            signal,
            cash=ledger.cash,
            equity=equity,
            positions=positions_dict,
        )
        decisions.append(audit.__dict__)
        if not risk_decision.allow:
            await event_bus.publish(robot_id, "decision", {
                "code": audit.code, "message": audit.message, "ticker": audit.ticker,
            })
            continue

        qty = int(risk_decision.quantity or 0)
        if qty <= 0:
            continue
        ticker = str(signal.secid or "").upper()
        price = float(signal.price_at_signal or prices.get(ticker, 0))
        if price <= 0:
            continue
        intent = risk.build_entry_intent(signal, qty, price)
        result = await exec_svc.execute_intent(intent, last_price=price)
        if result.status in ("filled", "submitted"):
            fills.append({
                "ticker": ticker,
                "kind": "entry",
                "side": result.side,
                "qty": qty,
                "price": result.price,
                "pnl": result.pnl,
                "status": result.status,
            })
        else:
            decisions.append({
                "code": result.reason or "EXEC_REJECTED",
                "message": result.reason or "rejected",
                "ticker": ticker,
                "allow": False,
            })

    await event_bus.publish(robot_id, "cycle", {
        "cycleNumber": cycle_number,
        "equity": ledger.mark_equity(prices),
        "positions": len(ledger.positions),
        "signals": len(signals),
        "mode": exec_svc.mode,
    })

    return {"decisions": decisions, "fills": fills, "signals": len(signals)}
