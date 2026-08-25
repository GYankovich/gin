"""Offline / public-Bybit reversion vs grid comparison (taker fee = 0.06%).

Uses robots_v2 BacktestHost. Synthetic regimes by default; optional real klines.

  cd backend
  python scripts/compare_bybit_reversion_grid.py
  python scripts/compare_bybit_reversion_grid.py --bybit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.backtest.host import BacktestHost
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4

CONFIG_DIR = Path(__file__).resolve().parent / "configs"
# Whole-coin paper sizing: need equity * maxPositionShare >= BTC price.
INITIAL = 200_000.0
INTERVAL = "CANDLE_INTERVAL_15_MIN"
BARS = 480  # ~5 days of 15m bars
BYBIT_KLINE = "https://api.bybit.com/v5/market/kline"


def _load_config(name: str) -> dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _sine_range(n: int, *, start: float, amp_pct: float) -> list[float]:
    """Sharper mean-reverting path so RSI can hit oversold/overbought."""
    out: list[float] = []
    px = start
    for i in range(n):
        cycle = math.sin(2 * math.pi * i / 36.0)  # ~9h period on 15m
        spike = 0.0
        if i % 37 == 0:
            spike = -amp_pct * 0.8
        elif i % 41 == 0:
            spike = amp_pct * 0.8
        target = start * (1.0 + amp_pct * cycle + spike)
        px = 0.45 * px + 0.55 * target
        out.append(px)
    return out


def _dump_then_chop(n: int, *, start: float) -> list[float]:
    out: list[float] = []
    px = start
    dump_end = n // 4
    for i in range(n):
        if i < dump_end:
            px *= 0.996
        else:
            px *= 1.0 + 0.012 * math.sin(2 * math.pi * (i - dump_end) / 28.0)
        out.append(px)
    return out


def _mixed(n: int, *, start: float) -> list[float]:
    a = _sine_range(n // 2, start=start, amp_pct=0.06)
    b = _dump_then_chop(n - len(a), start=a[-1])
    return a + b


def _closes_to_candles(closes: list[float], *, ticker: str) -> list[Candle]:
    base = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    prev = closes[0]
    for i, close in enumerate(closes):
        open_ = prev
        high = max(open_, close) * 1.001
        low = min(open_, close) * 0.999
        out.append(
            Candle(
                interval=INTERVAL,
                time=base + timedelta(minutes=15 * i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=50_000 + (i % 20) * 500,
                secid=ticker,
            )
        )
        prev = close
    return out


def _regime_series(kind: str) -> dict[str, list[Candle]]:
    if kind == "range":
        btc = _sine_range(BARS, start=65_000.0, amp_pct=0.06)
        eth = _sine_range(BARS, start=3_400.0, amp_pct=0.08)
    elif kind == "dump":
        btc = _dump_then_chop(BARS, start=65_000.0)
        eth = _dump_then_chop(BARS, start=3_400.0)
    else:
        btc = _mixed(BARS, start=65_000.0)
        eth = _mixed(BARS, start=3_400.0)
    return {
        "BTCUSDT": _closes_to_candles(btc, ticker="BTCUSDT"),
        "ETHUSDT": _closes_to_candles(eth, ticker="ETHUSDT"),
    }


def _fetch_bybit_klines(symbol: str, *, limit: int = 500) -> list[Candle]:
    """Public linear klines (15m). No API key."""
    qs = urllib.parse.urlencode({
        "category": "linear",
        "symbol": symbol,
        "interval": "15",
        "limit": str(min(limit, 1000)),
    })
    with urllib.request.urlopen(f"{BYBIT_KLINE}?{qs}", timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if str(payload.get("retCode")) not in ("0", "0.0"):
        raise RuntimeError(f"Bybit kline error for {symbol}: {payload}")
    rows = list(payload.get("result", {}).get("list") or [])
    rows.reverse()  # API is newest-first
    out: list[Candle] = []
    for row in rows:
        ts_ms = int(row[0])
        o, h, low, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        vol = float(row[5])
        out.append(
            Candle(
                interval=INTERVAL,
                time=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                open=o,
                high=h,
                low=low,
                close=c,
                volume=vol,
                secid=symbol,
            )
        )
    return out


def _bybit_series() -> dict[str, list[Candle]]:
    return {
        "BTCUSDT": _fetch_bybit_klines("BTCUSDT", limit=500),
        "ETHUSDT": _fetch_bybit_klines("ETHUSDT", limit=500),
    }


def _with_archetype(base: dict[str, Any], strategy_block: dict[str, Any]) -> TradingRobotConfigV4:
    cfg = deepcopy(base)
    cfg["strategy"] = strategy_block
    cfg["strategy"]["timeframe"] = "15m"
    cfg["risk"]["brokerCommissionPct"] = 0.06  # taker
    return TradingRobotConfigV4.model_validate(cfg)


async def _run_one(
    *,
    label: str,
    config: TradingRobotConfigV4,
    candles: dict[str, list[Candle]],
    session_id: int,
) -> dict[str, Any]:
    host = BacktestHost()
    result = await host.run(
        config=config,
        universe=["BTCUSDT", "ETHUSDT"],
        candles_by_ticker=candles,
        initial_capital=INITIAL,
        session_id=session_id,
        robot_id=session_id,
    )
    fills = result.trades
    # Entry fills often carry pnl_net=0; score only realized exit PnL.
    pnls = [float(t["pnl_net"]) for t in fills if abs(float(t.get("pnl_net") or 0)) > 1e-9]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "label": label,
        "final_equity": result.final_equity,
        "return_pct": result.total_return_percent,
        "max_dd_pct": result.max_drawdown_percent,
        "trades": len(fills),
        "closed_with_pnl": len(pnls),
        "win_rate_pct": round(100.0 * wins / len(pnls), 1) if pnls else None,
        "sum_pnl": round(sum(pnls), 2) if pnls else 0.0,
    }


def _print_table(title: str, rows: list[dict[str, Any]]) -> None:
    print(title)
    print(f"{'run':<22} {'ret%':>8} {'maxDD%':>8} {'trades':>7} {'win%':>7} {'equity':>10}")
    print("-" * 70)
    for r in rows:
        wr = "-" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}"
        print(
            f"{r['label']:<22} {r['return_pct']:>8.2f} {r['max_dd_pct']:>8.2f} "
            f"{r['trades']:>7} {wr:>7} {r['final_equity']:>10.2f}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bybit",
        action="store_true",
        help="Use public Bybit 15m klines (BTC/ETH) instead of synthetic regimes",
    )
    args = parser.parse_args()

    rev_base = _load_config("bybit_reversion_paper.json")
    grid_base = _load_config("bybit_grid_paper.json")
    rev_cfg = _with_archetype(rev_base, rev_base["strategy"])
    grid_cfg = _with_archetype(grid_base, grid_base["strategy"])

    rows: list[dict[str, Any]] = []
    sid = 910_001

    if args.bybit:
        candles = _bybit_series()
        n = min(len(candles["BTCUSDT"]), len(candles["ETHUSDT"]))
        for label, cfg in (("reversion", rev_cfg), ("grid", grid_cfg)):
            row = await _run_one(
                label=f"{label}/bybit",
                config=cfg,
                candles=candles,
                session_id=sid,
            )
            row["archetype"] = label
            row["regime"] = "bybit"
            rows.append(row)
            sid += 1
        _print_table(
            f"Bybit public klines | fee=taker 0.06% | capital={int(INITIAL)} | bars~{n} | TF=15m",
            rows,
        )
        a, b = rows[0], rows[1]
        better = "reversion" if a["return_pct"] >= b["return_pct"] else "grid"
        safer = "reversion" if a["max_dd_pct"] <= b["max_dd_pct"] else "grid"
        print(f"\nVerdict: higher return -> {better}; lower DD -> {safer}")
        return

    regimes = ("range", "dump", "mixed")
    for regime in regimes:
        candles = _regime_series(regime)
        for label, cfg in (("reversion", rev_cfg), ("grid", grid_cfg)):
            row = await _run_one(
                label=f"{label}/{regime}",
                config=cfg,
                candles=candles,
                session_id=sid,
            )
            row["archetype"] = label
            row["regime"] = regime
            rows.append(row)
            sid += 1

    _print_table(
        f"Synthetic regimes | fee=taker 0.06% | capital={int(INITIAL)} | bars={BARS} | TF=15m",
        rows,
    )
    print("\nVerdict hint:")
    for regime in regimes:
        a = next(r for r in rows if r["archetype"] == "reversion" and r["regime"] == regime)
        b = next(r for r in rows if r["archetype"] == "grid" and r["regime"] == regime)
        better = "reversion" if a["return_pct"] >= b["return_pct"] else "grid"
        safer = "reversion" if a["max_dd_pct"] <= b["max_dd_pct"] else "grid"
        print(f"  {regime}: higher return -> {better}; lower DD -> {safer}")


if __name__ == "__main__":
    asyncio.run(main())
