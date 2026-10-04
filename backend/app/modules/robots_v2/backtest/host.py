"""Historical bar replay using robots v2 unified trading cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.modules.trading_core.contracts import Candle, OrderIntent
from app.modules.robots_v2.backtest.funding import apply_funding_charges_for_bar
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.cycle_sync import run_paper_cycle_sync
from app.modules.robots_v2.engine.execution import ExecutionService
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.risk.eod import MSK, is_within_trading_session, should_eod_flatten
from app.modules.robots_v2.strategy.runtime import StrategyRuntime


def dicts_to_candles(
    series: list[dict[str, Any]],
    *,
    ticker: str,
    interval: str,
) -> list[Candle]:
    out: list[Candle] = []
    for row in series:
        c = Candle.from_tinvest_dict(row, interval=interval, secid=ticker)
        if c.time.tzinfo is None:
            c.time = c.time.replace(tzinfo=timezone.utc)
        out.append(c)
    out.sort(key=lambda x: x.time)
    return out


def build_bar_timeline(candles_by_ticker: dict[str, list[Candle]]) -> list[datetime]:
    times: set[datetime] = set()
    for series in candles_by_ticker.values():
        for c in series:
            times.add(c.time)
    return sorted(times)


def max_drawdown_percent(equity_curve: list[dict[str, Any]]) -> float:
    peak = 0.0
    max_dd = 0.0
    for point in equity_curve:
        eq = float(point.get("equity") or 0)
        if eq <= 0:
            continue
        peak = max(peak, eq)
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            max_dd = max(max_dd, dd)
    return round(max_dd, 4)


def _flatten_all_positions(ledger: PaperLedger, prices: dict[str, float]) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []
    for ticker, pos in list(ledger.positions.items()):
        px = prices.get(ticker, pos.avg_entry_price)
        qty = int(pos.quantity)
        side = "SELL" if pos.is_long else "BUY"
        pnl = ledger.apply_fill(
            ticker=ticker,
            side=side,
            quantity=qty,
            price=px,
            reduce_only=True,
        )
        fills.append({
            "ticker": ticker,
            "kind": "flatten",
            "side": side,
            "qty": qty,
            "price": px,
            "pnl": pnl,
            "reason": "eod_flatten",
        })
    return fills


def _holdings_snapshot(ledger: PaperLedger, prices: dict[str, float]) -> list[dict[str, Any]]:
    """P1 holdings list for portfolio snapshots (glass-box)."""
    rows: list[dict[str, Any]] = []
    for ticker, pos in sorted(ledger.positions.items(), key=lambda kv: kv[0]):
        mark = float(prices.get(ticker, pos.avg_entry_price) or 0)
        rows.append({
            "ticker": str(ticker).upper(),
            "qty": int(pos.quantity),
            "side": "long" if pos.is_long else "short",
            "avg_entry": round(float(pos.avg_entry_price), 6),
            "mark": round(mark, 6),
        })
    return rows


def _portfolio_snapshot_row(
    *,
    bar_time: datetime,
    ledger: PaperLedger,
    prices: dict[str, float],
) -> dict[str, Any]:
    holdings = _holdings_snapshot(ledger, prices)
    equity = ledger.mark_equity(prices)
    return {
        "snapshot_time": bar_time.isoformat(),
        "equity": round(equity, 2),
        "cash": round(ledger.cash, 2),
        "positions": holdings,
        "positions_count": len(holdings),
    }


def build_fee_summary(
    trades: list[dict[str, Any]],
    *,
    funding_total: float = 0.0,
    funding_events: int = 0,
    tax_total: float | None = None,
) -> dict[str, Any]:
    """Aggregate cost strip for metrics_summary / details."""
    commission_total = 0.0
    for t in trades:
        try:
            commission_total += float(t.get("commission") or 0)
        except (TypeError, ValueError):
            continue
    out: dict[str, Any] = {
        "commission_total": round(commission_total, 6),
        "funding_total": round(float(funding_total or 0), 6),
        "funding_events": int(funding_events or 0),
    }
    if tax_total is not None:
        out["tax_total"] = round(float(tax_total), 6)
    return out


def _ensure_intent_id(intent: OrderIntent) -> str:
    meta = dict(getattr(intent, "meta", None) or {})
    iid = str(meta.get("intent_id") or "").strip()
    if not iid:
        iid = str(uuid4())
        meta["intent_id"] = iid
        intent.meta = meta
    return iid


def _execution_event(
    *,
    ts: datetime,
    intent: OrderIntent | None = None,
    intent_id: str | None = None,
    cycle_id: str | None = None,
    ticker: str | None = None,
    side: str | None = None,
    kind: str | None = None,
    status: str,
    reason: str | None = None,
    reject_reason: str | None = None,
    quantity: float | int | None = None,
    price: float | None = None,
    signal_time: str | None = None,
    trade_id: int | None = None,
) -> dict[str, Any]:
    meta = dict(getattr(intent, "meta", None) or {}) if intent is not None else {}
    iid = intent_id or str(meta.get("intent_id") or uuid4())
    return {
        "event_id": str(uuid4()),
        "ts": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "intent_id": iid,
        "cycle_id": cycle_id or (str(meta["cycle_id"]) if meta.get("cycle_id") else None),
        "ticker": str(ticker or (getattr(intent, "figi", None) if intent else "") or "").upper(),
        "side": side or (str(getattr(intent, "side", None) or "") if intent else None) or None,
        "kind": kind or (str(getattr(intent, "kind", None) or "") if intent else None) or None,
        "status": status,
        "reason": reason if reason is not None else (str(getattr(intent, "reason", None) or "") or None),
        "reject_reason": reject_reason,
        "quantity": quantity if quantity is not None else (
            float(getattr(intent, "quantity", 0) or 0) if intent is not None else None
        ),
        "price": price if price is not None else (
            float(getattr(intent, "price", 0) or 0) or None if intent is not None else None
        ),
        "signal_time": signal_time or (str(meta["signal_time"]) if meta.get("signal_time") else None),
        "trade_id": trade_id,
    }


def _record_fills(
    fills: list[dict[str, Any]],
    *,
    bar_time: datetime,
    prices: dict[str, float],
    commission: float,
    trade_id: int,
    trades: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> int:
    for fill in fills:
        trade_id += 1
        ticker = str(fill.get("ticker") or "")
        kind = str(fill.get("kind") or "")
        reason = str(fill.get("reason") or kind or "").strip()
        side = str(fill.get("side") or ("SELL" if "exit" in kind or kind == "flatten" else "BUY"))
        qty = int(fill.get("qty") or fill.get("quantity") or 0) or 1
        price = float(fill.get("price") or prices.get(ticker, 0))
        pnl = fill.get("pnl")
        cycle_id = fill.get("cycle_id")
        signal_time = fill.get("signal_time")
        intent_id = fill.get("intent_id")
        trade_row = {
            "id": trade_id,
            "figi": ticker,
            "side": side,
            "bar_time": bar_time.isoformat(),
            "price": price,
            "quantity": qty,
            "commission": round(price * qty * commission, 2),
            "pnl_net": round(float(pnl), 2) if pnl is not None else None,
            "reason": reason or None,
            "kind": kind or None,
        }
        if cycle_id:
            trade_row["cycle_id"] = str(cycle_id)
        if signal_time:
            trade_row["signal_time"] = str(signal_time)
        if intent_id:
            trade_row["intent_id"] = str(intent_id)
        fill["trade_id"] = trade_id
        trades.append(trade_row)
        order_row = {
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "price": price,
            "time": bar_time.isoformat(),
            "kind": kind,
            "reason": reason or None,
            "id": trade_id,
            "status": str(fill.get("status") or "filled"),
        }
        if cycle_id:
            order_row["cycle_id"] = str(cycle_id)
        if signal_time:
            order_row["signal_time"] = str(signal_time)
        if intent_id:
            order_row["intent_id"] = str(intent_id)
        orders.append(order_row)
    return trade_id


def _apply_deferred_intents(
    intents: list[OrderIntent],
    *,
    opens: dict[str, float],
    exec_svc: ExecutionService,
    risk: RiskEngine,
    runtime: StrategyRuntime,
    session_id: int,
    archetype: str,
    clock: datetime,
) -> tuple[list[dict[str, Any]], list[OrderIntent], list[dict[str, Any]]]:
    """Fill yesterday's close signals at this bar's open. Unpriced names stay queued."""
    fills: list[dict[str, Any]] = []
    leftover: list[OrderIntent] = []
    events: list[dict[str, Any]] = []
    for intent in intents:
        _ensure_intent_id(intent)
        ticker = str(intent.figi or "").upper()
        px = float(opens.get(ticker) or 0)
        if px <= 0:
            leftover.append(intent)
            continue
        if str(getattr(intent, "order_type", None) or "MARKET").upper() != "LIMIT":
            intent.price = px
        result = exec_svc.execute_intent_sync(intent, last_price=px)
        meta = getattr(intent, "meta", None) or {}
        kind = str(getattr(intent, "kind", None) or "entry")
        if result.status in ("filled", "submitted"):
            risk.record_realized_pnl(result.pnl)
            fill_row: dict[str, Any] = {
                "ticker": result.ticker,
                "kind": kind,
                "side": result.side,
                "reason": intent.reason,
                "qty": result.quantity,
                "price": result.price,
                "pnl": result.pnl,
                "status": result.status,
                "intent_id": str(meta.get("intent_id") or ""),
            }
            if meta.get("cycle_id"):
                fill_row["cycle_id"] = str(meta["cycle_id"])
            if meta.get("signal_time"):
                fill_row["signal_time"] = str(meta["signal_time"])
            fills.append(fill_row)
            events.append(_execution_event(
                ts=clock,
                intent=intent,
                status="filled",
                quantity=result.quantity,
                price=float(result.price or 0) or None,
            ))
            if str(intent.reason or "") == "stop_loss":
                runtime.notify_stop_loss(session_id, archetype, result.ticker, at=clock)
        elif result.status == "resting":
            events.append(_execution_event(
                ts=clock,
                intent=intent,
                status="resting",
                quantity=result.quantity,
                price=float(result.price or px) or None,
            ))
        else:
            # Rejected/cancelled: drop (priced once already) — do not re-queue.
            events.append(_execution_event(
                ts=clock,
                intent=intent,
                status="rejected",
                reject_reason=str(getattr(result, "reason", None) or result.status or "EXEC_REJECT"),
                quantity=result.quantity,
                price=float(result.price or px) or None,
            ))
    return fills, leftover, events


def build_run_narrative(
    *,
    initial_capital: float,
    final_equity: float,
    total_return_percent: float,
    max_drawdown_percent: float,
    history_stats: dict[str, Any],
    fee_summary: dict[str, Any] | None = None,
    finished_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Structured RU narrative steps for glass-box UI (SPEC §5.4 / [R-14])."""
    ts = (finished_at or datetime.now(timezone.utc)).isoformat()
    bars = int(history_stats.get("bars") or 0)
    tickers = int(history_stats.get("tickers") or 0)
    warmup = int(history_stats.get("warmup_bars") or 0)
    traded = int(history_stats.get("traded_bars") or 0)
    trades_n = int(history_stats.get("trades") or 0)
    signals_n = int(history_stats.get("signals") or 0)
    truncated = bool(history_stats.get("signals_truncated"))
    dropped = int(history_stats.get("dropped_deferred") or 0)
    funding_events = int(history_stats.get("funding_events") or 0)
    fee = fee_summary or {}

    steps: list[dict[str, Any]] = [
        {
            "section": "подготовка",
            "step": 1,
            "text": f"К прогону готово {bars} баров по {tickers} инструментам; стартовый капитал {round(initial_capital, 2)}.",
            "ts": ts,
        },
        {
            "section": "симуляция",
            "step": 2,
            "text": (
                f"Прогрев: {warmup} баров; торговых баров: {traded}. "
                "Сигналы считаются по закрытию, исполнение — на открытии следующего бара (без заглядывания вперёд)."
            ),
            "ts": ts,
        },
        {
            "section": "исполнение",
            "step": 3,
            "text": (
                f"Сделок: {trades_n}; сигналов в журнале: {signals_n}"
                + (" (журнал обрезан по лимиту)" if truncated else "")
                + (f"; отложенных заявок сброшено в конце: {dropped}" if dropped else "")
                + "."
            ),
            "ts": ts,
        },
    ]
    if funding_events or float(fee.get("funding_total") or 0):
        steps.append({
            "section": "издержки",
            "step": 4,
            "text": (
                f"Комиссия: {fee.get('commission_total', 0)}; "
                f"фандинг: {fee.get('funding_total', 0)} ({funding_events} событий)."
            ),
            "ts": ts,
        })
    steps.append({
        "section": "итог",
        "step": len(steps) + 1,
        "text": (
            f"Итоговый капитал {round(final_equity, 2)}; "
            f"доходность {round(total_return_percent, 4)}%; "
            f"макс. просадка {round(max_drawdown_percent, 4)}%."
        ),
        "ts": ts,
    })
    return steps


