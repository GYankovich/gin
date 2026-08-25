from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots_v2.audit_pnl import enrich_fills_realized_pnl

db = SessionLocal()
rows = db.execute(
    text(
        """
        SELECT f.id, f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, c.session_id
        FROM public.robots_v2_fills f
        JOIN public.robots_v2_orders o ON o.id = f.order_id
        JOIN public.robots_v2_cycles c ON c.id = o.cycle_id
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
        "sessionId": str(r.session_id),
    }
    for r in rows
]
target = [t for t in timeline if "2026-08-14 12:48:37" in t["filledAt"]][0]
out = enrich_fills_realized_pnl([target], commission_rate=0.0005, tax_rate=0.13, all_fills_chronological=timeline)
print("12:48 SMLT after session-scoped FIFO:")
print(out[0])
db.close()
