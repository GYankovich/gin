#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestUtils [1]
#/// Исходный модуль `backend/app/modules/tinvest/utils.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/tinvest/utils.py
"""
Специфичные для T-Invest утилиты парсинга
"""
from datetime import datetime, timezone
from typing import Any, Optional, Dict

from app.modules.robots.common.utils import safe_int, safe_str, safe_float, safe_bool, mask_token


def parse_api_timestamp(value: Any) -> Optional[datetime]:
    """Парсит Timestamp из T-Invest API (ISO-строка или {seconds,nanos})."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(value, dict):
        sec = value.get("seconds")
        if sec is None:
            return None
        dt = datetime.fromtimestamp(int(sec), tz=timezone.utc)
        nanos = int(value.get("nanos") or 0)
        if nanos:
            dt = dt.replace(microsecond=min(nanos // 1000, 999999))
        return dt
    return None


def parse_money_value(money_value: dict) -> Optional[dict]:
    """Парсинг MoneyValue из T-Invest API"""
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
    """Парсинг Quotation из T-Invest API"""
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


def parse_account_type(account_type: str) -> str:
    """Парсит тип счета из ответа T-Invest"""
    return safe_str(account_type).replace("ACCOUNT_TYPE_", "")


def parse_account_status(status: str) -> str:
    """Парсит статус счета из ответа T-Invest"""
    return safe_str(status).replace("ACCOUNT_STATUS_", "")