"""
Один торговый цикл: exits → signals → risk → execute → persist.

Вынесено из TradingSession (BRD-ARCH-04 этап 1). Host — TradingSession или BacktestTradingSession.
Цикл: plan SL/TP intents → strategy signals → submit_intents (единственный post_order).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, TYPE_CHECKING

from app.modules.robots.trading.contracts import ExecutionMode, OrderIntent
from app.modules.robots.trading.grain_seed_orchestrator import filter_grain_seed_signals

if TYPE_CHECKING:
    from app.modules.robots.trading.session import TradingSession


async def run_single_trading_cycle(host: "TradingSession", cycle_count: int) -> None:
    """
    Один торговый цикл (live: _trading_worker; backtest: на каждый бар).

    Явный pipeline:
      exits (Risk/Stage4) → signals (Strategy/Stage5) → execute (LiveExecutionService)
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
    health_ok = True
    if hasattr(host, "_check_live_account_health"):
        health_ok = await host._check_live_account_health()

    if host.strategy_name == "grain_seed":
        await host._update_portfolio()

    prices = await host._get_latest_prices_from_queue()
    queue_size = host.price_queue.qsize()
    if queue_size > 0:
        host._write_log(f"📊 Очередь цен: {queue_size} сообщений")

    if prices and health_ok:
        await host._update_positions()
        await host._reconcile_open_positions_with_broker()

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

        exit_intents: List[OrderIntent] = []
        if use_force_flatten:
            await host._grain_seed_cancel_open_orders_on_broker()
            flatten_trades, closed_meta = await host._grain_seed_market_close_open_positions(prices)
            # Legacy flatten still returns placed trades; register pending from meta.
            for item in closed_meta:
                if item.get("order_id"):
                    host.symbol_guard().register_pending_close(
                        str(item["order_id"]),
                        item,
                    )
                    await host._put_to_queue_with_limit(
                        host.order_queue,
                        {
                            "type": "order_status",
                            "order_id": item["order_id"],
                            "status": "pending_close",
                            "timestamp": host._now().isoformat(),
                        },
                    )
        else:
            # --- Risk exits (Stage4 decision only) ---
            exit_intents = await host._plan_exit_intents(prices)

        # --- Strategy signals (Stage5) ---
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
                    "intent_source": s.get("intent_source") or (
                        "exit_strategy" if str(s.get("signal", "")).upper() == "SELL" else "entry"
                    ),
                    "decision_id": decision_id,
                    "run_id": host._execution_log_id,
                    "cycle_id": host._cycle_id,
                    "time": host._now().isoformat(),
                })

        # --- Execute: single path for exits + entries ---
        entry_intents = [OrderIntent.from_strategy_signal(s) for s in signals]
        all_intents = list(exit_intents) + entry_intents
        trades = await host._execute_intents(all_intents) if all_intents else []

        for t in trades:
            if str(t.get("intent_source") or "") == "exit_sl_tp" and t.get("order_id"):
                host.symbol_guard().register_pending_close(
                    str(t["order_id"]),
                    {
                        "trade_id": t.get("trade_id"),
                        "order_id": t.get("order_id"),
                        "figi": t.get("figi"),
                        "exit_price": t.get("exit_price") or t.get("price"),
                        "reason": t.get("reason"),
                        "profit": t.get("profit"),
                    },
                )
                await host._put_to_queue_with_limit(
                    host.order_queue,
                    {
                        "type": "order_status",
                        "order_id": t["order_id"],
                        "status": "pending_close",
                        "timestamp": host._now().isoformat(),
                    },
                )

        if flatten_trades and host.db:
            ft_ids = await host.save_trades(host.db, host.schema, host.robot_id, flatten_trades)
            host._write_log(f"   💾 [grain_seed] Сохранено принудительных заявок: {len(ft_ids)}")
            try:
                from app.modules.portfolio.order_registry import (
                    insert_robot_orders_batch,
                    resolve_portfolio_account_pk,
                )

                broker_acct = str(getattr(host, "account_id", None) or "").strip()
                uid = getattr(host, "user_id", None)
                if broker_acct and uid:
                    pa_id = resolve_portfolio_account_pk(
                        host.db,
                        user_id=int(uid),
                        broker_account_id=broker_acct,
                    )
                    if pa_id:
                        insert_robot_orders_batch(
                            host.db,
                            portfolio_account_id=int(pa_id),
                            robot_id=int(host.robot_id),
                            trades=flatten_trades,
                        )
            except Exception:
                pass
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
                    "intent_source": "flatten",
                    "time": host._now().isoformat(),
                })

        if trades:
            trade_ids = await host.save_trades(host.db, host.schema, host.robot_id, trades)
            host._write_log(f"   💾 Сохранено сделок: {len(trade_ids)}")
            try:
                from app.modules.portfolio.order_registry import (
                    insert_robot_orders_batch,
                    resolve_portfolio_account_pk,
                )

                broker_acct = str(getattr(host, "account_id", None) or "").strip()
                uid = getattr(host, "user_id", None)
                if broker_acct and uid and host.db:
                    pa_id = resolve_portfolio_account_pk(
                        host.db,
                        user_id=int(uid),
                        broker_account_id=broker_acct,
                    )
                    if pa_id:
                        n_ao = insert_robot_orders_batch(
                            host.db,
                            portfolio_account_id=int(pa_id),
                            robot_id=int(host.robot_id),
                            trades=trades,
                        )
                        if n_ao:
                            host._write_log(f"   💾 portfolio_orders: +{n_ao}")
            except Exception as ao_exc:
                host._write_log(f"   ⚠️ portfolio_orders write failed: {ao_exc}")
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
                    "reason": t.get("error") or t.get("reason"),
                    "intent_source": t.get("intent_source"),
                    "signal_id": t.get("signal_id"),
                    "trade_id": trade_id,
                    "order_id": t.get("order_id"),
                    "decision_id": order_decision_id,
                    "run_id": host._execution_log_id,
                    "cycle_id": host._cycle_id,
                    "time": host._now().isoformat(),
                })
            marked = 0
            for idx, t in enumerate(trades):
                sid = t.get("signal_id")
                if not sid or t.get("status") in {"failed", "skipped"}:
                    continue
                trade_id = trade_ids[idx] if idx < len(trade_ids) else None
                marked += await host.mark_signals_executed(
                    host.db,
                    host.schema,
                    [int(sid)],
                    executed_trade_id=int(trade_id) if trade_id is not None else None,
                )
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
