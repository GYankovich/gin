"""Analyze last N fills with exit reason and round-trip PnL."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

ROBOT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 25
HOURS = int(sys.argv[3]) if len(sys.argv) > 3 else 24


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=HOURS)
        fills = db.execute(
            text(
                f"""
                SELECT f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind,
                       f.order_id, o.broker_order_id
                FROM {schema}.robots_v2_fills f
                LEFT JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
                WHERE f.robot_id = :rid AND f.filled_at >= :since
                ORDER BY f.filled_at DESC
                LIMIT :lim
                """
            ),
            {"rid": ROBOT_ID, "since": since, "lim": LIMIT},
        ).fetchall()

        print(f"=== LAST {len(fills)} FILLS (last {HOURS}h, newest first) ===")
        for f in fills:
            print(
                f"  {f.filled_at} {f.ticker:6} {f.side:4} qty={float(f.quantity):g} "
                f"px={float(f.price):.4f} kind={f.kind} pnl={float(f.pnl or 0):+.2f}"
            )

        # Round trips for sells in window — match to prior buys
        all_fills = db.execute(
            text(
                f"""
                SELECT f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind
                FROM {schema}.robots_v2_fills f
                WHERE f.robot_id = :rid AND f.filled_at >= :since
                ORDER BY f.filled_at ASC
                """
            ),
            {"rid": ROBOT_ID, "since": since},
        ).fetchall()

        lots: dict[str, list[dict]] = defaultdict(list)
        losses: list[dict] = []
        for f in all_fills:
            t = str(f.ticker).upper()
            side = str(f.side).upper()
            qty = float(f.quantity)
            px = float(f.price)
            if side == "BUY":
                lots[t].append({"qty": qty, "px": px, "ts": f.filled_at})
            elif side == "SELL" and lots[t]:
                rem = qty
                while rem > 0 and lots[t]:
                    lot = lots[t][0]
                    take = min(rem, lot["qty"])
                    gross = (px - lot["px"]) * take
                    hold = (f.filled_at - lot["ts"]).total_seconds()
                    move_bps = (px - lot["px"]) / lot["px"] * 10000 if lot["px"] else 0
                    if gross < 0 or float(f.pnl or 0) < 0:
                        losses.append({
                            "exit_ts": f.filled_at,
                            "ticker": t,
                            "kind": f.kind,
                            "entry_px": lot["px"],
                            "exit_px": px,
                            "qty": take,
                            "gross": gross,
                            "ledger_pnl": float(f.pnl or 0),
                            "hold_sec": hold,
                            "move_bps": move_bps,
                        })
                    rem -= take
                    lot["qty"] -= take
                    if lot["qty"] <= 1e-9:
                        lots[t].pop(0)

        print(f"\n=== LOSING EXITS ({len(losses)}) ===")
        for r in sorted(losses, key=lambda x: x["exit_ts"], reverse=True):
            print(
                f"  {r['exit_ts']} {r['ticker']:6} kind={r['kind']:14} "
                f"{r['entry_px']:.2f}->{r['exit_px']:.2f} ({r['move_bps']:+.1f}bps) "
                f"hold={r['hold_sec']:.0f}s gross={r['gross']:+.2f} ledger={r['ledger_pnl']:+.2f}"
            )

        # Match exit decisions for losing trades
        if losses:
            tickers = list({r["ticker"] for r in losses})
            min_ts = min(r["exit_ts"] for r in losses)
            decs = db.execute(
                text(
                    f"""
                    SELECT d.created_at, d.ticker, d.stage, d.code, d.message, d.context
                    FROM {schema}.robots_v2_decisions d
                    WHERE d.robot_id = :rid
                      AND d.ticker = ANY(:tickers)
                      AND d.created_at >= :since
                      AND d.stage IN ('exits', 'strategy')
                    ORDER BY d.created_at DESC
                    """
                ),
                {"rid": ROBOT_ID, "tickers": tickers, "since": min_ts - timedelta(minutes=5)},
            ).fetchall()

            print("\n=== EXIT DECISIONS / SIGNALS for losers ===")
            dec_by_ts: dict[str, list] = defaultdict(list)
            for d in decs:
                key = f"{d.created_at} {d.ticker}"
                dec_by_ts[key].append(d)

            seen = set()
            for r in losses:
                # find closest decision within 2 sec
                match = None
                for d in decs:
                    if str(d.ticker).upper() != r["ticker"]:
                        continue
                    dt = abs((d.created_at - r["exit_ts"]).total_seconds())
                    if dt <= 2 and d.created_at not in seen:
                        match = d
                        seen.add(d.created_at)
                        break
                if match:
                    ctx = match.context if isinstance(match.context, dict) else {}
                    slim = {k: ctx.get(k) for k in (
                        "reason", "entryPrice", "exitPrice", "markPrice", "stopLoss",
                        "takeProfit", "deltaPct", "code", "blockReason",
                    ) if ctx.get(k) is not None}
                    print(
                        f"  {r['exit_ts']} {r['ticker']} [{match.stage}] {match.code}: "
                        f"{(match.message or '')[:90]}"
                    )
                    if slim:
                        print(f"    -> {json.dumps(slim, default=str)}")
                else:
                    # check signals
                    sig = db.execute(
                        text(
                            f"""
                            SELECT created_at, side, reason, price FROM {schema}.robots_v2_signals
                            WHERE robot_id = :rid AND ticker = :t
                              AND created_at BETWEEN :t0 AND :t1
                            ORDER BY created_at DESC LIMIT 1
                            """
                        ),
                        {
                            "rid": ROBOT_ID,
                            "t": r["ticker"],
                            "t0": r["exit_ts"] - timedelta(seconds=2),
                            "t1": r["exit_ts"] + timedelta(seconds=2),
                        },
                    ).fetchone()
                    if sig:
                        print(
                            f"  {r['exit_ts']} {r['ticker']} signal={sig.reason} "
                            f"px={sig.price} (no exit decision matched)"
                        )
                    else:
                        print(f"  {r['exit_ts']} {r['ticker']} (no decision/signal matched)")

        print("\n=== SUMMARY BY EXIT KIND (losses only) ===")
        by_kind: dict[str, dict] = defaultdict(lambda: {"n": 0, "ledger": 0.0})
        for r in losses:
            by_kind[r["kind"]]["n"] += 1
            by_kind[r["kind"]]["ledger"] += r["ledger_pnl"]
        for k, v in sorted(by_kind.items(), key=lambda x: x[1]["ledger"]):
            print(f"  {k}: n={v['n']} total_ledger={v['ledger']:.2f}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
