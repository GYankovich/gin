"""ByBit mainnet live smoke (read-only, no orders)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.modules.bybit.http_client import BybitHttpClient
from app.modules.robots.trading.brokers.factory import create_broker_facade


def _position_view(position: Dict[str, Any]) -> Dict[str, Any]:
    qty = position.get("quantity")
    if isinstance(qty, dict):
        qty_val = qty.get("decimal")
    else:
        qty_val = qty
    return {
        "figi": position.get("figi"),
        "type": position.get("instrument_type"),
        "qty": qty_val,
        "side": position.get("side"),
    }


async def run_bybit_public_smoke(*, symbol: str = "BTCUSDT") -> Dict[str, Any]:
    client = BybitHttpClient()
    try:
        await client.get_server_time()
        data = await client.get_kline(category="linear", symbol=symbol.upper(), interval="60", limit=3)
        rows = list((data.get("result") or {}).get("list") or [])
        return {
            "ok": True,
            "mainnet": True,
            "symbol": symbol.upper(),
            "kline_rows": len(rows),
            "last_close": float(rows[0][4]) if rows else None,
        }
    finally:
        await client.close()


async def run_bybit_live_smoke(
    api_key: str,
    token_extra_data: Optional[Dict[str, Any]] = None,
    *,
    symbol: str = "BTCUSDT",
    instrument_category: str = "linear",
) -> Dict[str, Any]:
    """
    Private mainnet smoke via ByBitBrokerFacade (wallet + positions + candles).
    Does not place orders. Leverage is not modified (1x policy).
    """
    config = {
        "broker_type": "bybit",
        "bybit": {"instrument_category": instrument_category, "leverage": 1},
    }
    broker = create_broker_facade(
        "bybit",
        api_key,
        token_extra_data=token_extra_data,
        robot_config=config,
    )
    out: Dict[str, Any] = {
        "ok": False,
        "mainnet": True,
        "leverage": 1,
        "symbol": symbol.upper(),
        "instrument_category": instrument_category,
    }

    try:
        await broker._http.query_api()
        out["query_api"] = "ok"

        accounts = await broker.get_accounts()
        out["accounts_count"] = len(accounts)
        unified = next(
            (a for a in accounts if str(a.get("type") or "").upper() == "UNIFIED"),
            accounts[0] if accounts else {"id": broker.make_account_id("UNIFIED")},
        )
        account_id = str(unified.get("id"))
        out["account_id"] = account_id

        portfolio = await broker.get_portfolio(account_id)
        out["total_equity"] = (portfolio.get("total_amount_portfolio") or {}).get("decimal")
        out["free_funds"] = portfolio.get("free_funds")
        positions: List[Dict[str, Any]] = list(portfolio.get("positions") or [])
        out["positions_count"] = len(positions)
        out["positions"] = [_position_view(p) for p in positions]

        out["free_funds_check"] = await broker.get_free_funds(account_id)

        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(hours=6)
        candles = await broker.get_candles(symbol.upper(), from_dt, to_dt, "1h")
        out["candles_6h"] = len(candles)

        out["ok"] = True
        return out
    finally:
        await broker.close()


__all__ = ["run_bybit_live_smoke", "run_bybit_public_smoke"]