_MAX_SIGNAL_LOG = 25_000
SIGNAL_LOG_CAP = _MAX_SIGNAL_LOG


def _build_daily_summary(
    signal_events: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}

    def _day_key(raw: Any) -> str | None:
        if raw is None:
            return None
        s = str(raw)
        return s[:10] if len(s) >= 10 else None

    for ev in signal_events:
        d = _day_key(ev.get("signal_time"))
        if not d:
            continue
        row = by_day.setdefault(
            d,
            {
                "date": d,
                "signals_total": 0,
                "signals_executed": 0,
                "signals_rejected": 0,
                "signals_deferred": 0,
                "trades_total": 0,
                "candidates_accept": 0,
                "candidates_reject": 0,
            },
        )
        row["signals_total"] += 1
        status = str(ev.get("status") or "").lower()
        if int(ev.get("was_executed") or 0):
            row["signals_executed"] += 1
            row["candidates_accept"] += 1
        elif status == "deferred":
            row["signals_deferred"] += 1
            row["candidates_accept"] += 1
        else:
            row["signals_rejected"] += 1
            row["candidates_reject"] += 1
    for t in trades:
        d = _day_key(t.get("bar_time"))
        if not d:
            continue
        row = by_day.setdefault(
            d,
            {
                "date": d,
                "signals_total": 0,
                "signals_executed": 0,
                "signals_rejected": 0,
                "signals_deferred": 0,
                "trades_total": 0,
                "candidates_accept": 0,
                "candidates_reject": 0,
            },
        )
        row["trades_total"] += 1
    return [by_day[k] for k in sorted(by_day.keys())]


