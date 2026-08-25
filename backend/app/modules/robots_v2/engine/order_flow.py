"""Order-flow aggregator for scalper (trade/price tick → delta%).

Volumes are stored as **notional** (price × size) so minLiquidity works
across MOEX ₽ and crypto USDT without unit confusion.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque

from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot


@dataclass
class _Tick:
    ts: datetime
    price: float
    side: str  # buy | sell
    volume: float  # notional
    real_trade: bool = False


class OrderFlowAggregator:
    """Rolling window buy/sell notional from trades or inferred price ticks."""

    def __init__(self, *, window_sec: int = 30) -> None:
        self.window_sec = max(5, int(window_sec))
        self._ticks: dict[str, Deque[_Tick]] = defaultdict(deque)
        self._last_price: dict[str, float] = {}
        self._has_real_trades: dict[str, bool] = defaultdict(bool)

    def on_price(self, ticker: str, price: float, *, volume: float = 1.0, now: datetime | None = None) -> None:
        """Price tick — side inferred (uptick/downtick). Skipped if real trades already flowing."""
        t = ticker.upper()
        if self._has_real_trades.get(t):
            self._last_price[t] = price
            return
        ts = now or datetime.now(timezone.utc)
        prev = self._last_price.get(t)
        if prev is None or price >= prev:
            side = "buy"
        else:
            side = "sell"
        self._last_price[t] = price
        # Caller may pass size (small) or notional (~price scale)
        vol = max(0.0, float(volume))
        if vol >= max(price * 0.5, 1.0):
            notional = vol
        else:
            notional = vol * max(float(price), 0.0)
        if notional <= 0:
            notional = max(float(price), 1.0)
        q = self._ticks[t]
        q.append(_Tick(ts=ts, price=price, side=side, volume=notional, real_trade=False))
        self._trim(t, ts)

    def on_trade(
        self,
        ticker: str,
        *,
        price: float,
        side: str,
        volume: float,
        now: datetime | None = None,
        turnover: float | None = None,
    ) -> None:
        t = ticker.upper()
        ts = now or datetime.now(timezone.utc)
        self._last_price[t] = price
        self._has_real_trades[t] = True
        notional = float(turnover) if turnover and turnover > 0 else max(0.0, float(volume)) * max(float(price), 0.0)
        self._ticks[t].append(
            _Tick(
                ts=ts,
                price=price,
                side="buy" if side.lower().startswith("b") else "sell",
                volume=max(0.0, notional),
                real_trade=True,
            )
        )
        self._trim(t, ts)

    def _trim(self, ticker: str, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.window_sec)
        q = self._ticks[ticker]
        while q and q[0].ts < cutoff:
            q.popleft()

    def snapshot(self, ticker: str, *, now: datetime | None = None) -> OrderFlowSnapshot | None:
        t = ticker.upper()
        ts = now or datetime.now(timezone.utc)
        self._trim(t, ts)
        q = self._ticks.get(t)
        if not q:
            return None
        buy = sum(x.volume for x in q if x.side == "buy")
        sell = sum(x.volume for x in q if x.side == "sell")
        total = buy + sell
        if total <= 0:
            return None
        delta_pct = (buy - sell) / total * 100.0
        tick_count = len(q)
        trade_count = sum(1 for x in q if x.real_trade)
        has_real = bool(self._has_real_trades.get(t) or trade_count > 0)
        return OrderFlowSnapshot(
            buyVolume=buy,
            sellVolume=sell,
            deltaPct=delta_pct,
            windowSec=self.window_sec,
            tickCount=tick_count,
            tradeCount=trade_count,
            hasRealTrades=has_real,
            flowSource="trades" if has_real else "inferred",
        )

    def snapshots(self, tickers: list[str], *, now: datetime | None = None) -> dict[str, OrderFlowSnapshot]:
        out: dict[str, OrderFlowSnapshot] = {}
        for raw in tickers:
            snap = self.snapshot(raw, now=now)
            if snap is not None:
                out[raw.upper()] = snap
        return out
