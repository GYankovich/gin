# app/modules/robots/common/utils.py
"""
Вспомогательные функции для роботов
"""
from datetime import datetime, timezone
from typing import Any, Optional
import json


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


def safe_float(value: Any, default: float = 0.0) -> float:
    """Безопасное преобразование в float"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """Безопасное преобразование в bool"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return bool(value)


def safe_datetime_now() -> datetime:
    """Текущее время в UTC"""
    return datetime.now(timezone.utc)


def safe_json_dumps(data: Any, default: str = "{}") -> str:
    """Безопасное преобразование в JSON строку"""
    if data is None:
        return default
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return default


def safe_json_loads(data: str, default: Any = None) -> Any:
    """Безопасное преобразование JSON строки в объект"""
    if not data:
        return default
    try:
        return json.loads(data)
    except Exception:
        return default


def mask_token(token: str, visible_chars: int = 6) -> str:
    """Маскирует токен для безопасного отображения"""
    if not token:
        return "***"

    token_str = safe_str(token)
    if len(token_str) <= visible_chars * 2:
        return "***"

    return f"{token_str[:visible_chars]}...{token_str[-visible_chars:]}"


def format_duration(ms: int) -> str:
    """Форматирует длительность в человеко-читаемый вид"""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        minutes = ms // 60000
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"


def parse_account_type(account_type: str) -> str:
    """Парсит тип счета из ответа T-Invest"""
    return safe_str(account_type).replace("ACCOUNT_TYPE_", "")


def parse_account_status(status: str) -> str:
    """Парсит статус счета из ответа T-Invest"""
    return safe_str(status).replace("ACCOUNT_STATUS_", "")


def parse_money_value(money_value: dict) -> Optional[dict]:
    """Парсит MoneyValue из T-Invest API"""
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
    """Парсит Quotation из T-Invest API"""
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


class Singleton:
    """
    Декоратор для реализации паттерна Singleton
    """
    def __init__(self, cls):
        self._cls = cls
        self._instance = None

    def __call__(self, *args, **kwargs):
        if self._instance is None:
            self._instance = self._cls(*args, **kwargs)
        return self._instance