@dataclass
class BacktestHostResult:
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: float
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    portfolio_snapshots: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    daily_summary: list[dict[str, Any]] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    history_stats: dict[str, int] = field(default_factory=dict)
    funding_charges_total: float = 0.0
    fee_summary: dict[str, Any] = field(default_factory=dict)
    universe_by_day: dict[date, list[str]] = field(default_factory=dict)
    execution_events: list[dict[str, Any]] = field(default_factory=list)
    narrative: list[dict[str, Any]] = field(default_factory=list)


class BacktestHost:
    """Replay OHLCV bars through the paper trading cycle (ADR-02 unified pipeline)."""

    async def run(self, **kwargs: Any) -> BacktestHostResult:
        return self.run_sync(**kwargs)

    def run_sync(
        self,
        *,
        config: TradingRobotConfigV4,
        universe: list[str],
        candles_by_ticker: dict[str, list[Candle]],
        initial_capital: float,
        session_id: int,
        robot_id: int = 0,
        user_id: int = 0,
        trade_from: datetime | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        funding_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
        funding_mode: str = "historical",
        universe_by_day: dict[date, list[str]] | None = None,
    ) -> BacktestHostResult:
        _ = user_id
        tickers = [t.upper() for t in universe if t]
        day_universe: dict[date, list[str]] = {}
        if universe_by_day:
            for d, names in universe_by_day.items():
                day_universe[d] = [str(t).upper() for t in (names or []) if t]
        candles_by_ticker = {k.upper(): v for k, v in candles_by_ticker.items()}
        funding_by_symbol = {
            str(k).upper(): list(v or [])
            for k, v in (funding_by_symbol or {}).items()
            if k
        }
        timeline = build_bar_timeline({t: candles_by_ticker.get(t, []) for t in tickers})
        if not timeline:
            return BacktestHostResult(
                initial_capital=initial_capital,
                final_equity=initial_capital,
                total_return_percent=0.0,
                max_drawdown_percent=0.0,
                stages=["No candle data in requested range"],
                history_stats={"bars": 0, "tickers": len(tickers)},
            )

        if trade_from is not None and trade_from.tzinfo is None:
            trade_from = trade_from.replace(tzinfo=timezone.utc)

        commission = config.risk.broker_commission_pct / 100.0
        allow_short = config.core.instrument_type in ("perpetual", "coin_futures")
        ledger = PaperLedger(cash=initial_capital, commission_rate=commission, allow_short=allow_short)
        risk = RiskEngine(config.risk, allow_short=allow_short)
        risk.begin_session(initial_capital)
        exec_svc = ExecutionService(
            mode="paper",
            robot_id=robot_id,
            ledger=ledger,
            slippage_pct=config.risk.slippage_pct,
            quiet=True,
        )
        runtime = StrategyRuntime()
        plugin = runtime.get_plugin(session_id, config.strategy.archetype)
        plugin.scan_enabled = False

        equity_curve: list[dict[str, Any]] = []
        portfolio_snapshots: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        signal_events: list[dict[str, Any]] = []
        signals_truncated = False
        trade_id = 0
        skipped_schedule = 0
        warmup_bars = 0
        traded_bars = 0
        funding_charges_total = 0.0
        funding_events_applied = 0
        eod_done = False
        last_day: date | None = None
        prev_bar_time: datetime | None = None
        applied_funding_keys: set[tuple[str, str]] = set()

        idx_by_ticker: dict[str, dict[datetime, Candle]] = {}
        for t in tickers:
            series = candles_by_ticker.get(t, [])
            idx_by_ticker[t] = {c.time: c for c in series}

        history: dict[str, list[Candle]] = {t: [] for t in tickers}
        total_bars = len(timeline)
        last_progress = 0
        deferred: list[OrderIntent] = []
        execution_events: list[dict[str, Any]] = []
        dropped_deferred = 0
        archetype = config.strategy.archetype

        for cycle_num, bar_time in enumerate(timeline, start=1):
            if is_cancelled and is_cancelled():
                break
            if progress_callback and (cycle_num == 1 or cycle_num == total_bars or cycle_num - last_progress >= 64):
                last_progress = cycle_num
                progress_callback(cycle_num, total_bars)

            opens: dict[str, float] = {}
            prices: dict[str, float] = {}
            for t in tickers:
                bar = idx_by_ticker[t].get(bar_time)
                if bar is not None:
                    history[t].append(bar)
                    opens[t] = float(bar.open)
                    prices[t] = float(bar.close)

            if not prices:
                continue

            if trade_from is not None and bar_time < trade_from:
                warmup_bars += 1
                prev_bar_time = bar_time
                continue

            if deferred and opens:
                open_fills, deferred, fill_events = _apply_deferred_intents(
                    deferred,
                    opens=opens,
                    exec_svc=exec_svc,
                    risk=risk,
                    runtime=runtime,
                    session_id=session_id,
                    archetype=archetype,
                    clock=bar_time,
                )
                trade_id = _record_fills(
                    open_fills,
                    bar_time=bar_time,
                    prices=opens,
                    commission=commission,
                    trade_id=trade_id,
                    trades=trades,
                    orders=orders,
                )
                # Attach trade_id onto matching fill events when available.
                by_intent = {
                    str(f.get("intent_id") or ""): f.get("trade_id")
                    for f in open_fills
                    if f.get("intent_id") and f.get("trade_id") is not None
                }
                for ev in fill_events:
                    tid = by_intent.get(str(ev.get("intent_id") or ""))
                    if tid is not None:
                        ev["trade_id"] = tid
                execution_events.extend(fill_events)
                # Flip originating deferred signal rows → filled for reject-lens counts.
                if open_fills:
                    from app.modules.robots_v2.backtest.persist import (
                        promote_deferred_signals_to_filled,
                    )

                    promote_deferred_signals_to_filled(signal_events, fills=open_fills)

            if not is_within_trading_session(config.core.schedule, now=bar_time):
                # Still apply funding outside MOEX hours for 24/7 crypto perps.
                if funding_by_symbol and ledger.positions:
                    before_keys = len(applied_funding_keys)
                    funding_charges_total += apply_funding_charges_for_bar(
                        ledger,
                        funding_by_symbol=funding_by_symbol,
                        prev_bar_time=prev_bar_time,
                        bar_time=bar_time,
                        prices=prices,
                        applied_keys=applied_funding_keys,
                        mode=funding_mode,
                    )
                    funding_events_applied += len(applied_funding_keys) - before_keys
                skipped_schedule += 1
                prev_bar_time = bar_time
                continue

            day_key = bar_time.astimezone(MSK).date()
            if last_day is not None and day_key != last_day:
                risk.begin_trading_day(ledger.mark_equity(prices))
                eod_done = False
                risk.resume_entries()
            last_day = day_key

            # Active tradable set for this day (+ held names so we can manage open risk).
            if day_universe:
                todays = set(day_universe.get(day_key) or [])
                held = {str(t).upper() for t in ledger.positions.keys()}
                if config.universe.exit_on_drop and held - todays:
                    flat_drop = []
                    for t in sorted(held - todays):
                        pos = ledger.positions.get(t)
                        px = prices.get(t)
                        if pos is None or px is None or px <= 0:
                            continue
                        qty = int(pos.quantity)
                        side = "SELL" if pos.is_long else "BUY"
                        pnl = ledger.apply_fill(
                            ticker=t,
                            side=side,
                            quantity=qty,
                            price=px,
                            reduce_only=True,
                        )
                        flat_drop.append({
                            "ticker": t,
                            "kind": "flatten",
                            "side": side,
                            "qty": qty,
                            "price": px,
                            "pnl": pnl,
                            "reason": "universe_drop",
                        })
                    if flat_drop:
                        trade_id = _record_fills(
                            flat_drop,
                            bar_time=bar_time,
                            prices=prices,
                            commission=commission,
                            trade_id=trade_id,
                            trades=trades,
                            orders=orders,
                        )
                        held = {str(t).upper() for t in ledger.positions.keys()}
                active_universe = sorted(todays | held) or tickers
            else:
                active_universe = tickers

            in_eod = should_eod_flatten(
                risk=config.risk,
                schedule=config.core.schedule,
                instrument_type=config.core.instrument_type,
                now=bar_time,
            )
            if eod_done and not in_eod:
                eod_done = False
                risk.resume_entries()

            if in_eod:
                if not eod_done:
                    flat_fills = _flatten_all_positions(ledger, prices)
                    risk.pause_entries()
                    eod_done = True
                    trade_id = _record_fills(
                        flat_fills,
                        bar_time=bar_time,
                        prices=prices,
                        commission=commission,
                        trade_id=trade_id,
                        trades=trades,
                        orders=orders,
                    )
                if funding_by_symbol:
                    before_keys = len(applied_funding_keys)
                    funding_charges_total += apply_funding_charges_for_bar(
                        ledger,
                        funding_by_symbol=funding_by_symbol,
                        prev_bar_time=prev_bar_time,
                        bar_time=bar_time,
                        prices=prices,
                        applied_keys=applied_funding_keys,
                        mode=funding_mode,
                    )
                    funding_events_applied += len(applied_funding_keys) - before_keys
                snap = _portfolio_snapshot_row(bar_time=bar_time, ledger=ledger, prices=prices)
                equity_curve.append({"time": bar_time.isoformat(), "equity": snap["equity"]})
                portfolio_snapshots.append(snap)
                prev_bar_time = bar_time
                continue

            traded_bars += 1
            cycle_out = run_paper_cycle_sync(
                robot_id=robot_id,
                config=config,
                universe=active_universe,
                ledger=ledger,
                risk=risk,
                prices=prices,
                candle_history=history,
                session_id=session_id,
                cycle_number=cycle_num,
                execution=exec_svc,
                runtime=runtime,
                triggered_by="bar_close",
                allow_short=allow_short,
                now=bar_time,
            )
            new_deferred = list(cycle_out.get("deferred_intents") or [])
            for intent in new_deferred:
                _ensure_intent_id(intent)
                execution_events.append(_execution_event(
                    ts=bar_time,
                    intent=intent,
                    status="deferred",
                ))
            deferred.extend(new_deferred)

            for ev in list(cycle_out.get("signal_log") or []):
                if len(signal_events) >= _MAX_SIGNAL_LOG:
                    signals_truncated = True
                    break
                signal_events.append(ev)

            cycle_fills = list(cycle_out.get("fills") or [])
            for fill in cycle_fills:
                if not fill.get("intent_id"):
                    fill["intent_id"] = str(uuid4())
                execution_events.append(_execution_event(
                    ts=bar_time,
                    intent_id=str(fill.get("intent_id")),
                    cycle_id=str(fill.get("cycle_id")) if fill.get("cycle_id") else None,
                    ticker=str(fill.get("ticker") or ""),
                    side=str(fill.get("side") or "") or None,
                    kind=str(fill.get("kind") or "") or None,
                    status="filled",
                    reason=str(fill.get("reason") or "") or None,
                    quantity=fill.get("qty") or fill.get("quantity"),
                    price=float(fill.get("price") or 0) or None,
                    signal_time=str(fill.get("signal_time")) if fill.get("signal_time") else None,
                ))
            trade_id = _record_fills(
                cycle_fills,
                bar_time=bar_time,
                prices=prices,
                commission=commission,
                trade_id=trade_id,
                trades=trades,
                orders=orders,
            )
            # Back-fill trade_id on the just-appended fill events.
            for fill in cycle_fills:
                iid = str(fill.get("intent_id") or "")
                tid = fill.get("trade_id")
                if not iid or tid is None:
                    continue
                for ev in reversed(execution_events):
                    if ev.get("intent_id") == iid and ev.get("status") == "filled" and ev.get("trade_id") is None:
                        ev["trade_id"] = tid
                        break

            if funding_by_symbol:
                before_keys = len(applied_funding_keys)
                funding_charges_total += apply_funding_charges_for_bar(
                    ledger,
                    funding_by_symbol=funding_by_symbol,
                    prev_bar_time=prev_bar_time,
                    bar_time=bar_time,
                    prices=prices,
                    applied_keys=applied_funding_keys,
                    mode=funding_mode,
                )
                funding_events_applied += len(applied_funding_keys) - before_keys

            snap = _portfolio_snapshot_row(bar_time=bar_time, ledger=ledger, prices=prices)
            equity_curve.append({"time": bar_time.isoformat(), "equity": snap["equity"]})
            portfolio_snapshots.append(snap)
            prev_bar_time = bar_time

        # End-of-run: surface dropped deferred as reject signals + execution events.
        drop_ts = prev_bar_time or (timeline[-1] if timeline else datetime.now(timezone.utc))
        for intent in deferred:
            _ensure_intent_id(intent)
            meta = getattr(intent, "meta", None) or {}
            execution_events.append(_execution_event(
                ts=drop_ts,
                intent=intent,
                status="dropped",
                reject_reason="DROPPED_DEFERRED",
            ))
            if len(signal_events) < _MAX_SIGNAL_LOG:
                signal_events.append({
                    "signal_time": str(meta.get("signal_time") or drop_ts.isoformat()),
                    "figi": str(intent.figi or "").upper(),
                    "signal_type": str(intent.side or "BUY").upper(),
                    "price": float(intent.price or 0) or None,
                    "was_executed": 0,
                    "reason": intent.reason or None,
                    "reject_reason": "DROPPED_DEFERRED",
                    "kind": str(getattr(intent, "kind", None) or "entry"),
                    "status": "rejected",
                    "quantity": float(intent.quantity or 0) or None,
                    "cycle_id": str(meta["cycle_id"]) if meta.get("cycle_id") else None,
                    "intent_id": str(meta.get("intent_id") or ""),
                })
            else:
                signals_truncated = True
        dropped_deferred = len(deferred)
        deferred.clear()

        last_prices = {
            t: (history[t][-1].close if history.get(t) else 0.0)
            for t in tickers
        }
        final_equity = ledger.mark_equity(last_prices)
        ret_pct = 0.0
        if initial_capital > 0:
            ret_pct = (final_equity - initial_capital) / initial_capital * 100.0

        runtime.drop_session(session_id)

        daily_summary = _build_daily_summary(signal_events, trades)
        fee_summary = build_fee_summary(
            trades,
            funding_total=funding_charges_total,
            funding_events=funding_events_applied,
        )
        history_stats = {
            "bars": len(timeline),
            "tickers": len(tickers),
            "universe_days": len(day_universe),
            "trades": len(trades),
            "signals": len(signal_events),
            "signals_truncated": int(signals_truncated),
            "warmup_bars": warmup_bars,
            "traded_bars": traded_bars,
            "skipped_schedule": skipped_schedule,
            "dropped_deferred": dropped_deferred,
            "funding_events": funding_events_applied,
            "execution_events": len(execution_events),
        }
        narrative = build_run_narrative(
            initial_capital=initial_capital,
            final_equity=round(final_equity, 2),
            total_return_percent=round(ret_pct, 4),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            history_stats=history_stats,
            fee_summary=fee_summary,
            finished_at=drop_ts if isinstance(drop_ts, datetime) else None,
        )
        stages = [
            f"Replayed {len(timeline)} bars across {len(tickers)} tickers",
            f"Warmup bars: {warmup_bars}",
            f"Traded bars: {traded_bars}",
            f"Skipped (schedule): {skipped_schedule}",
            f"Trades: {len(trades)}",
            f"Signals logged: {len(signal_events)}"
            + (" (truncated)" if signals_truncated else ""),
            "Fills at next bar open (no look-ahead)",
        ]
        if funding_by_symbol:
            stages.append(
                f"Funding events applied: {funding_events_applied} "
                f"(cash adj {round(funding_charges_total, 4)})"
            )

        return BacktestHostResult(
            initial_capital=initial_capital,
            final_equity=round(final_equity, 2),
            total_return_percent=round(ret_pct, 4),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            trades=trades,
            equity_curve=equity_curve,
            portfolio_snapshots=portfolio_snapshots,
            orders=orders,
            signals=signal_events,
            daily_summary=daily_summary,
            stages=stages,
            history_stats=history_stats,
            funding_charges_total=round(funding_charges_total, 6),
            fee_summary=fee_summary,
            universe_by_day=dict(day_universe),
            execution_events=execution_events,
            narrative=narrative,
        )
