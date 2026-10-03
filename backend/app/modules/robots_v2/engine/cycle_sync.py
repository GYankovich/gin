"""Synchronous paper trading cycle for bar-replay backtests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.trading_core.contracts import Candle, OrderIntent
from app.modules.trading_core.costs import calculate_take_profit_price
from app.modules.trading_core.risk.manager import decide_take_profit_order
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.execution import ExecutionService
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.resting_orphans import select_orphan_resting_tickers
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.strategy.helpers import (
    allow_strategy_exit_below_break_even,
    block_exit_below_break_even,
)
from app.modules.robots_v2.strategy.runtime import StrategyRuntime
from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot, StrategyContext


def _submit_intent(
    exec_svc: ExecutionService,
    intent: OrderIntent,
    last_price: float,
    *,
    defer_market: bool,
    deferred: list[OrderIntent],
):
    """Place non-marketable LIMIT now; defer marketable fills to the next bar open."""
    if not defer_market:
        return exec_svc.execute_intent_sync(intent, last_price=last_price)
    order_type = str(getattr(intent, "order_type", None) or "MARKET").upper()
    if order_type == "LIMIT" and not exec_svc._limit_would_fill(
        str(intent.side or "BUY"),
        last_price,
        float(intent.price or 0),
    ):
        return exec_svc.execute_intent_sync(intent, last_price=last_price)
    deferred.append(intent)
    return None


def run_paper_cycle_sync(
    *,
    robot_id: int,
    config: TradingRobotConfigV4,
    universe: list[str],
    ledger: PaperLedger,
    risk: RiskEngine,
    prices: dict[str, float],
    candle_history: dict[str, list[Candle]],
    session_id: int,
    cycle_number: int,
    execution: ExecutionService,
    runtime: StrategyRuntime,
    triggered_by: str = "bar_close",
    allow_short: bool = False,
    now: datetime | None = None,
    order_flow: dict[str, OrderFlowSnapshot] | None = None,
    defer_market_fills: bool = True,
) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    fills: list[dict[str, Any]] = []
    deferred: list[OrderIntent] = []
    exec_svc = execution

    for poll_result in exec_svc.poll_resting_fills_sync(last_prices=prices):
        if poll_result.status == "filled":
            risk.record_realized_pnl(poll_result.pnl)
            fills.append({
                "ticker": poll_result.ticker,
                "kind": poll_result.kind or "exit_sl_tp",
                "side": poll_result.side,
                "reason": poll_result.reason,
                "pnl": poll_result.pnl,
                "status": poll_result.status,
            })

    positions_dict = ledger.positions_dict(prices)
    open_list = ledger.open_positions_list(prices)
    exit_intents = risk.evaluate_exits(open_list, prices)
    exit_tickers = {
        str(getattr(i, "figi", "") or "").upper()
        for i in exit_intents
        if str(getattr(i, "reason", "") or "") == "take_profit"
    }
    for ticker, ro in list(getattr(exec_svc, "_resting", {}).items()):
        if str(ro.reason or "") not in ("take_profit", "broker_sync") and str(ro.kind or "") != "exit_sl_tp":
            continue
        if ticker.upper() in exit_tickers:
            continue
        pos = next(
            (p for p in open_list if str(p.get("ticker") or p.get("figi") or "").upper() == ticker.upper()),
            None,
        )
        if pos is None:
            continue
        entry = float(pos.get("entry_price") or 0)
        px = float(prices.get(ticker.upper()) or pos.get("current_price") or 0)
        is_long = str(pos.get("side", "")).lower() in {"buy", "long"}
        if entry <= 0 or px <= 0:
            continue
        tp = calculate_take_profit_price(
            entry,
            float(config.risk.take_profit_pct),
            is_long=is_long,
            broker_commission_rate=float(config.risk.broker_commission_pct) / 100.0,
            ndfl_rate=float(config.risk.tax_pct) / 100.0,
        )
        armed = decide_take_profit_order(
            entry_price=entry,
            current_price=px,
            take_profit=tp,
            is_long=is_long,
            risk_params=getattr(risk, "_risk_dict", {}) or {},
        )
        if armed is None:
            exec_svc.cancel_resting_local(ticker)

    held_tickers = {
        str(p.get("ticker") or p.get("figi") or "").upper()
        for p in open_list
        if str(p.get("ticker") or p.get("figi") or "").strip()
    }
    for orphan_t in select_orphan_resting_tickers(
        getattr(exec_svc, "_resting", {}) or {},
        held_tickers=held_tickers,
        wanted_entries=set(),
        scope="exit",
    ):
        exec_svc.cancel_resting_local(orphan_t)

    for intent in exit_intents:
        ticker_u = str(intent.figi or "").upper()
        mark = float(prices.get(ticker_u) or 0)
        limit_or_intent_px = float(intent.price or 0)
        meta = getattr(intent, "meta", None) or {}
        order_type = str(getattr(intent, "order_type", None) or "MARKET").upper()
        if str(getattr(intent, "reason", "") or "") == "take_profit" and mark > 0:
            entry_m = float(meta.get("entry_price") or 0)
            tp_m = float(meta.get("take_profit") or 0)
            if entry_m > 0 and tp_m > 0:
                span = abs(tp_m - entry_m)
                if span > 0 and (
                    mark > tp_m * 1.02
                    or abs(mark - entry_m) > max(span * 3.0, entry_m * 0.05)
                ):
                    continue
                if order_type == "MARKET" and mark < tp_m * 0.999:
                    continue
        result = _submit_intent(
            exec_svc,
            intent,
            mark if mark > 0 else limit_or_intent_px,
            defer_market=defer_market_fills,
            deferred=deferred,
        )
        if result is not None and result.status in ("filled", "submitted"):
            risk.record_realized_pnl(result.pnl)
            fills.append({
                "ticker": result.ticker,
                "kind": "exit_sl_tp",
                "side": result.side,
                "reason": intent.reason,
                "qty": result.quantity,
                "price": result.price,
                "pnl": result.pnl,
                "status": result.status,
            })
            if str(getattr(intent, "reason", "") or "") == "stop_loss":
                runtime.notify_stop_loss(
                    session_id,
                    config.strategy.archetype,
                    result.ticker,
                    at=clock,
                    price=result.price,
                )

    positions_dict = ledger.positions_dict(prices)
    equity = ledger.mark_equity(prices)
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
        now=clock,
        triggered_by=triggered_by,  # type: ignore[arg-type]
        instrument_type=config.core.instrument_type,
        allow_short=allow_short,
        order_flow=order_flow,
        ws_healthy=True,
        take_profit_pct=config.risk.take_profit_pct,
        stop_loss_pct=config.risk.stop_loss_pct,
        broker_commission_rate=config.risk.broker_commission_pct / 100.0,
        tax_pct=config.risk.tax_pct,
    )
    signals = runtime.evaluate(session_id, ctx)
    signal_log: list[dict[str, Any]] = []
    cycle_id = str(ctx.cycle_id)
    bar_iso = clock.isoformat()

    def _log_signal(
        *,
        ticker: str,
        side: str,
        price: float | None,
        strategy_reason: str | None,
        kind: str,
        status: str,
        was_executed: bool,
        reject_reason: str | None = None,
        quantity: float | int | None = None,
    ) -> None:
        signal_log.append({
            "signal_time": bar_iso,
            "figi": ticker,
            "signal_type": str(side or "").upper() or "UNKNOWN",
            "price": price,
            "was_executed": 1 if was_executed else 0,
            "reason": strategy_reason,
            "reject_reason": reject_reason,
            "kind": kind,
            "status": status,
            "quantity": quantity,
            "cycle_id": cycle_id,
        })

    for signal in signals:
        ticker = str(signal.secid or "").upper()
        strat_reason = signal.reason or None
        if signal.side == "CLOSE":
            pos = ledger.positions.get(ticker)
            if not pos:
                _log_signal(
                    ticker=ticker,
                    side="CLOSE",
                    price=prices.get(ticker),
                    strategy_reason=strat_reason,
                    kind="exit_strategy",
                    status="rejected",
                    was_executed=False,
                    reject_reason="NO_POSITION",
                )
                continue
            px = prices.get(ticker, pos.avg_entry_price)
            tp_block = block_exit_below_break_even(
                entry=float(pos.avg_entry_price),
                price=float(px),
                side="long" if pos.is_long else "short",
                broker_commission_rate=config.risk.broker_commission_pct / 100.0,
            )
            if tp_block and not allow_strategy_exit_below_break_even(signal.reason):
                _log_signal(
                    ticker=ticker,
                    side="CLOSE",
                    price=float(px) if px is not None else None,
                    strategy_reason=strat_reason,
                    kind="exit_strategy",
                    status="rejected",
                    was_executed=False,
                    reject_reason="BREAK_EVEN_BLOCK",
                    quantity=int(pos.quantity),
                )
                continue
            intent = OrderIntent(
                kind="exit_strategy",
                figi=ticker,
                side="SELL" if pos.is_long else "BUY",
                quantity=float(pos.quantity),
                price=px,
                reduce_only=True,
                reason=signal.reason or "exit_strategy",
            )
            result = _submit_intent(
                exec_svc,
                intent,
                px,
                defer_market=defer_market_fills,
                deferred=deferred,
            )
            if result is None:
                _log_signal(
                    ticker=ticker,
                    side=intent.side,
                    price=float(px) if px is not None else None,
                    strategy_reason=strat_reason or "exit_strategy",
                    kind="exit_strategy",
                    status="deferred",
                    was_executed=False,
                    quantity=int(pos.quantity),
                )
            elif result.status in ("filled", "submitted"):
                risk.record_realized_pnl(result.pnl)
                fills.append({
                    "ticker": ticker,
                    "kind": "exit_strategy",
                    "side": result.side,
                    "reason": signal.reason or "exit_strategy",
                    "qty": int(pos.quantity),
                    "price": result.price or px,
                    "pnl": result.pnl,
                    "status": result.status,
                })
                positions_dict = ledger.positions_dict(prices)
                equity = ledger.mark_equity(prices)
                _log_signal(
                    ticker=ticker,
                    side=result.side or intent.side,
                    price=float(result.price or px or 0) or None,
                    strategy_reason=strat_reason or "exit_strategy",
                    kind="exit_strategy",
                    status=str(result.status),
                    was_executed=True,
                    quantity=int(pos.quantity),
                )
                if str(signal.reason or "") == "scalper_delta_invalidation":
                    runtime.notify_stop_loss(
                        session_id,
                        config.strategy.archetype,
                        ticker,
                        at=clock,
                        price=result.price or px,
                    )
            else:
                _log_signal(
                    ticker=ticker,
                    side=intent.side,
                    price=float(px) if px is not None else None,
                    strategy_reason=strat_reason or "exit_strategy",
                    kind="exit_strategy",
                    status="rejected",
                    was_executed=False,
                    reject_reason=str(result.reason or result.status or "EXEC_REJECT"),
                    quantity=int(pos.quantity),
                )
            continue

        if not risk.session_state.accept_new_entries and signal.side in ("BUY", "SELL"):
            pos = ledger.positions.get(ticker)
            is_reduce = (
                (signal.side == "SELL" and pos is not None and pos.is_long)
                or (signal.side == "BUY" and pos is not None and not pos.is_long)
            )
            if not is_reduce:
                _log_signal(
                    ticker=ticker,
                    side=str(signal.side),
                    price=float(signal.price_at_signal or prices.get(ticker) or 0) or None,
                    strategy_reason=strat_reason,
                    kind="entry",
                    status="rejected",
                    was_executed=False,
                    reject_reason="ENTRIES_PAUSED",
                )
                continue

        risk_decision, audit = risk.pre_trade(
            signal,
            cash=ledger.cash,
            equity=equity,
            positions=positions_dict,
        )
        if not risk_decision.allow:
            _log_signal(
                ticker=ticker,
                side=str(signal.side),
                price=float(signal.price_at_signal or prices.get(ticker) or 0) or None,
                strategy_reason=strat_reason,
                kind="entry",
                status="rejected",
                was_executed=False,
                reject_reason=str(audit.code or risk_decision.reason or "RISK_BLOCK"),
            )
            continue
        qty = int(risk_decision.quantity or 0)
        if qty <= 0:
            _log_signal(
                ticker=ticker,
                side=str(signal.side),
                price=float(signal.price_at_signal or prices.get(ticker) or 0) or None,
                strategy_reason=strat_reason,
                kind="entry",
                status="rejected",
                was_executed=False,
                reject_reason="ZERO_QTY",
            )
            continue
        price = float(signal.price_at_signal or prices.get(ticker, 0))
        if price <= 0:
            _log_signal(
                ticker=ticker,
                side=str(signal.side),
                price=None,
                strategy_reason=strat_reason,
                kind="entry",
                status="rejected",
                was_executed=False,
                reject_reason="STALE_OR_MISSING_PRICE",
                quantity=qty,
            )
            continue
        intent = risk.build_entry_intent(signal, qty, price)
        result = _submit_intent(
            exec_svc,
            intent,
            price,
            defer_market=defer_market_fills,
            deferred=deferred,
        )
        if result is None:
            _log_signal(
                ticker=ticker,
                side=intent.side,
                price=price,
                strategy_reason=strat_reason or "entry",
                kind="entry",
                status="deferred",
                was_executed=False,
                quantity=qty,
            )
        elif result.status in ("filled", "submitted"):
            fills.append({
                "ticker": ticker,
                "kind": "entry",
                "side": result.side,
                "reason": signal.reason or "entry",
                "qty": qty,
                "price": result.price,
                "pnl": result.pnl,
                "status": result.status,
            })
            positions_dict = ledger.positions_dict(prices)
            equity = ledger.mark_equity(prices)
            _log_signal(
                ticker=ticker,
                side=result.side or intent.side,
                price=float(result.price or price),
                strategy_reason=strat_reason or "entry",
                kind="entry",
                status=str(result.status),
                was_executed=True,
                quantity=qty,
            )
        else:
            _log_signal(
                ticker=ticker,
                side=intent.side,
                price=price,
                strategy_reason=strat_reason or "entry",
                kind="entry",
                status="rejected",
                was_executed=False,
                reject_reason=str(result.reason or result.status or "EXEC_REJECT"),
                quantity=qty,
            )

    wanted_entries: set[tuple[str, str]] = set()
    if risk.session_state.accept_new_entries:
        for signal in signals:
            side = str(signal.side or "").upper()
            if side not in ("BUY", "SELL"):
                continue
            ticker = str(signal.secid or "").upper()
            if not ticker:
                continue
            pos = ledger.positions.get(ticker)
            is_reduce = (
                (side == "SELL" and pos is not None and pos.is_long)
                or (side == "BUY" and pos is not None and not pos.is_long)
            )
            if is_reduce:
                continue
            wanted_entries.add((ticker, side))
    held_now = {str(t).upper() for t in ledger.positions}
    for orphan_t in select_orphan_resting_tickers(
        getattr(exec_svc, "_resting", {}) or {},
        held_tickers=held_now,
        wanted_entries=wanted_entries,
        scope="entry",
    ):
        exec_svc.cancel_resting_local(orphan_t)

    return {
        "fills": fills,
        "signals": len(signals),
        "signal_log": signal_log,
        "cycleId": cycle_id,
        "deferred_intents": deferred,
    }
