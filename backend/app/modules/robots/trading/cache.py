"""
Кэш для свечей и цен
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingCache [1]
#/// Исходный модуль `backend/app/modules/robots/trading/cache.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import asyncio


class CandlesCache:
    """
    Кэш для свечей с TTL (Time To Live)
    
    Использование:
        cache = CandlesCache(ttl_seconds=300)  # 5 минут
        cache.set("BBG004730ZJ9", "CANDLE_INTERVAL_DAY", 60, candles_data)
        cached = cache.get("BBG004730ZJ9", "CANDLE_INTERVAL_DAY", 60)
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Args:
            ttl_seconds: Время жизни кэша в секундах (по умолчанию 5 минут)
        """
        self._cache: Dict[str, Dict] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def _make_key(self, figi: str, interval: str, days: int) -> str:
        """Создает ключ для кэша"""
        return f"{figi}:{interval}:{days}"

    def get(self, figi: str, interval: str, days: int) -> Optional[List[Dict]]:
        """
        Получает свечи из кэша если они ещё валидны
        
        Returns:
            Список свечей или None если нет в кэше или истекли
        """
        key = self._make_key(figi, interval, days)

        if key in self._cache:
            entry = self._cache[key]
            if datetime.now(timezone.utc) < entry["expires_at"]:
                return entry["data"]
            else:
                # Истекло, удаляем
                del self._cache[key]

        return None

    def append_candle(self, figi: str, interval: str, days: int, candle: Dict) -> bool:
        """Добавляет или обновляет свечу в кэше (по time). Возвращает False если ключа нет."""
        key = self._make_key(figi, interval, days)
        entry = self._cache.get(key)
        if not entry:
            return False

        ts = str(candle.get("time") or "")
        data: List[Dict] = list(entry["data"])
        replaced = False
        for idx, existing in enumerate(data):
            if str(existing.get("time") or "") == ts:
                data[idx] = candle
                replaced = True
                break
        if not replaced:
            data.append(candle)
            data.sort(key=lambda c: str(c.get("time") or ""))

        now = datetime.now(timezone.utc)
        entry["data"] = data
        entry["expires_at"] = now + timedelta(seconds=self._ttl)
        return True

    def set(self, figi: str, interval: str, days: int, candles: List[Dict]):
        """
        Сохраняет свечи в кэш
        
        Args:
            figi: FIGI инструмента
            interval: Интервал свечей
            days: Количество дней
            candles: Список свечей
        """
        key = self._make_key(figi, interval, days)
        now = datetime.now(timezone.utc)

        self._cache[key] = {
            "data": candles,
            "expires_at": now + timedelta(seconds=self._ttl),
            "created_at": now,
            "figi": figi,
            "interval": interval,
            "days": days
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику кэша
        
        Returns:
            Dict с количеством записей и списком ключей
        """
        now = datetime.now(timezone.utc)
        active_entries = []

        for key, entry in self._cache.items():
            if now < entry["expires_at"]:
                remaining = int((entry["expires_at"] - now).total_seconds())
                active_entries.append({
                    "key": key,
                    "created_at": entry["created_at"].isoformat(),
                    "expires_in_seconds": remaining,
                    "candles_count": len(entry["data"])
                })

        return {
            "total_entries": len(self._cache),
            "active_entries": len(active_entries),
            "ttl_seconds": self._ttl,
            "entries": active_entries
        }

    def clear(self):
        """Очищает весь кэш"""
        self._cache.clear()

    def clear_expired(self):
        """Удаляет истекшие записи"""
        now = datetime.now(timezone.utc)
        expired_keys = [
            key for key, entry in self._cache.items()
            if now >= entry["expires_at"]
        ]
        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)


# Глобальный экземпляр кэша
_candles_cache = CandlesCache(ttl_seconds=86400)  # 24h, продлевается при append


def get_candles_cache() -> CandlesCache:
    """Возвращает глобальный кэш свечей"""
    return _candles_cache


def clear_candles_cache():
    """Очищает глобальный кэш свечей"""
    _candles_cache.clear()