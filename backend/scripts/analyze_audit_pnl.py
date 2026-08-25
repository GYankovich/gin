"""Analyze robots v2 audit fills PnL for a robot."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

ROBOT_ID = 1


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        tables = db.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = :schema AND tablename LIKE 'robots_v2_%'
                ORDER BY 1
                """
            ),
            {"schema": schema},
        ).fetchall()
        print("=== TABLES ===")
        print([r[0] for r in tables])

        counts = {}
        for t in [r[0] for r in tables]:
            counts[t] = db.execute(text(f"SELECT COUNT(*) FROM {schema}.{t}")).scalar()
        print("=== COUNTS ===")
        for k, v in counts.items():
            print(f"  {k}: {v}")

        sessions = db.execute(
            text(
                f"""
                SELECT id, mode, started_at, ended_at, stop_reason, virtual_capital
                FROM {schema}.robots_v2_sessions
                WHERE robot_id = :rid
                ORDER BY started_at DESC
                LIMIT 10
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print(f"\n=== SESSIONS robot={ROBOT_ID} (last 10) ===")
        for s in sessions:
            print(
                f"  {s.id} mode={s.mode} start={s.started_at} end={s.ended_at} "
                f"stop={s.stop_reason} cap={s.virtual_capital}"
            )

        fills = db.execute(
            text(
                f"""
                SELECT f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind, f.filled_at,
                       o.broker_order_id
                FROM {schema}.robots_v2_fills f
                LEFT JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
                WHERE f.robot_id = :rid
                ORDER BY f.filled_at ASC
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()

        print(f"\n=== FILLS robot={ROBOT_ID} total={len(fills)} ===")
        if not fills:
            print("  (no fills in audit yet — migration/deploy or session before audit?)")
            return

        ledger_pnl_sum = sum(float(f.pnl or 0) for f in fills)

        # Price-based round-trip PnL (FIFO per ticker, long-only scalper)
        positions: dict[str, list[tuple[float, float]]] = defaultdict(list)
        price_pnl_by_ticker: dict[str, float] = defaultdict(float)
        price_pnl_total = 0.0
        round_trips = 0
        wins = 0
        losses = 0

        for f in fills:
            ticker = str(f.ticker).upper()
            side = str(f.side).upper()
            qty = float(f.quantity)
            price = float(f.price)
            ts = f.filled_at

            if side == "BUY":
                positions[ticker].append((qty, price))
            elif side == "SELL" and positions[ticker]:
                rem = qty
                while rem > 0 and positions[ticker]:
                    lot_qty, lot_px = positions[ticker][0]
                    take = min(rem, lot_qty)
                    pnl = (price - lot_px) * take
                    price_pnl_total += pnl
                    price_pnl_by_ticker[ticker] += pnl
                    round_trips += 1
                    if pnl >= 0:
                        wins += 1
                    else:
                        losses += 1
                    rem -= take
                    if lot_qty - take <= 1e-9:
                        positions[ticker].pop(0)
                    else:
                        positions[ticker][0] = (lot_qty - take, lot_px)

            print(
                f"  {ts} {ticker} {side} qty={qty} px={price:.4f} kind={f.kind} "
                f"ledger_pnl={float(f.pnl or 0):.2f}"
            )

        print("\n=== SUMMARY ===")
        print(f"  Ledger PnL sum (audit column): {ledger_pnl_sum:.2f}")
        print(f"  Price-based closed PnL (FIFO): {price_pnl_total:.2f}")
        print(f"  Round trips closed: {round_trips} (W={wins} L={losses})")
        print(f"  Open lots left: { {k: v for k,v in positions.items() if v} }")

        print("\n=== PnL BY TICKER (price-based) ===")
        for t, p in sorted(price_pnl_by_ticker.items(), key=lambda x: x[1]):
            print(f"  {t}: {p:.2f}")

        print("\n=== PnL BY KIND (ledger column) ===")
        by_kind: dict[str, float] = defaultdict(float)
        for f in fills:
            by_kind[str(f.kind)] += float(f.pnl or 0)
        for k, p in sorted(by_kind.items(), key=lambda x: x[1]):
            print(f"  {k}: {p:.2f}")

        # Decisions deny breakdown
        denies = db.execute(
            text(
                f"""
                SELECT code, COUNT(*) cnt
                FROM {schema}.robots_v2_decisions
                WHERE robot_id = :rid AND outcome = 'deny'
                GROUP BY code ORDER BY cnt DESC LIMIT 15
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print("\n=== TOP DENY CODES ===")
        for d in denies:
            print(f"  {d.code}: {d.cnt}")

        skips = db.execute(
            text(
                f"""
                SELECT skip_reason, COUNT(*) cnt
                FROM {schema}.robots_v2_cycles
                WHERE robot_id = :rid AND status = 'skip'
                GROUP BY skip_reason ORDER BY cnt DESC
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print("\n=== SKIP CYCLES ===")
        for s in skips:
            print(f"  {s.skip_reason}: {s.cnt}")

        # Ledger bug check: exit_strategy fills with huge pnl
        weird = [
            f for f in fills
            if str(f.kind) == "exit_strategy" and abs(float(f.pnl or 0)) > 1000
        ]
        if weird:
            print(f"\n=== SUSPICIOUS exit_strategy ledger pnl ({len(weird)} rows) ===")
            for f in weird[:5]:
                print(f"  {f.ticker} ledger_pnl={float(f.pnl or 0):.2f} px={float(f.price):.4f}")

        # Round-trip analysis with commission
        COMMISSION = 0.0005
        positions_rt: dict[str, list[dict]] = defaultdict(list)
        rounds: list[dict] = []
        for f in fills:
            t = str(f.ticker).upper()
            side = str(f.side).upper()
            qty = float(f.quantity)
            px = float(f.price)
            ts = f.filled_at
            kind = str(f.kind)
            if side == "BUY":
                positions_rt[t].append({"qty": qty, "px": px, "ts": ts})
            elif side == "SELL" and positions_rt[t]:
                rem = qty
                entry_ts = None
                entry_px = None
                pnl_gross = 0.0
                comm = 0.0
                while rem > 0 and positions_rt[t]:
                    lot = positions_rt[t][0]
                    take = min(rem, lot["qty"])
                    pnl_gross += (px - lot["px"]) * take
                    comm += (lot["px"] + px) * take * COMMISSION
                    entry_ts = lot["ts"]
                    entry_px = lot["px"]
                    rem -= take
                    lot["qty"] -= take
                    if lot["qty"] <= 1e-9:
                        positions_rt[t].pop(0)
                hold_sec = (ts - entry_ts).total_seconds() if entry_ts else 0.0
                net = pnl_gross - comm
                move_pct = (px - entry_px) / entry_px * 100.0 if entry_px else 0.0
                rounds.append({
                    "ticker": t, "kind": kind, "entry_px": entry_px, "exit_px": px,
                    "qty": qty, "gross": pnl_gross, "comm": comm, "net": net,
                    "hold_sec": hold_sec, "move_pct": move_pct,
                })

        if rounds:
            wins = [r for r in rounds if r["net"] >= 0]
            losses = [r for r in rounds if r["net"] < 0]
            ex_banep = [r for r in rounds if r["ticker"] != "BANEP"]
            print("\n=== ROUND-TRIP ANALYSIS (price + 0.05% comm/side) ===")
            print(f"  Rounds: {len(rounds)}  W/L: {len(wins)}/{len(losses)}  "
                  f"win rate {100 * len(wins) / len(rounds):.1f}%")
            print(f"  Net PnL: {sum(r['net'] for r in rounds):.2f} rub")
            print(f"  Gross: {sum(r['gross'] for r in rounds):.2f}  "
                  f"Commission est: {sum(r['comm'] for r in rounds):.2f}")
            print(f"  Avg hold: {sum(r['hold_sec'] for r in rounds) / len(rounds):.1f}s")
            if losses:
                print(f"  Avg net on loss: {sum(r['net'] for r in losses) / len(losses):.2f} rub")
                print(f"  Avg price move on loss: "
                      f"{sum(r['move_pct'] for r in losses) / len(losses):.4f}%")

            by_kind: dict[str, dict] = defaultdict(lambda: {"n": 0, "net": 0.0})
            for r in rounds:
                by_kind[r["kind"]]["n"] += 1
                by_kind[r["kind"]]["net"] += r["net"]
            print("\n=== NET PnL BY EXIT KIND ===")
            for k, v in sorted(by_kind.items(), key=lambda x: x[1]["net"]):
                print(f"  {k}: n={v['n']} net={v['net']:.2f}")

            print("\n=== SAMPLE LOSSES ===")
            for r in sorted(losses, key=lambda x: x["net"])[:10]:
                print(
                    f"  {r['ticker']} {r['kind']} {r['entry_px']:.2f}->{r['exit_px']:.2f} "
                    f"move={r['move_pct']:.3f}% hold={r['hold_sec']:.1f}s net={r['net']:.2f}"
                )
            if ex_banep:
                print(f"\n  Excluding BANEP: net={sum(r['net'] for r in ex_banep):.2f} rub, "
                      f"rounds={len(ex_banep)}")

        # Equity curve from cycles
        eq_rows = db.execute(
            text(f"""
                SELECT cycle_number, equity, status, skip_reason, triggered_by, started_at
                FROM {schema}.robots_v2_cycles
                WHERE robot_id = :rid AND equity IS NOT NULL
                ORDER BY started_at
            """),
            {"rid": ROBOT_ID},
        ).fetchall()
        if eq_rows:
            eq_vals = [float(r.equity) for r in eq_rows]
            print("\n=== EQUITY FROM CYCLES ===")
            print(f"  First: {eq_vals[0]:.2f}  Last: {eq_vals[-1]:.2f}  "
                  f"Min: {min(eq_vals):.2f}  Max: {max(eq_vals):.2f}")
            print(f"  Delta last-first: {eq_vals[-1] - eq_vals[0]:.2f}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
