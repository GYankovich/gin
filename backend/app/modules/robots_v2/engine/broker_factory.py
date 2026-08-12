"""Create broker facade + resolve account for robots v2 live mode."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots_v2.universe.token_context import TokenContext

logger = logging.getLogger(__name__)


def create_broker_from_token(
    ctx: TokenContext,
    *,
    instrument_type: str = "stock",
    robot_config: dict[str, Any] | None = None,
) -> BrokerFacade | None:
    if not ctx.api_key:
        return None
    if ctx.broker == "bybit":
        from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade

        category = "inverse" if instrument_type == "coin_futures" else "linear"
        return ByBitBrokerFacade(
            ctx.api_key,
            testnet=ctx.testnet,
            api_secret=ctx.api_secret,
            instrument_category=category,
            user_id=ctx.user_id,
            token_id=ctx.token_id,
            context_type="robot_v2",
            context_ref=str(ctx.token_id),
        )
    return create_broker_facade(
        ctx.broker,
        ctx.api_key,
        api_secret=ctx.api_secret,
        token_extra_data={"testnet": ctx.testnet, "api_secret": ctx.api_secret},
        robot_config=robot_config,
        user_id=ctx.user_id,
        token_id=ctx.token_id,
        context_type="robot_v2",
    )


async def resolve_account_id(broker: BrokerFacade, preferred: str | None = None) -> str | None:
    if preferred:
        return preferred
    try:
        accounts = await broker.get_accounts()
    except Exception:
        logger.exception("get_accounts failed broker=%s", getattr(broker, "broker_type", "?"))
        return None
    if not accounts:
        return None
    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        for key in ("id", "account_id", "accountId"):
            val = acc.get(key)
            if val:
                return str(val)
    return None


async def resolve_ticker_instrument_map(
    ctx: TokenContext,
    tickers: list[str],
) -> dict[str, str]:
    """ticker → broker instrument id (FIGI for T-Invest, symbol for Bybit)."""
    out: dict[str, str] = {}
    if ctx.broker == "bybit":
        for tk in tickers:
            t = str(tk or "").strip().upper()
            if t:
                out[t] = t
        return out
    if ctx.broker != "tinvest" or not ctx.api_key:
        for tk in tickers:
            t = str(tk or "").strip().upper()
            if t:
                out[t] = t
        return out
    from app.modules.market_data.service import resolve_figi_and_ticker

    for tk in tickers:
        t = str(tk or "").strip().upper()
        if not t:
            continue
        try:
            figi, _, _ = await resolve_figi_and_ticker("", t, "tinvest", ctx.api_key)
            out[t] = str(figi or t).upper()
        except Exception:
            logger.warning("figi resolve failed ticker=%s token_id=%s", t, ctx.token_id)
            out[t] = t
    return out
