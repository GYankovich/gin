"""Single trading cycle for robots v2 (paper + live via ExecutionService)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.modules.robots.trading.contracts import Candle, OrderIntent
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.audit import (
    AuditCycleBundle,
    AuditDecisionRow,
    AuditExecutionRow,
    AuditSignalRow,
    decision_row_from_dict,
    execution_row_from_result,
    signal_row_from_eval,
)
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.execution import ExecutionService, attach_ticker_warnings
from app.modules.robots_v2.engine.market_data import strategy_tape_prices
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.strategy.helpers import (
    allow_strategy_exit_below_break_even,
    block_exit_below_break_even,
)
from app.modules.robots_v2.strategy.runtime import strategy_runtime
from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot, StrategyContext

StageCallback = Callable[..., Awaitable[None]]


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
    action_log: Any | None = None,
    on_stage: StageCallback | None = None,
    audit_session_id: UUID | None = None,
    cycle_started_at: datetime | None = None,
    now: datetime | None = None,
    emit_events: bool = True,
    mark_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    _ = user_id

    cycle_id = uuid4()
    clock = now or cycle_started_at or datetime.now(timezone.utc)
    started_at = cycle_started_at or clock
    audit_signals: list[AuditSignalRow] = []
    audit_decisions: list[AuditDecisionRow] = []
    audit_executions: list[AuditExecutionRow] = []

    def _alog(msg: str) -> None:
        if action_log is not None:
            action_log.info(msg)

    async def _publish(event_type: str, payload: dict[str, Any]) -> None:
        if emit_events:
            await event_bus.publish(robot_id, event_type, payload)

    async def _stage(name: str, **kwargs: Any) -> None:
        if on_stage is not None:
            await on_stage(name, **kwargs)

    decisions: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    tape_prices = strategy_tape_prices(prices, mark_prices)

    exec_svc = execution or ExecutionService(
        mode="paper",
        robot_id=robot_id,
        ledger=ledger,
        slippage_pct=config.risk.slippage_pct,
        action_log=action_log,
    )

    positions_dict = ledger.positions_dict(prices)
    equity = ledger.mark_equity(prices)

    # 1. Exits-first (SL/TP)
    await _stage("exits")
    sync_force = triggered_by in ("poll", "bar_close")
    for poll_result in await exec_svc.sync_orders_from_broker(force=sync_force):
        if poll_result.status == "filled":
            audit_executions.append(
                execution_row_from_result(poll_result, kind=poll_result.kind or "exit_sl_tp"),
            )
            risk.record_realized_pnl(poll_result.pnl)
            fills.append({
                "ticker": poll_result.ticker,
                "kind": poll_result.kind or "exit_sl_tp",
                "side": poll_result.side,
                "reason": poll_result.reason,
                "pnl": poll_result.pnl,
                "status": poll_result.status,
            })
            _alog(
                f"ORDER_SYNC_FILL {poll_result.side} {poll_result.ticker} "
                f"qty={poll_result.quantity} pnl={poll_result.pnl:.4f}"
            )
        elif poll_result.status in ("cancelled", "rejected"):
            audit_executions.append(
                execution_row_from_result(poll_result, kind=poll_result.kind or "exit_sl_tp"),
            )
            _alog(
                f"ORDER_SYNC_{poll_result.status.upper()} {poll_result.ticker}: "
                f"{poll_result.reason}"
            )

    for poll_result in await exec_svc.poll_resting_fills(last_prices=prices):
        audit_executions.append(
            execution_row_from_result(poll_result, kind=poll_result.kind or "exit_sl_tp"),
        )
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
            _alog(
                f"RESTING_FILL {poll_result.side} {poll_result.ticker} "
                f"qty={poll_result.quantity} pnl={poll_result.pnl:.4f}"
            )

    open_list = ledger.open_positions_list(prices)
    exit_intents = risk.evaluate_exits(open_list, prices)
    exit_tickers = {
        str(getattr(i, "figi", "") or "").upper()
        for i in exit_intents
        if str(getattr(i, "reason", "") or "") == "take_profit"
    }
    # Drop premature TP LIMIT left from older logic / sync if TP not armed yet.
    for ticker, ro in list(getattr(exec_svc, "_resting", {}).items()):
        if str(ro.reason or "") not in ("take_profit", "broker_sync") and str(ro.kind or "") != "exit_sl_tp":
            continue
        if ticker.upper() in exit_tickers:
            continue
        pos = next((p for p in open_list if str(p.get("ticker") or p.get("figi") or "").upper() == ticker.upper()), None)
        if pos is None:
            continue
        from app.modules.robots.trading.risk.manager import decide_take_profit_order
        from app.modules.robots.trading.costs import calculate_take_profit_price

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
            _alog(f"CANCEL premature TP resting {ticker} mark={px:.4g} tp={tp:.4g}")
            await exec_svc.cancel_resting(ticker)

    for intent in exit_intents:
        ticker_u = str(intent.figi or "").upper()
        mark = float(prices.get(ticker_u) or 0)
        limit_or_intent_px = float(intent.price or 0)
        meta = getattr(intent, "meta", None) or {}
        order_type = str(getattr(intent, "order_type", None) or "MARKET").upper()
        audit_decisions.append(AuditDecisionRow(
            stage="exits",
            outcome="allow",
            code=str(getattr(intent, "reason", None) or "exit_sl_tp"),
            message=(
                f"Exit {intent.side} {intent.figi} qty={intent.quantity} "
                f"mark={mark:.4g} intentPx={limit_or_intent_px:.4g} "
                f"type={order_type} reason={getattr(intent, 'reason', '')}"
            ),
            ticker=ticker_u,
            context={
                "entryPrice": meta.get("entry_price"),
                "markPrice": mark or meta.get("mark_price"),
                "exitPrice": limit_or_intent_px,
                "takeProfit": meta.get("take_profit"),
                "stopLoss": meta.get("stop_loss"),
                "orderType": order_type,
                "kind": getattr(intent, "kind", "exit_sl_tp"),
            },
        ))
        _alog(
            f"EXIT_SL_TP {intent.side} {intent.figi} qty={intent.quantity} "
            f"reason={intent.reason} type={order_type} mark={mark:.4g} "
            f"intentPx={limit_or_intent_px:.4g}"
        )
        # IMPORTANT: last_price must be mark, never limit TP price — otherwise
        # paper/live paths can treat TP as already reached and dump at market.
        # Sanity: reject insane marks for take_profit (stale WS / bad mapping).
        # Real move to TP is ~1%; a +10% jump in one tick is not a valid TP trigger.
        if str(getattr(intent, "reason", "") or "") == "take_profit" and mark > 0:
            entry_m = float(meta.get("entry_price") or 0)
            tp_m = float(meta.get("take_profit") or 0)
            if entry_m > 0 and tp_m > 0:
                span = abs(tp_m - entry_m)
                # Extreme jump vs TP distance → phantom WS/mapping (e.g. BANEP 940
                # vs entry 833 / TP ~843). Mild overshoots past TP stay allowed.
                if span > 0 and (
                    mark > tp_m * 1.02
                    or abs(mark - entry_m) > max(span * 3.0, entry_m * 0.05)
                ):
                    _alog(
                        f"SKIP take_profit {ticker_u}: insane mark={mark:.4g} "
                        f"entry={entry_m:.4g} tp={tp_m:.4g}"
                    )
                    audit_decisions.append(AuditDecisionRow(
                        stage="exits",
                        outcome="deny",
                        code="STALE_MARK_TP",
                        message=(
                            f"Skip TP {ticker_u}: mark={mark:.4g} inconsistent with "
                            f"entry={entry_m:.4g} tp={tp_m:.4g}"
                        ),
                        ticker=ticker_u,
                        context={
                            "entryPrice": entry_m,
                            "markPrice": mark,
                            "takeProfit": tp_m,
                        },
                    ))
                    continue
                # MARKET TP only if mark actually reached TP (not a phantom print).
                if order_type == "MARKET" and mark < tp_m * 0.999:
                    _alog(
                        f"SKIP take_profit MARKET {ticker_u}: mark={mark:.4g} < tp={tp_m:.4g}"
                    )
                    continue

        result = await exec_svc.execute_intent(
            intent,
            last_price=mark if mark > 0 else limit_or_intent_px,
        )
        if str(result.reason or "") not in ("ALREADY_RESTING", "REJECT_COOLDOWN"):
            audit_executions.append(execution_row_from_result(result, kind="exit_sl_tp"))
        if result.status in ("filled", "submitted"):
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
                strategy_runtime.notify_stop_loss(
                    session_id,
                    config.strategy.archetype,
                    result.ticker,
                    at=clock,
                    price=result.price,
                )
        elif result.status == "resting":
            _alog(
                f"EXIT_SL_TP resting {intent.figi} {result.side} "
                f"qty={result.quantity} @ {result.price:.4g}"
            )
        elif str(result.reason or "") == "REJECT_COOLDOWN":
            pass
        else:
            _alog(f"EXIT_SL_TP rejected {intent.figi}: {result.reason}")

    positions_dict = ledger.positions_dict(prices)
    equity = ledger.mark_equity(prices)

    # 2. Strategy signals
    await _stage("strategy")
    ctx = StrategyContext(
        robot_id=robot_id,
        cycle_id=cycle_id,
        config=config.strategy,
        universe=universe,
        last_price=tape_prices,
        candles=candle_history,
        atr={},
        open_positions=list(positions_dict.values()),
        mode=config.core.mode,
        now=clock,
        triggered_by=triggered_by,  # type: ignore[arg-type]
        instrument_type=config.core.instrument_type,
        allow_short=allow_short,
        order_flow=order_flow,
        ws_healthy=ws_healthy,
        take_profit_pct=config.risk.take_profit_pct,
        stop_loss_pct=config.risk.stop_loss_pct,
        broker_commission_rate=config.risk.broker_commission_pct / 100.0,
        tax_pct=config.risk.tax_pct,
    )
    signals = strategy_runtime.evaluate(session_id, ctx)
    ticker_scan = strategy_runtime.last_scan(session_id, config.strategy.archetype)

    if not signals:
        min_bars = min((len(candle_history.get(t) or []) for t in universe), default=0) if universe else 0
        no_sig = {
            "code": "NO_SIGNAL",
            "message": (
                f"Strategy quiet (triggered_by={triggered_by}, "
                f"minCandles={min_bars}, universe={len(universe)})"
            ),
            "allow": True,
            "triggeredBy": triggered_by,
            "minCandles": min_bars,
        }
        decisions.append(no_sig)
        audit_decisions.append(decision_row_from_dict(no_sig, stage="strategy"))
        _alog(f"DECISION NO_SIGNAL by={triggered_by} minCandles={min_bars}")

    for signal in signals:
        ticker = str(signal.secid or "").upper()
        audit_signals.append(signal_row_from_eval(
            signal,
            prices=tape_prices,
            positions=ledger.positions,
            order_flow=order_flow,
        ))
        await _stage("risk", detail=ticker)
        _alog(f"SIGNAL {signal.side} {signal.secid} reason={signal.reason}")
        await _publish("signal", {
            "ticker": signal.secid,
            "side": signal.side,
            "reason": signal.reason,
        })

        if signal.side == "CLOSE":
            pos = ledger.positions.get(ticker)
            if pos:
                await _stage("execution", detail=ticker)
                px = tape_prices.get(ticker, pos.avg_entry_price)
                tp_block = block_exit_below_break_even(
                    entry=float(pos.avg_entry_price),
                    price=float(px),
                    side="long" if pos.is_long else "short",
                    broker_commission_rate=config.risk.broker_commission_pct / 100.0,
                )
                if tp_block and not allow_strategy_exit_below_break_even(signal.reason):
                    blocked = {
                        "code": "EXIT_BELOW_BREAK_EVEN",
                        "message": tp_block,
                        "ticker": ticker,
                        "allow": False,
                    }
                    decisions.append(blocked)
                    audit_decisions.append(decision_row_from_dict(blocked, stage="execution"))
                    _alog(f"EXIT_STRATEGY blocked {ticker}: {tp_block}")
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
                result = await exec_svc.execute_intent(intent, last_price=px)
                audit_executions.append(execution_row_from_result(result, kind="exit_strategy"))
                if result.status in ("filled", "submitted"):
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
                    if str(signal.reason or "") == "scalper_delta_invalidation":
                        strategy_runtime.notify_stop_loss(
                            session_id,
                            config.strategy.archetype,
                            ticker,
                            at=clock,
                            price=result.price or px,
                        )
                else:
                    _alog(f"EXIT_STRATEGY rejected {ticker}: {result.reason}")
            continue

        if not risk.session_state.accept_new_entries and signal.side in ("BUY", "SELL"):
            pos = ledger.positions.get(ticker)
            is_reduce = (
                (signal.side == "SELL" and pos is not None and pos.is_long)
                or (signal.side == "BUY" and pos is not None and not pos.is_long)
            )
            if not is_reduce:
                paused = {
                    "code": "ENTRIES_PAUSED",
                    "message": "New entries paused",
                    "ticker": signal.secid,
                    "allow": False,
                }
                decisions.append(paused)
                audit_decisions.append(decision_row_from_dict(paused, stage="risk"))
                _alog(f"DECISION ENTRIES_PAUSED ticker={signal.secid}")
                continue

        risk_decision, audit = risk.pre_trade(
            signal,
            cash=ledger.cash,
            equity=equity,
            positions=positions_dict,
        )
        decisions.append(audit.__dict__)
        audit_decisions.append(decision_row_from_dict(audit.__dict__, stage="risk"))
        if not risk_decision.allow:
            _alog(f"DECISION {audit.code} ticker={audit.ticker} msg={audit.message}")
            await _publish("decision", {
                "code": audit.code, "message": audit.message, "ticker": audit.ticker,
            })
            continue

        qty = int(risk_decision.quantity or 0)
        if qty <= 0:
            _alog(f"DECISION ZERO_QTY ticker={signal.secid}")
            continue
        price = float(signal.price_at_signal or prices.get(ticker, 0))
        if price <= 0:
            _alog(f"DECISION BAD_PRICE ticker={ticker}")
            continue
        await _stage("execution", detail=ticker)
        intent = risk.build_entry_intent(signal, qty, price)
        _alog(f"ENTRY {intent.side} {ticker} qty={qty} price={price:.6g}")
        result = await exec_svc.execute_intent(intent, last_price=price)
        audit_executions.append(execution_row_from_result(result, kind="entry"))
        if result.status in ("filled", "submitted"):
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
        else:
            rejected = {
                "code": result.reason or "EXEC_REJECTED",
                "message": result.reason or "rejected",
                "ticker": ticker,
                "allow": False,
            }
            decisions.append(rejected)
            audit_decisions.append(decision_row_from_dict(rejected, stage="execution"))
            _alog(f"ENTRY rejected {ticker}: {result.reason}")

    await _stage("metrics")
    ui_prices = mark_prices or prices
    positions_rows = ledger.open_positions_list(ui_prices)
    if positions_rows:
        from app.modules.robots_v2.risk.adapter import enrich_positions_with_exit_prices
        positions_rows = enrich_positions_with_exit_prices(positions_rows, config.risk)
    positions_rows = attach_ticker_warnings(positions_rows, exec_svc, last_prices=ui_prices)
    await _publish("cycle", {
        "cycleNumber": cycle_number,
        "equity": ledger.mark_equity(ui_prices),
        "positions": len(ledger.positions),
        "openPositions": positions_rows,
        "positionsUpdatedAt": clock.isoformat(),
        "signals": len(signals),
        "mode": exec_svc.mode,
        "triggeredBy": triggered_by,
        "stage": "done",
        "tickerScan": ticker_scan,
    })

    finished_at = clock
    audit_bundle: AuditCycleBundle | None = None
    if audit_session_id is not None:
        audit_bundle = AuditCycleBundle(
            cycle_id=cycle_id,
            session_id=audit_session_id,
            robot_id=robot_id,
            cycle_number=cycle_number,
            triggered_by=triggered_by,
            started_at=started_at,
            finished_at=finished_at,
            status="ok",
            equity=ledger.mark_equity(prices),
            stats={
                "signals": len(signals),
                "fills": len(fills),
                "decisions": len(decisions),
            },
            signals=audit_signals,
            decisions=audit_decisions,
            executions=audit_executions,
        )

    return {
        "decisions": decisions,
        "fills": fills,
        "signals": len(signals),
        "tickerScan": ticker_scan,
        "auditBundle": audit_bundle,
        "cycleId": str(cycle_id),
    }
