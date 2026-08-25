"""Helpers for per-ticker strategy scan snapshots."""

from __future__ import annotations

from typing import Any


def build_session_skip_scan(
    universe: list[str],
    prices: dict[str, float],
    *,
    code: str,
    message: str,
    candle_history: dict[str, list[Any]] | None = None,
) -> list[dict[str, Any]]:
    """Uniform scan rows when strategy was not evaluated (schedule/EOD/etc.)."""
    out: list[dict[str, Any]] = []
    hist = candle_history or {}
    for raw in universe:
        t = str(raw).upper()
        px = prices.get(t)
        row: dict[str, Any] = {
            "ticker": t,
            "code": code,
            "message": message,
            "metrics": {"bars": len(hist.get(t) or [])},
        }
        if px is not None and px > 0:
            row["price"] = round(float(px), 4)
        out.append(row)
    return out
