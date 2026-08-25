"""Pair fills into round-trips with hold time and exit reason."""
from __future__ import annotations

import json
import sys
from collections import defaultdict

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

ROBOT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
SINCE = "2026-08-14"
TICKERS = ["SMLT", "X5"]
if len(sys.argv) > 2:
    args = sys.argv[2:]
    if args[-1].startswith("20"):
        SINCE = args[-1]
        args = args[:-1]
    if args:
        TICKERS = [t.upper() for t in args]


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        fills = db.execute(
            text(
                f"""
                SELECT f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind, f.order_id
                FROM {schema}.robots_v2_fills f
                WHERE f.robot_id = :rid AND f.ticker = ANY(:tickers)
                  AND f.filled_at >= CAST(:since AS timestamptz)
                ORDER BY f.filled_at ASC
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS, "since": SINCE},
        ).fetchall()

        lots: dict[str, list[dict]] = defaultdict(list)
        print(f"=== ROUND TRIPS since {SINCE} ===")
        for f in fills:
            t = str(f.ticker).upper()
            side = str(f.side).upper()
            qty = float(f.quantity)
            px = float(f.price)
            if side == "BUY":
                lots[t].append({"qty": qty, "px": px, "ts": f.filled_at})
                print(f"  ENTRY  {f.filled_at} {t} BUY {qty} @ {px:.4f}")
            elif side == "SELL" and lots[t]:
                rem = qty
                while rem > 0 and lots[t]:
                    lot = lots[t][0]
                    take = min(rem, lot["qty"])
                    gross = (px - lot["px"]) * take
                    hold = (f.filled_at - lot["ts"]).total_seconds()
                    move_bps = (px - lot["px"]) / lot["px"] * 10000 if lot["px"] else 0
                    print(
                        f"  EXIT   {f.filled_at} {t} SELL {take} @ {px:.4f} "
                        f"kind={f.kind} entry={lot['px']:.4f} gross={gross:.2f} "
                        f"ledger_pnl={float(f.pnl or 0):.2f} hold={hold:.0f}s move={move_bps:.1f}bps"
                    )
                    rem -= take
                    lot["qty"] -= take
                    if lot["qty"] <= 1e-9:
                        lots[t].pop(0)

        print("\n=== EXIT DECISIONS since", SINCE, "===")
        decs = db.execute(
            text(
                f"""
                SELECT d.created_at, d.ticker, d.stage, d.code, d.message, d.context
                FROM {schema}.robots_v2_decisions d
                WHERE d.robot_id = :rid AND d.ticker = ANY(:tickers)
                  AND d.created_at >= CAST(:since AS timestamptz)
                  AND d.stage IN ('exits', 'strategy')
                ORDER BY d.created_at ASC
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS, "since": SINCE},
        ).fetchall()
        for d in decs:
            ctx = d.context if isinstance(d.context, dict) else {}
            print(f"  {d.created_at} [{d.stage}] {d.ticker} {d.code} {d.message or ''}")
            if ctx:
                slim = {k: ctx[k] for k in ctx if k in (
                    "kind", "reason", "entryPrice", "exitPrice", "markPrice", "stopLoss",
                    "takeProfit", "deltaPct", "buyVolume", "sellVolume", "blockReason",
                    "minHoldSec", "minExitMoveBps", "code", "metrics",
                )}
                if slim:
                    print(f"    ctx={json.dumps(slim, default=str)}")

        print("\n=== ROBOT RISK CONFIG ===")
        row = db.execute(
            text(f"SELECT config FROM {schema}.robots_v2 WHERE id = :id"),
            {"id": ROBOT_ID},
        ).fetchone()
        if row and row.config:
            cfg = row.config
            risk = (cfg.get("risk") or {})
            strat = (cfg.get("strategy") or {})
            params = (strat.get("params") or {})
            print(json.dumps({
                "stopLossPct": risk.get("stopLossPct"),
                "takeProfitPct": risk.get("takeProfitPct"),
                "minHoldSec": params.get("minHoldSec"),
                "minExitMoveBps": params.get("minExitMoveBps"),
                "deltaThresholdPct": params.get("deltaThresholdPct"),
            }, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
