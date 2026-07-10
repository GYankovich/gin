"""ByBit read-only market data service for HTTP API."""

from __future__ import annotations

from typing import Any, Dict, Literal

from sqlalchemy.orm import Session

from app.modules.bybit.funding import fetch_funding_rate
from app.modules.bybit.http_client import BybitApiError, BybitHttpClient
from app.modules.bybit.instruments import list_instruments
from app.modules.bybit.schemas import (
    BybitFundingRateResponse,
    BybitInstrumentItem,
    BybitInstrumentsResponse,
    BybitUniverseScreeningPreviewRequest,
    BybitUniverseScreeningPreviewResponse,
)


class BybitMarketService:
    async def get_funding_rate(
        self,
        *,
        symbol: str,
        instrument_category: Literal["spot", "linear", "inverse"] = "linear",
        testnet: bool = True,
    ) -> BybitFundingRateResponse:
        return await fetch_funding_rate(
            symbol=symbol,
            instrument_category=instrument_category,
            testnet=testnet,
        )

    async def get_instruments(
        self,
        *,
        category: Literal["spot", "linear", "inverse"] = "linear",
        quote_coin: str | None = None,
        testnet: bool = True,
    ) -> BybitInstrumentsResponse:
        rows = await list_instruments(
            category=category,
            quote_coin=quote_coin,
            testnet=testnet,
        )
        items = [BybitInstrumentItem.model_validate(r) for r in rows]
        return BybitInstrumentsResponse(
            items=items,
            total=len(items),
            category=category,
            testnet=testnet,
        )

    async def preview_universe_screening(
        self,
        db: Session,
        user_id: int,
        body: BybitUniverseScreeningPreviewRequest,
    ) -> BybitUniverseScreeningPreviewResponse:
        from app.modules.robots.crypto_universe import (
            _find_active_bybit_token,
            _resolve_filters,
            fetch_bybit_tickers,
            screen_bybit_universe_live,
        )

        token_row = _find_active_bybit_token(db, user_id)
        if not token_row:
            return BybitUniverseScreeningPreviewResponse(
                accepted=0,
                scanned=0,
                message="Активный ByBit API token не найден",
                skipped=True,
            )

        cu: Dict[str, Any] = {
            "min_volume_24h_usd": float(body.min_volume_24h_usd),
            "max_spread_bps": float(body.max_spread_bps),
            "category": body.instrument_category,
            "lookback_days": int(body.lookback_days),
        }
        if body.min_funding_rate_pct is not None:
            cu["min_funding_rate"] = float(body.min_funding_rate_pct) / 100.0
        if body.max_funding_rate_pct is not None:
            cu["max_funding_rate"] = float(body.max_funding_rate_pct) / 100.0
        if body.min_open_interest_usd is not None:
            cu["min_open_interest_usd"] = float(body.min_open_interest_usd)
        if body.min_lsr is not None:
            cu["min_lsr"] = float(body.min_lsr)
        if body.max_lsr is not None:
            cu["max_lsr"] = float(body.max_lsr)
        if body.min_rvol is not None:
            cu["min_rvol"] = float(body.min_rvol)
        if body.min_atr_percent is not None:
            cu["min_atr_percent"] = float(body.min_atr_percent)
        if body.max_atr_percent is not None:
            cu["max_atr_percent"] = float(body.max_atr_percent)

        config = {
            "crypto_universe": cu,
            "bybit": {
                "instrument_category": body.instrument_category,
                "testnet": body.testnet,
            },
        }
        filters = _resolve_filters(config)
        api_key = token_row["token"]
        api_secret = token_row["token_secret"]
        testnet = bool(token_row.get("testnet", body.testnet))

        tickers = await fetch_bybit_tickers(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            category=filters.category,
        )
        client = BybitHttpClient(testnet=testnet, api_key=api_key, api_secret=api_secret)
        try:
            accepted_rows, _rejected = await screen_bybit_universe_live(
                tickers,
                client=client,
                filters=filters,
                db=db,
            )
        finally:
            await client.close()

        return BybitUniverseScreeningPreviewResponse(
            accepted=len(accepted_rows),
            scanned=len(tickers),
            skipped=False,
        )


bybit_market_service = BybitMarketService()

__all__ = ["BybitMarketService", "bybit_market_service", "BybitApiError"]
