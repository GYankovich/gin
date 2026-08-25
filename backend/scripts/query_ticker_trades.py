"""Query audit trail for specific tickers."""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

ROBOT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
TICKERS = [t.upper() for t in sys.argv[2:]] or ["SMLT", "X5"]


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        print(f"=== FILLS robot={ROBOT_ID} tickers={TICKERS} ===")
        fills = db.execute(
            text(
                f"""
                SELECT f.filled_at, f.ticker, f.side, f.quantity, f.price, f.pnl, f.kind,
                       o.order_type, o.status, o.broker_order_id, o.submitted_at AS order_at
                FROM {schema}.robots_v2_fills f
                LEFT JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
                WHERE f.robot_id = :rid AND f.ticker = ANY(:tickers)
                ORDER BY f.filled_at DESC
                LIMIT 40
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS},
        ).fetchall()
        for f in fills:
            print(
                f"  {f.filled_at} {f.ticker} {f.side} qty={f.quantity} px={float(f.price):.4f} "
                f"kind={f.kind} pnl={float(f.pnl or 0):.2f} "
                f"type={f.order_type} order_at={f.order_at}"
            )

        print("\n=== SIGNALS ===")
        sigs = db.execute(
            text(
                f"""
                SELECT s.created_at, s.ticker, s.side, s.kind, s.reason, s.price
                FROM {schema}.robots_v2_signals s
                WHERE s.robot_id = :rid AND s.ticker = ANY(:tickers)
                ORDER BY s.created_at DESC LIMIT 30
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS},
        ).fetchall()
        for s in sigs:
            print(
                f"  {s.created_at} {s.ticker} {s.side} kind={s.kind} reason={s.reason} px={s.price}"
            )

        print("\n=== ORDERS (resting + recent) ===")
        orders = db.execute(
            text(
                f"""
                SELECT o.submitted_at, o.ticker, o.side, o.quantity, o.price,
                       o.status, o.kind, o.order_type, o.broker_order_id, o.reject_reason
                FROM {schema}.robots_v2_orders o
                WHERE o.robot_id = :rid AND o.ticker = ANY(:tickers)
                ORDER BY o.submitted_at DESC LIMIT 30
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS},
        ).fetchall()
        for o in orders:
            print(
                f"  {o.submitted_at} {o.ticker} {o.side} qty={o.quantity} px={float(o.price or 0):.4f} "
                f"status={o.status} kind={o.kind} type={o.order_type} "
                f"broker={o.broker_order_id} reject={o.reject_reason}"
            )

        print("\n=== DECISIONS (strategy scan) ===")
        decs = db.execute(
            text(
                f"""
                SELECT d.created_at, d.ticker, d.code, d.outcome, d.message, d.context, d.stage
                FROM {schema}.robots_v2_decisions d
                WHERE d.robot_id = :rid AND d.ticker = ANY(:tickers)
                ORDER BY d.created_at DESC LIMIT 40
                """
            ),
            {"rid": ROBOT_ID, "tickers": TICKERS},
        ).fetchall()
        for d in decs:
            msg = (d.message or "")[:100]
            ctx = d.context if isinstance(d.context, dict) else {}
            print(f"  {d.created_at} [{d.stage}] {d.ticker} {d.code}/{d.outcome} {msg} {json.dumps(ctx, default=str)[:120]}")

        print("\n=== SESSIONS ===")
        sess = db.execute(
            text(
                f"""
                SELECT id, started_at, ended_at, stop_reason
                FROM {schema}.robots_v2_sessions
                WHERE robot_id = :rid ORDER BY started_at DESC LIMIT 5
                """
            ),
            {"rid": ROBOT_ID},
        ).fetchall()
        for s in sess:
            print(f"  {s.id} start={s.started_at} end={s.ended_at} stop={s.stop_reason}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
