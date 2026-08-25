"""Create broker facade + resolve account for robots v2 live mode."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots_v2.universe.token_context import TokenContext

logger = logging.getLogger(__name__)


def create_broker_from_token(
    ctx: TokenContext,
    *,
    instrument_type: str = "stock",
    robot_config: dict[str, Any] | None = None,
    robot_id: int | None = None,
) -> BrokerFacade | None:
    if not ctx.api_key:
        return None
    context_ref = str(robot_id) if robot_id is not None else str(ctx.token_id)
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
            context_type="trading",
            context_ref=context_ref,
        )
    return create_broker_facade(
        ctx.broker,
        ctx.api_key,
        api_secret=ctx.api_secret,
        token_extra_data={"testnet": ctx.testnet, "api_secret": ctx.api_secret},
        robot_config=robot_config,
        user_id=ctx.user_id,
        token_id=ctx.token_id,
        context_type="trading",
        context_ref=context_ref,
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


def persist_token_account_id(
    *,
    user_id: int,
    token_id: int,
    account_id: str | None,
    schema: str | None = None,
) -> None:
    """Cache resolved broker account on api_tokens for live sessions."""
    if not account_id:
        return
    from app.core.config import settings

    sch = schema or getattr(settings, "DB_SCHEMA", None) or "public"
    db = SessionLocal()
    try:
        db.execute(
            text(f"""
                UPDATE {sch}.api_tokens
                SET account_id = :account_id,
                    last_error = NULL,
                    last_error_at = NULL,
                    updated_at = NOW()
                WHERE id = :token_id AND user_id = :user_id
            """),
            {
                "account_id": str(account_id),
                "token_id": token_id,
                "user_id": user_id,
            },
        )
        db.commit()
    except Exception:
        logger.exception("persist_token_account_id failed token_id=%s", token_id)
        db.rollback()
    finally:
        db.close()


def load_token_account_id(token_id: int, user_id: int, *, schema: str | None = None) -> str | None:
    from app.core.config import settings

    sch = schema or getattr(settings, "DB_SCHEMA", None) or "public"
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"""
                SELECT account_id FROM {sch}.api_tokens
                WHERE id = :token_id AND user_id = :user_id
            """),
            {"token_id": token_id, "user_id": user_id},
        ).fetchone()
        if row and row[0]:
            return str(row[0])
        return None
    finally:
        db.close()


def _looks_like_figi(value: str) -> bool:
    v = (value or "").strip().upper()
    return len(v) >= 8 and (v.startswith("BBG") or v.startswith("TCS"))


def _figi_map_from_db(tickers: list[str]) -> dict[str, str]:
    """Lookup ticker → FIGI from market_instruments (no API)."""
    wanted = [str(t).strip().upper() for t in tickers if str(t or "").strip()]
    if not wanted:
        return {}
    from app.core.config import settings

    schema = getattr(settings, "DB_SCHEMA", None) or "public"
    placeholders = ", ".join(f":t{i}" for i in range(len(wanted)))
    params = {f"t{i}": t for i, t in enumerate(wanted)}
    db = SessionLocal()
    try:
        rows = db.execute(
            text(f"""
                SELECT UPPER(ticker) AS ticker, UPPER(figi) AS figi
                FROM {schema}.market_instruments
                WHERE UPPER(ticker) IN ({placeholders})
                  AND figi IS NOT NULL
                  AND figi <> ''
            """),
            params,
        ).fetchall()
        out: dict[str, str] = {}
        for row in rows:
            tk = str(row[0] or "").upper()
            fg = str(row[1] or "").upper()
            if tk and _looks_like_figi(fg):
                out[tk] = fg
        return out
    except Exception:
        logger.warning("market_instruments FIGI lookup failed", exc_info=True)
        return {}
    finally:
        db.close()


def _index_instruments_by_ticker(items: list[dict[str, Any]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in items or []:
        if not isinstance(row, dict):
            continue
        tk = str(row.get("ticker") or "").strip().upper()
        fg = str(row.get("figi") or "").strip().upper()
        if tk and _looks_like_figi(fg):
            out[tk] = fg
    return out


async def resolve_ticker_instrument_map(
    ctx: TokenContext,
    tickers: list[str],
    *,
    robot_id: int | None = None,
) -> dict[str, str]:
    """ticker → broker instrument id (FIGI for T-Invest, symbol for Bybit).

    Uses DB cache + a single Shares/ETFs catalog fetch (not per-ticker Shares calls).
    """
    out: dict[str, str] = {}
    clean = [str(tk or "").strip().upper() for tk in tickers if str(tk or "").strip()]
    if ctx.broker == "bybit":
        for t in clean:
            out[t] = t
        return out
    if ctx.broker != "tinvest" or not ctx.api_key:
        for t in clean:
            out[t] = t
        return out

    from app.modules.robots_v2.engine.session_log import log_external_api
    from app.modules.tinvest.methods.instruments import InstrumentsClient

    db_map = _figi_map_from_db(clean)
    for t in clean:
        if t in db_map:
            out[t] = db_map[t]

    missing = [t for t in clean if t not in out]
    if not missing:
        return out

    client = InstrumentsClient(ctx.api_key)
    catalog: dict[str, str] = {}
    started = datetime.now(timezone.utc)
    try:
        shares = await client.get_shares()
        catalog.update(_index_instruments_by_ticker(shares))
        still = [t for t in missing if t not in catalog]
        if still:
            etfs = await client.get_etfs()
            catalog.update(_index_instruments_by_ticker(etfs))
        if robot_id is not None:
            await log_external_api(
                robot_id=robot_id,
                user_id=ctx.user_id,
                token_id=ctx.token_id,
                endpoint="tinvest.InstrumentsService/Shares+EtfsBulk",
                request_data={"tickers": missing[:20], "n": len(missing)},
                response_data={
                    "catalogSize": len(catalog),
                    "matched": sum(1 for t in missing if t in catalog),
                },
                response_status=200,
                started_at=started,
            )
    except Exception as exc:
        logger.warning("bulk figi catalog failed token_id=%s: %s", ctx.token_id, exc)
        if robot_id is not None:
            await log_external_api(
                robot_id=robot_id,
                user_id=ctx.user_id,
                token_id=ctx.token_id,
                endpoint="tinvest.InstrumentsService/Shares+EtfsBulk",
                request_data={"tickers": missing[:20]},
                error_message=str(exc)[:500],
                started_at=started,
            )

    for t in missing:
        if t in catalog:
            out[t] = catalog[t]
        else:
            out[t] = t
            logger.warning("figi unresolved ticker=%s token_id=%s", t, ctx.token_id)

    return out
