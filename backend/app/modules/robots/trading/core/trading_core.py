"""
Один торговый цикл: сигналы, риск-гейты, исполнение.

Вынесено из TradingSession (BRD-ARCH-04 этап 1). Host — TradingSession или BacktestTradingSession.
Позже: разделить generate vs execute на TradingCore + ExecutionService.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, TYPE_CHECKING

from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.grain_seed_orchestrator import filter_grain_seed_signals

if TYPE_CHECKING:
    from app.modules.robots.trading.session import TradingSession


async def run_single_trading_cycle(host: "TradingSession", cycle_count: int) -> None:
    """
    Один торговый цикл (live: _trading_worker; backtest: на каждый бар).

    `host` — сессия с API цикла (portfolio, signals, orders, persistence).
    """
    if host.db and host.mode != ExecutionMode.BACKTEST:
        host.db.rollback()
    cycle_start = host._now()
    host._reset_cycle_api_counts()
    host._cycle_id = await host.create_run_cycle(
        host.db,
        host.schema,
        host.robot_id,
        execution_log_id=host._execution_log_id,
        context={"cycle": cycle_count, "strategy": host.strategy_name, "broker_type": host.broker_type},
    )

    host._write_log(f"\n🔄 [TRADE] ЦИКЛ {cycle_count}")

    await host.refresh_config()
    await host._refresh_account_positions()

    if host.strategy_name == "grain_seed":
        await host._update_portfolio()

    prices = await host._get_latest_prices_from_queue()
    queue_size = host.price_queue.qsize()
    if queue_size > 0:
        host._write_log(f"📊 Очередь цен: {queue_size} сообщений")

    if prices:
        await host._update_positions()

        await host._apply_live_funding_if_due(prices)

        if host.strategy_name == "grain_seed":
            await host._apply_grain_seed_orchestration()

        orch = host._grain_seed_orchestration
        flatten_trades: List[Dict[str, Any]] = []
        broker_type = str(
            getattr(host, "broker_type", None)
            or ((getattr(host, "config", None) or {}).get("broker_type"))
            or "tinvest"
        ).strip().lower()
        flatten_default = False if broker_type == "bybit" else True
        use_force_flatten = (
            host.strategy_name == "grain_seed"
            and orch is not None
            and orch.allow_only_reduce
            and bool(host.strategy_params.get("force_market_flatten", flatten_default))
            and bool(str(host.strategy_params.get("force_close_time_msk") or "").strip())
        )
        if use_force_flatten:
            await host._grain_seed_cancel_open_orders_on_broker()
            flatten_trades, closed = await host._grain_seed_market_close_open_positions(prices)
        else:
            closed = await host._check_stop_loss(prices)

        for item in closed:
            if item.get("order_id"):
                host._pending_position_closures[item["order_id"]] = item
                await host._put_to_queue_with_limit(
                    host.order_queue,
                    {
                        "type": "order_status",
                        "order_id": item["order_id"],
                        "status": "pending_close",
                        "timestamp": host._now().isoformat(),
                    },
                )

        # --- Core: signals (Stage5 + risk gates) ---
        signals = await host._generate_signals(prices)
        if host.strategy_name == "grain_seed" and host._grain_seed_orchestration is not None:
            signals = filter_grain_seed_signals(signals, host._grain_seed_orchestration)
        if await host._is_daily_loss_limit_breached():
            host._write_log("🛑 [TRADE] Достигнут лимит max_daily_loss, новые сигналы пропущены")
            signals = []
        if signals:
            await host.save_signals(host.db, host.schema, host.robot_id, signals)
            host._write_log(f"   💾 Сохранено сигналов: {len(signals)}")
            for s in signals:
                decision_id = await host.save_decision(
                    host.db,
                    host.schema,
                    host.robot_id,
                    stage="stage5_signals",
                    decision_type="signal",
                    decision=str(s.get("signal", "")).lower(),
                    reason_code=None,
                    payload=s,
                    execution_log_id=host._execution_log_id,
                    cycle_id=host._cycle_id,
                    figi=s.get("figi"),
                )
                await host._publish_live_event({
                    "type": "signal",
                    "robot_id": host.robot_id,
                    "figi": s.get("figi"),
                    "signal_type": str(s.get("signal", "")).lower(),
                    "price": s.get("price"),
                    "target_price": s.get("target_price"),
                    "indicators": s.get("indicators", {}),
                    "decision_id": decision_id,
                    "run_id": host._execution_log_id,
                    "cycle_id": host._cycle_id,
                    "time": host._now().isoformat(),
                })

        # --- Execution: LiveExecutionService via host._execute_orders ---
        trades = await host._execute_orders(signals)
        if flatten_trades and host.db:
            ft_ids = await host.save_trades(host.db, host.schema, host.robot_id, flatten_trades)
            host._write_log(f"   💾 [grain_seed] Сохранено принудительных заявок: {len(ft_ids)}")
            for t in flatten_trades:
                await host._publish_live_event({
                    "type": "order",
                    "robot_id": host.robot_id,
                    "figi": t.get("figi"),
                    "side": t.get("side"),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "status": t.get("status"),
                    "reason": "grain_seed_force_flatten",
                    "time": host._now().isoformat(),
                })

        if trades:
            trade_ids = await host.save_trades(host.db, host.schema, host.robot_id, trades)
            host._write_log(f"   💾 Сохранено сделок: {len(trade_ids)}")
            for idx, t in enumerate(trades):
                trade_id = trade_ids[idx] if idx < len(trade_ids) else None
                order_decision_id = await host.save_decision(
                    host.db,
                    host.schema,
                    host.robot_id,
                    stage="stage6_orders",
                    decision_type="order",
                    decision=str(t.get("status", "unknown")),
                    reason_code=t.get("error"),
                    payload=t,
                    execution_log_id=host._execution_log_id,
                    cycle_id=host._cycle_id,
                    figi=t.get("figi"),
                )
                await host.save_order_event(
                    host.db,
                    host.schema,
                    host.robot_id,
                    order_id=t.get("order_id"),
                    status=str(t.get("status", "unknown")),
                    event_type="created",
                    trade_id=trade_id,
                    payload=t,
                )
                event_type = "order" if t.get("status") not in {"skipped"} else "skipped"
                await host._publish_live_event({
                    "type": event_type,
                    "robot_id": host.robot_id,
                    "figi": t.get("figi"),
                    "side": t.get("side"),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "status": t.get("status"),
                    "reason": t.get("error"),
                    "decision_id": order_decision_id,
                    "run_id": host._execution_log_id,
                    "cycle_id": host._cycle_id,
                    "time": host._now().isoformat(),
                })
            executed_signal_ids = [
                int(t["signal_id"])
                for t in trades
                if t.get("signal_id") and t.get("status") not in {"failed", "skipped"}
            ]
            marked = await host.mark_signals_executed(host.db, host.schema, executed_signal_ids)
            if marked:
                host._write_log(f"   ✅ Отмечено исполненных сигналов: {marked}")

        host.stats["signals_generated"] += len(signals)
        host.stats["orders_placed"] += len(trades) + len(flatten_trades)

    await host._process_order_statuses()

    elapsed = (host._now() - cycle_start).total_seconds()
    if not host._skip_cycle_sleep:
        wait_time = max(0, host.update_interval - elapsed)
        if wait_time > 0:
            host._write_log(f"⏱️ [TRADE] Ожидание {wait_time:.1f} сек...")
            await asyncio.sleep(wait_time)


class TradingCore:
    """Тонкая обёртка; позже получит facade/strategy/risk без привязки к session."""

    async def run_cycle(self, host: "TradingSession", cycle_count: int) -> None:
        await run_single_trading_cycle(host, cycle_count)


__all__ = ["TradingCore", "run_single_trading_cycle"]
