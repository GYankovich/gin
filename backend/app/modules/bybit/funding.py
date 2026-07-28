"""In-memory cache for ByBit funding rate (read-only UI / risk hints)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.modules.bybit.http_client import BybitApiError, BybitHttpClient
from app.modules.bybit.schemas import BybitFundingRateResponse

# Funding settles every ~8h; cache long enough to avoid hammering public API.
FUNDING_RATE_CACHE_TTL_SECONDS = 8 * 3600

_CacheKey = Tuple[str, str, bool]


@dataclass
class _CacheEntry:
    expires_at: float
    payload: BybitFundingRateResponse


_cache: Dict[_CacheKey, _CacheEntry] = {}


def _cache_get(key: _CacheKey) -> Optional[BybitFundingRateResponse]:
    entry = _cache.get(key)
    if not entry:
        return None
    if time.monotonic() >= entry.expires_at:
        _cache.pop(key, None)
        return None
    return entry.payload


def _cache_set(key: _CacheKey, payload: BybitFundingRateResponse) -> None:
    _cache[key] = _CacheEntry(
        expires_at=time.monotonic() + FUNDING_RATE_CACHE_TTL_SECONDS,
        payload=payload,
    )


def clear_funding_rate_cache() -> None:
    _cache.clear()


def _parse_next_funding_time(raw: object) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


async def fetch_funding_rate(
    *,
    symbol: str,
    instrument_category: str = "linear",
    testnet: bool = True,
    client: Optional[BybitHttpClient] = None,
) -> BybitFundingRateResponse:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    category = str(instrument_category or "linear").strip().lower()
    if category not in {"spot", "linear", "inverse"}:
        raise ValueError(f"unsupported instrument_category: {category}")

    cache_key: _CacheKey = (sym, category, bool(testnet))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if category == "spot":
        payload = BybitFundingRateResponse(
            symbol=sym,
            instrument_category="spot",
            funding_rate=0.0,
            next_funding_time=None,
            testnet=bool(testnet),
            source="bybit_tickers",
        )
        _cache_set(cache_key, payload)
        return payload

    own_client = client is None
    http = client or BybitHttpClient(testnet=testnet)
    try:
        data = await http.get_tickers(category=category, symbol=sym)
        rows = list((data.get("result") or {}).get("list") or [])
        row = next((r for r in rows if str(r.get("symbol") or "").upper() == sym), None)
        if not row and rows:
            row = rows[0]
        if not row:
            raise BybitApiError(f"funding rate not found for {sym}")
        payload = BybitFundingRateResponse(
            symbol=sym,
            instrument_category=category,  # type: ignore[arg-type]
            funding_rate=float(row.get("fundingRate") or 0),
            next_funding_time=_parse_next_funding_time(row.get("nextFundingTime")),
            testnet=bool(testnet),
            source="bybit_tickers",
        )
        _cache_set(cache_key, payload)
        return payload
    finally:
        if own_client:
            await http.close()


__all__ = [
    "FUNDING_RATE_CACHE_TTL_SECONDS",
    "clear_funding_rate_cache",
    "fetch_funding_rate",
]
