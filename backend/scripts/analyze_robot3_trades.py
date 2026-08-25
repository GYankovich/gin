"""Full trade analysis for robot #3."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots_v2.audit_pnl import build_round_trips, enrich_fills_realized_pnl

ROBOT_ID = 3


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"SELECT name, config FROM {schema}.robots_v2 WHERE id=:id"),
            {"id": ROBOT_ID},
        ).fetchone()
        if not row:
            print("Robot not found")
            return
        cfg = row.config or {}
        risk = cfg.get("risk") or {}
        strat = cfg.get("strategy") or {}
        comm_pct = float(risk.get("brokerCommissionPct") or 0.05)
        comm_rate = comm_pct / 100.0
        print("=== ROBOT 3 ===", row.name)
        print("mode:", (cfg.get("core") or {}).get("mode"))
        print("archetype:", strat.get("archetype"))
        print("params:", strat.get("params"))
        print("commission:", comm_pct, "%")

        fills_raw = db.execute(
            text(
                f"""
                SELECT f.id, f.ticker, f.side, f.quantity, f.price, f.pnl, f.commission,
                       f.kind, f.filled_at, f.order_id,
                       o.kind AS order_kind, o.order_type, o.status AS order_status, o.price AS order_price
                FROM {schema}.robots_v2_fills f
                LEFT JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
                WHERE f.robot_id = :rid
                ORDER BY f.filled_at ASC
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        orders_raw = db.execute(
            text(
                f"""
                SELECT id, ticker, side, kind, quantity, price, status, order_type, submitted_at
                FROM {schema}.robots_v2_orders
                WHERE robot_id = :rid
                ORDER BY submitted_at ASC
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        orders_by_id = {
            str(o.id): {
                "id": str(o.id),
                "ticker": o.ticker,
                "side": o.side,
                "kind": o.kind,
                "quantity": float(o.quantity),
                "price": float(o.price) if o.price is not None else None,
                "status": o.status,
                "orderType": o.order_type,
            }
            for o in orders_raw
        }
        print(f"\n=== FILLS: {len(fills_raw)} ===")
        if not fills_raw:
            return

        fills: list[dict] = []
        for f in fills_raw:
            fills.append(
                {
                    "id": str(f.id),
                    "ticker": f.ticker,
                    "side": f.side,
                    "quantity": float(f.quantity),
                    "price": float(f.price),
                    "pnl": float(f.pnl or 0),
                    "commission": float(f.commission or 0),
                    "kind": f.kind,
                    "filledAt": f.filled_at.isoformat() if f.filled_at else None,
                    "orderId": str(f.order_id) if f.order_id else None,
                    "reason": f.order_kind,
                }
            )

        enrich_fills_realized_pnl(fills, commission_rate=comm_rate)
        trips = build_round_trips(fills, orders_by_id, commission_rate=comm_rate)
        print(f"\n=== ROUND TRIPS: {len(trips)} ===")
        net_total = 0.0
        real_total = 0.0
        gross_total = 0.0
        wins = losses = 0
        for t in trips:
            net = float(t.get("netPnl") or t.get("net_pnl") or 0)
            real = float(t.get("realizedPnl") or t.get("realized_pnl") or 0)
            buy_px = t.get("buyPrice") or t.get("buy_price")
            sell_px = t.get("sellFillPrice") or t.get("sell_fill_price") or t.get("sellListedPrice")
            buy_at = str(t.get("buyAt") or t.get("buy_at") or "")[11:19]
            sell_at = str(t.get("sellAt") or t.get("sell_at") or "")[11:19]
            net_total += net
            real_total += real
            gross = (float(sell_px or 0) - float(buy_px or 0)) * float(t.get("buyQty") or t.get("buy_qty") or 0)
            if t.get("status") == "closed":
                gross_total += gross
                if net >= 0:
                    wins += 1
                else:
                    losses += 1
            print(
                f"  {t.get('ticker'):6} {str(t.get('status')):8} "
                f"BUY {buy_px} ({buy_at}) -> SELL {sell_px} ({sell_at or '-'}) "
                f"reason={t.get('reason')} gross~{gross:.2f} net={net:.2f}"
            )
        print(f"\nClosed W/L: {wins}/{losses}")
        print(f"SUM net (pocket): {net_total:.2f} RUB")
        print(f"SUM realized (after comm): {real_total:.2f} RUB")

        print("\n=== ALL FILLS (chronological) ===")
        for f in fills_raw:
            ts = f.filled_at.strftime("%Y-%m-%d %H:%M:%S") if f.filled_at else "?"
            print(
                f"  {ts} {str(f.ticker):6} {str(f.side):4} qty={float(f.quantity):6.0f} "
                f"px={float(f.price):9.4f} kind={str(f.kind):16} "
                f"ledger_pnl={float(f.pnl or 0):8.2f} comm={float(f.commission or 0):6.2f} "
                f"reason={f.order_kind}"
            )

        by_kind: dict[str, float] = defaultdict(float)
        for f in fills_raw:
            by_kind[str(f.kind)] += float(f.pnl or 0)
        print("\n=== LEDGER PNL BY KIND ===")
        for k, v in sorted(by_kind.items(), key=lambda x: x[1]):
            print(f"  {k}: {v:.2f}")

        by_ticker_net: dict[str, float] = defaultdict(float)
        for t in trips:
            if str(t.get("status")).lower() == "closed":
                tk = str(t.get("ticker")).upper()
                by_ticker_net[tk] += float(t.get("netPnl") or t.get("net_pnl") or 0)
        print("\n=== NET PNL BY TICKER (closed trips) ===")
        for tk, v in sorted(by_ticker_net.items(), key=lambda x: x[1]):
            print(f"  {tk}: {v:.2f}")

        by_reason: dict[str, float] = defaultdict(float)
        for t in trips:
            if str(t.get("status")).lower() == "closed":
                by_reason[str(t.get("reason") or "?")] += float(t.get("netPnl") or t.get("net_pnl") or 0)
        print("\n=== NET PNL BY EXIT REASON ===")
        for k, v in sorted(by_reason.items(), key=lambda x: x[1]):
            print(f"  {k}: {v:.2f}")

        # open lots
        pos: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for f in fills_raw:
            t = str(f.ticker).upper()
            q = float(f.quantity)
            p = float(f.price)
            side = str(f.side).upper()
            if side == "BUY":
                pos[t].append((q, p))
            elif side == "SELL":
                rem = q
                while rem > 0 and pos[t]:
                    lq, lp = pos[t][0]
                    take = min(rem, lq)
                    rem -= take
                    if lq - take <= 1e-9:
                        pos[t].pop(0)
                    else:
                        pos[t][0] = (lq - take, lp)
        open_pos = {k: v for k, v in pos.items() if v}
        print("\n=== OPEN LOTS ===", open_pos)

        sessions = db.execute(
            text(
                f"""
                SELECT id, started_at, ended_at, stop_reason
                FROM {schema}.robots_v2_sessions
                WHERE robot_id = :rid ORDER BY started_at ASC
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        print(f"\n=== SESSIONS: {len(sessions)} ===")
        for s in sessions:
            print(f"  {s.id} start={s.started_at} end={s.ended_at} stop={s.stop_reason}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
