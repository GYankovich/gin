"""Analyze SMLT pocket (netPnl) display."""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots_v2.audit_pnl import enrich_fills_realized_pnl


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT f.id, f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind
                FROM public.robots_v2_fills f
                WHERE f.robot_id = 1 AND f.ticker = 'SMLT'
                ORDER BY f.filled_at ASC
                """
            ),
        ).fetchall()
        timeline = [
            {
                "id": str(r.id),
                "ticker": r.ticker,
                "side": r.side,
                "quantity": float(r.quantity),
                "price": float(r.price),
                "filledAt": str(r.filled_at),
                "pnl": float(r.pnl or 0),
                "kind": r.kind,
            }
            for r in rows
        ]
        kinds = {t["id"]: t["kind"] for t in timeline}
        sells = [t for t in timeline if str(t["side"]).upper() == "SELL"]
        out_all = enrich_fills_realized_pnl(
            sells,
            commission_rate=0.0005,
            tax_rate=0.13,
            all_fills_chronological=timeline,
        )
        total_net = sum(float(x["netPnl"] or 0) for x in out_all if x.get("netPnl") is not None)
        print(f"SMLT sells: {len(sells)} total netPnl={total_net:.2f}")
        print("\n=== LAST 12 SMLT SELLS ===")
        for o in out_all[-12:]:
            print(
                f"  {o['filledAt'][:19]} kind={kinds.get(o['id'])} "
                f"entry={o.get('entryPrice')} px={o['price']} "
                f"ledger={o.get('ledgerPnl')} real={o.get('realizedPnl')} net={o.get('netPnl')}"
            )

        # Find row near -62.82
        print("\n=== ROWS with net near -62 ===")
        for o in out_all:
            net = float(o.get("netPnl") or 0)
            if abs(net + 62.82) < 1 or abs(net + 60) < 5:
                print(f"  MATCH? {o['filledAt'][:19]} net={net} entry={o.get('entryPrice')} px={o['price']}")

        # Simulate paginated audit like UI (limit 50, desc)
        page_rows = db.execute(
            text(
                """
                SELECT f.id, f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind
                FROM public.robots_v2_fills f
                WHERE f.robot_id = 1
                ORDER BY f.filled_at DESC
                LIMIT 50
                """
            ),
        ).fetchall()
        page = [
            {
                "id": str(r.id),
                "ticker": r.ticker,
                "side": r.side,
                "quantity": float(r.quantity),
                "price": float(r.price),
                "filledAt": str(r.filled_at),
                "pnl": float(r.pnl or 0),
            }
            for r in page_rows
        ]
        full = db.execute(
            text(
                """
                SELECT f.id, f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl
                FROM public.robots_v2_fills f
                WHERE f.robot_id = 1
                ORDER BY f.filled_at ASC
                """
            ),
        ).fetchall()
        full_tl = [
            {
                "id": str(r.id),
                "ticker": r.ticker,
                "side": r.side,
                "quantity": float(r.quantity),
                "price": float(r.price),
                "filledAt": str(r.filled_at),
            }
            for r in full
        ]
        page_enriched = enrich_fills_realized_pnl(
            page, commission_rate=0.0005, tax_rate=0.13, all_fills_chronological=full_tl,
        )
        smlt_page = [x for x in page_enriched if str(x.get("ticker")).upper() == "SMLT" and str(x.get("side")).upper() == "SELL"]
        print(f"\n=== SMLT in UI page (last 50 fills) ===")
        for o in smlt_page[:8]:
            print(f"  {o['filledAt'][:19]} net={o.get('netPnl')} entry={o.get('entryPrice')} px={o['price']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
