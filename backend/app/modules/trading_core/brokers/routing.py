"""
Маршрутизация брокеров LIVE (BRD-ARCH-04 этап 6).

Единая точка: normalize broker_type, фильтр инструментов, проверка поддержки.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SUPPORTED_LIVE_BROKERS = frozenset({"tinvest", "bybit"})
STUB_BROKERS = frozenset({"vtb", "alfa"})
DEFAULT_BROKER = "tinvest"

# dictionary TOKEN.TYPE num_value → broker_type робота
TOKEN_TYPE_BROKER = {
    1: "tinvest",
    2: "bybit",
}


def broker_from_token_type(token_type: int | None) -> str:
    """Брокер по типу API-токена (1 — T-Invest, 2 — ByBit)."""
    try:
        key = int(token_type)
    except (TypeError, ValueError):
        return DEFAULT_BROKER
    return TOKEN_TYPE_BROKER.get(key, DEFAULT_BROKER)


class BrokerTokenMismatchError(ValueError):
    """config.broker_type не совпадает с типом API-токена."""

    def __init__(
        self,
        *,
        expected: str,
        actual: str,
        token_type: int | None = None,
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.token_type = token_type
        suffix = f" (token_type={token_type})" if token_type is not None else ""
        super().__init__(
            f"broker_type должен быть '{expected}' по токену, в config='{actual}'{suffix}"
        )


# Optional aliases for legacy / display labels. Canonical codes come from
# dictionary.TOKEN.TYPE.string_value (e.g. portfolio_updater query).
_BROKER_ALIASES = {
    "tinvest": "tinvest",
    "t-invest": "tinvest",
    "t_invest": "tinvest",
    "tinkoff": "tinvest",
    "t-bank": "tinvest",
    "tbank": "tinvest",
    "bybit": "bybit",
}


def normalize_broker_type(value: str | None) -> str:
    raw = (value or DEFAULT_BROKER).strip().lower()
    if not raw:
        return DEFAULT_BROKER
    return _BROKER_ALIASES.get(raw, raw)


def resolve_broker_from_token(
    token_type: int | None = None,
    *,
    token_type_name: str | None = None,
) -> str:
    """Источник истины: тип токена → broker_type."""
    if token_type is not None:
        return broker_from_token_type(token_type)
    name = str(token_type_name or "").strip()
    if name:
        return normalize_broker_type(name)
    return DEFAULT_BROKER


def enforce_broker_for_token(
    config: Optional[Dict[str, Any]] = None,
    *,
    token_type: int | None = None,
    token_type_name: str | None = None,
    mutate: bool = True,
    require_token: bool = False,
) -> str:
    """
    Строго резолвит брокера из токена.

    - Если token_type / token_type_name задан: broker только из токена.
      При непустом config.broker_type и расхождении — BrokerTokenMismatchError.
      При mutate=True записывает config['broker_type'] = expected.
    - Если токена нет (backtest без token): fallback на config.broker_type,
      либо ValueError при require_token=True.
    """
    has_token = token_type is not None or bool(str(token_type_name or "").strip())
    if not has_token:
        if require_token:
            raise ValueError("token_type обязателен для выбора брокера")
        cfg = config if isinstance(config, dict) else {}
        return normalize_broker_type(str(cfg.get("broker_type") or DEFAULT_BROKER))

    expected = resolve_broker_from_token(token_type, token_type_name=token_type_name)
    if isinstance(config, dict):
        raw = config.get("broker_type")
        if raw is not None and str(raw).strip():
            actual = normalize_broker_type(str(raw))
            if actual != expected:
                raise BrokerTokenMismatchError(
                    expected=expected,
                    actual=actual,
                    token_type=int(token_type) if token_type is not None else None,
                )
        if mutate:
            config["broker_type"] = expected
    return expected


def is_supported_live_broker(broker_type: str | None) -> bool:
    return normalize_broker_type(broker_type) in SUPPORTED_LIVE_BROKERS


def is_stub_broker(broker_type: str | None) -> bool:
    return normalize_broker_type(broker_type) in STUB_BROKERS


def filter_allowed_instruments(
    broker_type: str | None,
    instruments: List[str],
) -> Tuple[List[str], int]:
    """
    T-Invest: только FIGI (BBG…).
    """
    raw = list(instruments or [])
    bt = normalize_broker_type(broker_type)

    if bt == "tinvest":
        out = [str(x).strip().upper() for x in raw if str(x).strip().upper().startswith("BBG")]
        return out, len(raw) - len(out)

    out = [str(x).strip().upper() for x in raw if str(x).strip()]
    return out, len(raw) - len(out)


def backtest_data_source_for_broker(broker_type: str | None) -> str:
    """Исторические свечи backtest: MOEX/cache независимо от LIVE-брокера."""
    return "moex"


def resolve_bybit_api_secret(
    *,
    api_secret: str | None = None,
    token_extra_data: Optional[Dict[str, Any]] = None,
) -> str | None:
    secret = str(api_secret or "").strip()
    if secret:
        return secret
    extra = token_extra_data if isinstance(token_extra_data, dict) else {}
    from_extra = str(extra.get("token_secret") or extra.get("api_secret") or "").strip()
    return from_extra or None


def resolve_bybit_instrument_category(config: Optional[Dict[str, Any]]) -> str:
    cfg = config if isinstance(config, dict) else {}
    bybit = cfg.get("bybit") if isinstance(cfg.get("bybit"), dict) else {}
    return str(bybit.get("instrument_category") or "linear").strip().lower()


def live_market_data_provider(broker_type: str | None) -> str:
    bt = normalize_broker_type(broker_type)
    if bt == "tinvest":
        return "tinvest"
    if bt == "bybit":
        return "bybit_market"
    return "unknown"


__all__ = [
    "DEFAULT_BROKER",
    "SUPPORTED_LIVE_BROKERS",
    "STUB_BROKERS",
    "TOKEN_TYPE_BROKER",
    "BrokerTokenMismatchError",
    "backtest_data_source_for_broker",
    "broker_from_token_type",
    "enforce_broker_for_token",
    "filter_allowed_instruments",
    "is_stub_broker",
    "is_supported_live_broker",
    "live_market_data_provider",
    "normalize_broker_type",
    "resolve_broker_from_token",
    "resolve_bybit_api_secret",
    "resolve_bybit_instrument_category",
]
