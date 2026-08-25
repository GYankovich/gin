"""Historical bar replay using robots v2 unified trading cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.modules.robots.trading.contracts import Candle, OrderIntent
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
        trades.append({
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
        })
        orders.append({
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "price": price,
            "time": bar_time.isoformat(),
            "kind": kind,
            "reason": reason or None,
        })
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
) -> tuple[list[dict[str, Any]], list[OrderIntent]]:
    """Fill yesterday's close signals at this bar's open. Unpriced names stay queued."""
    fills: list[dict[str, Any]] = []
    leftover: list[OrderIntent] = []
    for intent in intents:
        ticker = str(intent.figi or "").upper()
        px = float(opens.get(ticker) or 0)
        if px <= 0:
            leftover.append(intent)
            continue
        if str(getattr(intent, "order_type", None) or "MARKET").upper() != "LIMIT":
            intent.price = px
        result = exec_svc.execute_intent_sync(intent, last_price=px)
        if result.status in ("filled", "submitted"):
            risk.record_realized_pnl(result.pnl)
            kind = str(getattr(intent, "kind", None) or "entry")
            fills.append({
                "ticker": result.ticker,
                "kind": kind,
                "side": result.side,
                "reason": intent.reason,
                "qty": result.quantity,
                "price": result.price,
                "pnl": result.pnl,
                "status": result.status,
            })
            if str(intent.reason or "") == "stop_loss":
                runtime.notify_stop_loss(session_id, archetype, result.ticker, at=clock)
        elif result.status != "resting":
            leftover.append(intent)
    return fills, leftover


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
    stages: list[str] = field(default_factory=list)
    history_stats: dict[str, int] = field(default_factory=dict)


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
    ) -> BacktestHostResult:
        _ = user_id
        tickers = [t.upper() for t in universe if t]
        candles_by_ticker = {k.upper(): v for k, v in candles_by_ticker.items()}
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
        trade_id = 0
        skipped_schedule = 0
        warmup_bars = 0
        traded_bars = 0
        eod_done = False
        last_day: date | None = None

        idx_by_ticker: dict[str, dict[datetime, Candle]] = {}
        for t in tickers:
            series = candles_by_ticker.get(t, [])
            idx_by_ticker[t] = {c.time: c for c in series}

        history: dict[str, list[Candle]] = {t: [] for t in tickers}
        total_bars = len(timeline)
        last_progress = 0
        deferred: list[OrderIntent] = []
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
                continue

            if deferred and opens:
                open_fills, deferred = _apply_deferred_intents(
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

            if not is_within_trading_session(config.core.schedule, now=bar_time):
                skipped_schedule += 1
                continue

            day_key = bar_time.astimezone(MSK).date()
            if last_day is not None and day_key != last_day:
                risk.begin_trading_day(ledger.mark_equity(prices))
                eod_done = False
                risk.resume_entries()
            last_day = day_key

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
                equity = ledger.mark_equity(prices)
                equity_curve.append({"time": bar_time.isoformat(), "equity": round(equity, 2)})
                portfolio_snapshots.append({
                    "snapshot_time": bar_time.isoformat(),
                    "equity": round(equity, 2),
                    "cash": round(ledger.cash, 2),
                    "positions": len(ledger.positions),
                })
                continue

            traded_bars += 1
            cycle_out = run_paper_cycle_sync(
                robot_id=robot_id,
                config=config,
                universe=tickers,
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
            deferred.extend(list(cycle_out.get("deferred_intents") or []))

            equity = ledger.mark_equity(prices)
            equity_curve.append({"time": bar_time.isoformat(), "equity": round(equity, 2)})
            portfolio_snapshots.append({
                "snapshot_time": bar_time.isoformat(),
                "equity": round(equity, 2),
                "cash": round(ledger.cash, 2),
                "positions": len(ledger.positions),
            })

            trade_id = _record_fills(
                list(cycle_out.get("fills") or []),
                bar_time=bar_time,
                prices=prices,
                commission=commission,
                trade_id=trade_id,
                trades=trades,
                orders=orders,
            )

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

        return BacktestHostResult(
            initial_capital=initial_capital,
            final_equity=round(final_equity, 2),
            total_return_percent=round(ret_pct, 4),
            max_drawdown_percent=max_drawdown_percent(equity_curve),
            trades=trades,
            equity_curve=equity_curve,
            portfolio_snapshots=portfolio_snapshots,
            orders=orders,
            stages=[
                f"Replayed {len(timeline)} bars across {len(tickers)} tickers",
                f"Warmup bars: {warmup_bars}",
                f"Traded bars: {traded_bars}",
                f"Skipped (schedule): {skipped_schedule}",
                f"Trades: {len(trades)}",
                "Fills at next bar open (no look-ahead)",
            ],
            history_stats={
                "bars": len(timeline),
                "tickers": len(tickers),
                "trades": len(trades),
                "warmup_bars": warmup_bars,
                "traded_bars": traded_bars,
                "skipped_schedule": skipped_schedule,
                "dropped_deferred": dropped_deferred,
            },
        )
