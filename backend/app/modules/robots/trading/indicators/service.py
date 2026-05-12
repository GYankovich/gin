from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingIndicatorsService [1]
#/// Исходный модуль `backend/app/modules/robots/trading/indicators/service.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.core.logging_config import get_logger
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.cache import get_candles_cache

logger = get_logger(__name__)


@dataclass
class _TrackedIndicator:
    namespace: str
    figi: str
    interval: str
    days: int
    period_seconds: int
    next_update_at: datetime
    broker: BrokerFacade


class IndicatorService:
    """Background indicator data prefetcher + cache accessor."""

    def __init__(self):
        self._tracked: Dict[Tuple[str, str, str, int], _TrackedIndicator] = {}
        self._robot_keys: Dict[int, set[Tuple[str, str, str, int]]] = {}
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def _period_for_interval(self, interval: str) -> int:
        mapping = {
            "CANDLE_INTERVAL_1_MIN": 300,
            "CANDLE_INTERVAL_2_MIN": 300,
            "CANDLE_INTERVAL_3_MIN": 300,
            "CANDLE_INTERVAL_5_MIN": 300,
            "CANDLE_INTERVAL_10_MIN": 900,
            "CANDLE_INTERVAL_15_MIN": 900,
            "CANDLE_INTERVAL_30_MIN": 900,
            "CANDLE_INTERVAL_HOUR": 3600,
            "CANDLE_INTERVAL_2_HOUR": 3600,
            "CANDLE_INTERVAL_4_HOUR": 3600,
            "CANDLE_INTERVAL_DAY": 86400,
        }
        return mapping.get(interval, 300)

    def _cache_figi_key(self, namespace: str, figi: str) -> str:
        return f"{namespace}:{figi}"

    def _daily_next_update(self, now_utc: datetime) -> datetime:
        # 10:00 MSK = 07:00 UTC
        target = now_utc.replace(hour=7, minute=0, second=0, microsecond=0)
        if now_utc >= target:
            target += timedelta(days=1)
        return target

    async def register_robot(self, robot_id: int, broker: BrokerFacade, figis: List[str], strategy_params: Dict) -> None:
        interval = strategy_params.get("interval")
        if not interval:
            return
        days = int(strategy_params.get("candle_days", 60))
        period = self._period_for_interval(interval)
        now = datetime.now(timezone.utc)
        namespace = broker.cache_namespace

        async with self._lock:
            keys = self._robot_keys.setdefault(robot_id, set())
            for figi in figis:
                key = (namespace, figi, interval, days)
                keys.add(key)
                if key not in self._tracked:
                    next_update_at = now if interval != "CANDLE_INTERVAL_DAY" else self._daily_next_update(now)
                    self._tracked[key] = _TrackedIndicator(
                        namespace=namespace,
                        figi=figi,
                        interval=interval,
                        days=days,
                        period_seconds=period,
                        next_update_at=next_update_at,
                        broker=broker,
                    )
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._loop())

    async def unregister_robot(self, robot_id: int) -> None:
        async with self._lock:
            keys = self._robot_keys.pop(robot_id, set())
            for key in keys:
                still_used = any(key in s for s in self._robot_keys.values())
                if not still_used:
                    self._tracked.pop(key, None)
            if not self._robot_keys and self._task and not self._task.done():
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)

    async def get_candles_batch(
        self,
        broker: BrokerFacade,
        figis: List[str],
        strategy_params: Dict,
    ) -> Dict[str, List[Dict]]:
        interval = strategy_params["interval"]
        days = int(strategy_params.get("candle_days", 60))
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)
        cache = get_candles_cache()
        result: Dict[str, List[Dict]] = {}
        namespace = broker.cache_namespace

        for figi in figis:
            cache_figi = self._cache_figi_key(namespace, figi)
            cached = cache.get(cache_figi, interval, days)
            if cached is not None:
                result[figi] = cached
                continue
            candles = await broker.get_candles(figi, from_date, to_date, interval)
            cache.set(cache_figi, interval, days, candles)
            result[figi] = candles
        return result

    async def _loop(self) -> None:
        while True:
            try:
                now = datetime.now(timezone.utc)
                to_refresh: List[_TrackedIndicator] = []
                async with self._lock:
                    for tracked in self._tracked.values():
                        if tracked.next_update_at <= now:
                            to_refresh.append(tracked)

                for tracked in to_refresh:
                    try:
                        to_date = datetime.now(timezone.utc)
                        from_date = to_date - timedelta(days=tracked.days)
                        candles = await tracked.broker.get_candles(
                            tracked.figi,
                            from_date,
                            to_date,
                            tracked.interval,
                        )
                        cache_figi = self._cache_figi_key(tracked.namespace, tracked.figi)
                        get_candles_cache().set(cache_figi, tracked.interval, tracked.days, candles)
                        tracked.next_update_at = (
                            self._daily_next_update(to_date)
                            if tracked.interval == "CANDLE_INTERVAL_DAY"
                            else to_date + timedelta(seconds=tracked.period_seconds)
                        )
                    except Exception:
                        logger.exception(
                            "Indicator refresh failed for figi=%s interval=%s",
                            tracked.figi,
                            tracked.interval,
                        )
                        tracked.next_update_at = datetime.now(timezone.utc) + timedelta(seconds=30)

                get_candles_cache().clear_expired()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("IndicatorService loop failed")
                await asyncio.sleep(5)


indicator_service = IndicatorService()
