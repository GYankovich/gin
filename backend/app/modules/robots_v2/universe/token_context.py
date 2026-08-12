"""Token → market/broker context for Universe Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.robots.trading.brokers.routing import resolve_broker_from_token

Market = Literal["moex", "crypto"]


@dataclass(frozen=True)
class TokenContext:
    token_id: int
    user_id: int
    token_type: int
    broker: str
    market: Market
    api_key: str | None = None
    api_secret: str | None = None
    testnet: bool = True


def _market_for_broker(broker: str, instrument_type: str) -> Market:
    if broker == "bybit":
        return "crypto"
    return "moex"


def load_token_context(
    db: Session,
    *,
    user_id: int,
    token_id: int,
    instrument_type: str = "stock",
    schema: str = "public",
) -> TokenContext:
    row = db.execute(
        text(f"""
            SELECT id, token_type, token, extra_data
            FROM {schema}.api_tokens
            WHERE id = :token_id AND user_id = :user_id AND status IN (1, 3)
        """),
        {"token_id": token_id, "user_id": user_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found")
    token_type = int(row[1])
    broker = resolve_broker_from_token(token_type)
    market = _market_for_broker(broker, instrument_type)
    extra = row[3] if isinstance(row[3], dict) else {}
    secret = str(extra.get("token_secret") or extra.get("api_secret") or "").strip() or None
    return TokenContext(
        token_id=int(row[0]),
        user_id=user_id,
        token_type=token_type,
        broker=broker,
        market=market,
        api_key=str(row[2] or "").strip() or None,
        api_secret=secret,
        testnet=bool(extra.get("testnet", True)),
    )


def board_for_instrument_type(instrument_type: str) -> str:
    if instrument_type == "futures":
        return "RFUD"
    return "TQBR"
