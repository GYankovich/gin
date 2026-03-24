# app/modules/robots/common/utils.py
"""
Общие утилиты для роботов
"""
from datetime import datetime, timezone
from typing import Any, Optional
import json


# ============================================================
# Безопасные преобразования
# ============================================================

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


# ============================================================
# Работа с датой и временем
# ============================================================

def safe_datetime_now() -> datetime:
    """Текущее время в UTC"""
    return datetime.now(timezone.utc)


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


# ============================================================
# Работа с JSON
# ============================================================

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


# ============================================================
# Маскирование чувствительных данных
# ============================================================

def mask_token(token: str, visible_chars: int = 6) -> str:
    """Маскирует токен для безопасного отображения"""
    if not token:
        return "***"

    token_str = safe_str(token)
    if len(token_str) <= visible_chars * 2:
        return "***"

    return f"{token_str[:visible_chars]}...{token_str[-visible_chars:]}"


# ============================================================
# Singleton декоратор
# ============================================================

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