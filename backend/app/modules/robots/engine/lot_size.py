"""MOEX share lot size. T-Invest PostOrder quantity is lots, the ledger is shares."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def normalize_lot_size(raw: object) -> int:
    try:
        size = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return size if size > 0 else 1


def shares_to_lots(shares: int, lot_size: int) -> int:
    """Whole lots that fit into ``shares``. Remainder is not sent."""
    lot = normalize_lot_size(lot_size)
    qty = int(shares or 0)
    if qty <= 0:
        return 0
    return qty // lot


def lots_to_shares(lots: int, lot_size: int) -> int:
    lot = normalize_lot_size(lot_size)
    qty = int(lots or 0)
    if qty <= 0:
        return 0
    return qty * lot


def load_share_lot_sizes(
    db: Session,
    tickers: list[str],
    *,
    schema: str = "public",
) -> dict[str, int]:
    """Latest MOEX lot size per ticker from the market snapshot table."""
    wanted = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        wanted.append(ticker)
    if not wanted:
        return {}

    placeholders = ", ".join(f":t{i}" for i in range(len(wanted)))
    params = {f"t{i}": ticker for i, ticker in enumerate(wanted)}
    rows = db.execute(
        text(f"""
            SELECT ticker, lot_size
            FROM (
                SELECT UPPER(ticker) AS ticker,
                       lot_size,
                       row_number() OVER (
                           PARTITION BY UPPER(ticker) ORDER BY id DESC
                       ) AS rn
                FROM {schema}.market_snapshot_data
                WHERE UPPER(ticker) IN ({placeholders})
                  AND lot_size IS NOT NULL
                  AND lot_size > 0
            ) latest
            WHERE rn = 1
        """),
        params,
    ).fetchall()
    out: dict[str, int] = {}
    for row in rows:
        ticker = str(row[0] or "").upper()
        if ticker:
            out[ticker] = normalize_lot_size(row[1])
    return out
