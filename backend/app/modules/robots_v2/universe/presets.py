"""Screener presets → DMS / crypto filter sets (greenfield §5)."""

from __future__ import annotations

from typing import Any, Literal

ScreenerPreset = Literal["high_liquidity", "volatile", "low_price", "custom"]
Market = Literal["moex", "crypto"]

MOEX_STATUS_FILTERS: list[dict[str, Any]] = [
    {"type": "security_status", "eq": "A"},
    {"type": "trading_status", "eq": "T"},
]

MOEX_PRESETS: dict[ScreenerPreset, list[dict[str, Any]]] = {
    "high_liquidity": [
        *MOEX_STATUS_FILTERS,
        {"type": "min_avg_volume", "min": 50_000_000},
        {"type": "volume", "min": 10_000_000},
        {"type": "spread", "max_percent": 0.3},
    ],
    "volatile": [
        *MOEX_STATUS_FILTERS,
        {"type": "atr", "min_percent": 2.0},
    ],
    "low_price": [
        *MOEX_STATUS_FILTERS,
        {"type": "volume", "min": 5_000_000},
    ],
    "custom": [
        *MOEX_STATUS_FILTERS,
        {"type": "volume", "min": 10_000_000},
    ],
}

MOEX_PRICE_POST_FILTERS: dict[ScreenerPreset, tuple[float | None, float | None]] = {
    "high_liquidity": (None, None),
    "volatile": (10.0, None),
    "low_price": (10.0, 500.0),
    "custom": (10.0, None),
}

CRYPTO_PRESETS: dict[ScreenerPreset, dict[str, Any]] = {
    "high_liquidity": {
        "min_volume_24h_usd": 50_000_000,
        "max_spread_pct": 0.1,
    },
    "volatile": {
        "min_volume_24h_usd": 5_000_000,
        "min_atr_percent": 3.0,
    },
    "low_price": {
        "min_volume_24h_usd": 5_000_000,
        "max_last_price": 1.0,
    },
    "custom": {
        "min_volume_24h_usd": 5_000_000,
    },
}

MOEX_INDICES: list[dict[str, str]] = [
    {"code": "IMOEX", "name": "Индекс MOEX"},
    {"code": "RTSI", "name": "Индекс RTS"},
    {"code": "MOEXBC", "name": "Индекс голубых фишек"},
]

CRYPTO_INDICES: list[dict[str, str]] = [
    {"code": "TOP_BYBIT", "name": "Top-10 Bybit по объёму (USDT linear)"},
]


def resolve_moex_dms_filters(
    *,
    preset: ScreenerPreset | None,
    custom_filters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if custom_filters:
        mapped = [map_v4_filter_to_dms(f) for f in custom_filters]
        return [f for f in mapped if f]
    key: ScreenerPreset = preset or "custom"
    return list(MOEX_PRESETS.get(key, MOEX_PRESETS["custom"]))


def resolve_crypto_filters(
    *,
    preset: ScreenerPreset | None,
    custom_filters: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    base = dict(CRYPTO_PRESETS.get(preset or "custom", CRYPTO_PRESETS["custom"]))
    if custom_filters:
        for f in custom_filters:
            mapped = map_v4_filter_to_crypto(f)
            base.update(mapped)
    return base


def map_v4_filter_to_dms(raw: dict[str, Any]) -> dict[str, Any] | None:
    ftype = str(raw.get("type") or "").lower()
    op = str(raw.get("op") or ">")
    if ftype == "volume":
        return {"type": "volume", "min": float(raw.get("value") or 0)}
    if ftype == "hist_volume":
        return {"type": "min_avg_volume", "min": float(raw.get("value") or 0)}
    if ftype == "price":
        # handled as post-filter on last_price
        return {"type": "v4_price", "op": op, "value": float(raw.get("value") or 0)}
    if ftype == "atr":
        return {"type": "atr", "min_percent": float(raw.get("value") or 0)}
    if ftype == "gap":
        return {"type": "gap", "max_percent": float(raw.get("valuePct") or raw.get("value") or 0), "direction": "BOTH"}
    if ftype == "spread":
        return {"type": "spread", "max_percent": float(raw.get("valuePct") or raw.get("value") or 0)}
    if ftype == "list":
        tickers = [str(t).upper() for t in (raw.get("tickers") or [])]
        mode = str(raw.get("mode") or "include")
        if mode == "exclude":
            return {"type": "excluded_tickers", "list": tickers}
        return {"type": "only_tickers", "list": tickers}
    if ftype == "status":
        allowed = {str(x).lower() for x in (raw.get("allowed") or [])}
        out: list[dict[str, Any]] = []
        if "trading" in allowed:
            out.append({"type": "trading_status", "eq": "T"})
        return out[0] if out else None
    return None


def map_v4_filter_to_crypto(raw: dict[str, Any]) -> dict[str, Any]:
    ftype = str(raw.get("type") or "").lower()
    if ftype == "volume":
        return {"min_volume_24h_usd": float(raw.get("value") or 0)}
    if ftype == "spread":
        return {"max_spread_pct": float(raw.get("valuePct") or raw.get("value") or 0)}
    if ftype == "atr":
        return {"min_atr_percent": float(raw.get("value") or 0)}
    if ftype == "price":
        op = str(raw.get("op") or ">")
        val = float(raw.get("value") or 0)
        if op == "<":
            return {"max_last_price": val}
        return {"min_last_price": val}
    return {}


def moex_price_bounds(preset: ScreenerPreset | None, custom_filters: list[dict[str, Any]] | None) -> tuple[float | None, float | None]:
    if custom_filters:
        lo: float | None = None
        hi: float | None = None
        for f in custom_filters:
            if str(f.get("type") or "").lower() != "price":
                continue
            op = str(f.get("op") or ">")
            val = float(f.get("value") or 0)
            if op == ">":
                lo = val if lo is None else max(lo, val)
            elif op == "<":
                hi = val if hi is None else min(hi, val)
        return lo, hi
    key: ScreenerPreset = preset or "custom"
    return MOEX_PRICE_POST_FILTERS.get(key, (None, None))
