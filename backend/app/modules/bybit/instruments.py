"""ByBit instruments-info listing for UI autocomplete."""

from __future__ import annotations

from typing import Any, Literal

from app.modules.bybit.http_client import BybitHttpClient


async def list_instruments(
    *,
    category: Literal["spot", "linear", "inverse"] = "linear",
    quote_coin: str | None = None,
    testnet: bool = True,
    limit: int = 200,
    max_pages: int = 10,
    user_id: int | None = None,
    context_type: str | None = None,
    context_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch tradable symbols from ByBit public API (paginated)."""
    client = BybitHttpClient(
        testnet=testnet,
        user_id=user_id,
        context_type=context_type,
        context_ref=context_ref,
    )
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        payload = await client.get_instruments_info(
            category=category,
            limit=limit,
            cursor=cursor,
        )
        result = payload.get("result") or {}
        for item in result.get("list") or []:
            if str(item.get("status") or "").lower() not in {"trading", "trade"}:
                continue
            symbol = str(item.get("symbol") or "").strip()
            if not symbol:
                continue
            qc = str(item.get("quoteCoin") or "").strip()
            if quote_coin and qc.upper() != quote_coin.strip().upper():
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "base_coin": str(item.get("baseCoin") or ""),
                    "quote_coin": qc,
                    "status": item.get("status"),
                    "category": category,
                    "contract_type": str(item.get("contractType") or "").strip(),
                }
            )
        cursor = result.get("nextPageCursor") or None
        if not cursor:
            break
    rows.sort(key=lambda r: r["symbol"])
    return rows


__all__ = ["list_instruments"]
