"""Historical bar replay using robots v2 unified trading cycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.cycle import run_trading_cycle
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.risk.engine import RiskEngine
from app.modules.robots_v2.strategy.runtime import strategy_runtime


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
    """Replay OHLCV bars through run_trading_cycle (ADR-02 unified pipeline)."""

    async def run(
        self,
        *,
        config: TradingRobotConfigV4,
        universe: list[str],
        candles_by_ticker: dict[str, list[Candle]],
        initial_capital: float,
        session_id: int,
        robot_id: int = 0,
        user_id: int = 0,
        is_cancelled: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int], Awaitable[None] | None] | None = None,
    ) -> BacktestHostResult:
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

        commission = config.risk.broker_commission_pct / 100.0
        allow_short = config.core.instrument_type in ("perpetual", "coin_futures")
        ledger = PaperLedger(cash=initial_capital, commission_rate=commission, allow_short=allow_short)
        risk = RiskEngine(config.risk, allow_short=allow_short)
        risk.begin_session(initial_capital)

        equity_curve: list[dict[str, Any]] = []
        portfolio_snapshots: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        trade_id = 0

        # Index candles by time for fast slicing
        idx_by_ticker: dict[str, dict[datetime, Candle]] = {}
        sorted_by_ticker: dict[str, list[Candle]] = {}
        for t in tickers:
            series = candles_by_ticker.get(t, [])
            sorted_by_ticker[t] = series
            idx_by_ticker[t] = {c.time: c for c in series}

        history: dict[str, list[Candle]] = {t: [] for t in tickers}
        total_bars = len(timeline)

        for cycle_num, bar_time in enumerate(timeline, start=1):
            if is_cancelled and is_cancelled():
                break
            if progress_callback:
                maybe = progress_callback(cycle_num, total_bars)
                if asyncio.iscoroutine(maybe):
                    await maybe

            prices: dict[str, float] = {}
            for t in tickers:
                bar = idx_by_ticker[t].get(bar_time)
                if bar is not None:
                    history[t].append(bar)
                    prices[t] = float(bar.close)

            if not prices:
                continue

            candle_history = {t: list(history[t]) for t in tickers if history[t]}

            cycle_out = await run_trading_cycle(
                robot_id=robot_id,
                user_id=user_id,
                config=config,
                universe=tickers,
                ledger=ledger,
                risk=risk,
                prices=prices,
                candle_history=candle_history,
                session_id=session_id,
                cycle_number=cycle_num,
                triggered_by="bar_close",
                allow_short=allow_short,
            )

            equity = ledger.mark_equity(prices)
            equity_curve.append({"time": bar_time.isoformat(), "equity": round(equity, 2)})
            portfolio_snapshots.append({
                "snapshot_time": bar_time.isoformat(),
                "equity": round(equity, 2),
                "cash": round(ledger.cash, 2),
                "positions": len(ledger.positions),
            })

            for fill in cycle_out.get("fills") or []:
                trade_id += 1
                ticker = str(fill.get("ticker") or "")
                kind = str(fill.get("kind") or "")
                side = str(fill.get("side") or ("SELL" if "exit" in kind else "BUY"))
                qty = int(fill.get("qty") or 0) or 1
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
                })
                orders.append({
                    "ticker": ticker,
                    "side": side,
                    "quantity": qty,
                    "price": price,
                    "time": bar_time.isoformat(),
                    "kind": kind,
                })

        last_prices = {
            t: (history[t][-1].close if history.get(t) else 0.0)
            for t in tickers
        }
        final_equity = ledger.mark_equity(last_prices)
        ret_pct = 0.0
        if initial_capital > 0:
            ret_pct = (final_equity - initial_capital) / initial_capital * 100.0

        strategy_runtime.drop_session(session_id)

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
                f"Trades: {len(trades)}",
            ],
            history_stats={"bars": len(timeline), "tickers": len(tickers), "trades": len(trades)},
        )
