# app/modules/tinvest/utils.py
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def safe_float(value: Any, default: float = 0.0) -> float:
    """Безопасное преобразование в float"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Безопасное преобразование в int"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_str(value: Any, default: str = '') -> str:
    """Безопасное преобразование в строку"""
    if value is None:
        return default
    return str(value)


def safe_bool(value: Any, default: bool = False) -> bool:
    """Безопасное преобразование в bool"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return bool(value)


def parse_money_value(money_value: dict) -> Optional[dict]:
    """Парсинг MoneyValue в словарь"""
    if not money_value:
        return None

    units = safe_int(money_value.get("units", 0))
    nano = money_value.get("nano", 0)
    decimal_value = units + nano / 1e9

    return {
        "currency": safe_str(money_value.get("currency", "RUB")).upper(),
        "units": units,
        "nano": nano,
        "decimal": round(decimal_value, 2)
    }


def parse_quotation(quotation: dict) -> Optional[dict]:
    """Парсинг Quotation в словарь"""
    if not quotation:
        return None

    units = safe_int(quotation.get("units", 0))
    nano = quotation.get("nano", 0)
    decimal_value = units + nano / 1e9

    return {
        "units": units,
        "nano": nano,
        "decimal": round(decimal_value, 4)
    }


def parse_portfolio_position(position: dict) -> dict:
    """Парсинг позиции портфеля"""
    return {
        "figi": position.get("figi"),
        "instrument_type": safe_str(position.get("instrumentType", "")),
        "quantity": parse_quotation(position.get("quantity")),
        "average_position_price": parse_money_value(position.get("averagePositionPrice")),
        "current_price": parse_money_value(position.get("currentPrice")),
        "expected_yield": parse_quotation(position.get("expectedYield")),
        "daily_yield": parse_money_value(position.get("dailyYield")),
        "blocked": safe_bool(position.get("blocked", False)),
        "ticker": position.get("ticker"),
        "class_code": position.get("classCode"),
        "position_uid": position.get("positionUid"),
        "instrument_uid": position.get("instrumentUid")
    }


def mask_token(token: str, preview_length: int = 8) -> str:
    """Маскирует токен для безопасного отображения"""
    if not token:
        return "***"

    token_str = safe_str(token)

    if len(token_str) > preview_length * 2:
        return f"{token_str[:preview_length]}...{token_str[-preview_length:]}"

    return "***"