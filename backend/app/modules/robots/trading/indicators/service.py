from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingIndicatorsService [1]
#/// Исходный модуль `backend/app/modules/robots/trading/indicators/service.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.database import SessionLocal
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.cache import get_candles_cache
from app.modules.market_data import repository as md_repo
from app.modules.market_data import service as md_service
from app.modules.market_data.candle_format import api_candle_to_db_tuple

logger = get_logger(__name__)

# Исторический bootstrap для live: 10m свечи через REST T-Bank.
BOOTSTRAP_INTERVAL = "CANDLE_INTERVAL_10_MIN"
# Оценка числа торговых свечей в день (MOEX акции, ~530 мин сессии).
_TRADING_MINUTES_PER_DAY = 530
_INTERVAL_MINUTES: Dict[str, int] = {
    "CANDLE_INTERVAL_1_MIN": 1,
    "CANDLE_INTERVAL_2_MIN": 2,
    "CANDLE_INTERVAL_3_MIN": 3,
    "CANDLE_INTERVAL_5_MIN": 5,
    "CANDLE_INTERVAL_10_MIN": 10,
    "CANDLE_INTERVAL_15_MIN": 15,
    "CANDLE_INTERVAL_30_MIN": 30,
    "CANDLE_INTERVAL_HOUR": 60,
    "CANDLE_INTERVAL_2_HOUR": 120,
    "CANDLE_INTERVAL_4_HOUR": 240,
    "CANDLE_INTERVAL_DAY": 1440,
}

MAX_DAYS_BY_INTERVAL: Dict[str, int] = {
    "CANDLE_INTERVAL_1_MIN": 1,
    "CANDLE_INTERVAL_2_MIN": 2,
    "CANDLE_INTERVAL_3_MIN": 3,
    "CANDLE_INTERVAL_5_MIN": 7,
    "CANDLE_INTERVAL_10_MIN": 14,
    "CANDLE_INTERVAL_15_MIN": 21,
    "CANDLE_INTERVAL_30_MIN": 31,
    "CANDLE_INTERVAL_HOUR": 180,
    "CANDLE_INTERVAL_2_HOUR": 365,
    "CANDLE_INTERVAL_4_HOUR": 365,
    "CANDLE_INTERVAL_DAY": 3650,
}


@dataclass
class _TrackedIndicator:
    robot_id: int
    namespace: str
    figi: str
    interval: str
    days: int
    broker: BrokerFacade


class IndicatorService:
    """Prefetch свечей: REST bootstrap + live candle stream (T-Bank)."""

    def __init__(self):
        self._tracked: Dict[Tuple[str, str, str, int], _TrackedIndicator] = {}
        self._robot_keys: Dict[int, set[Tuple[str, str, str, int]]] = {}
        self._lock = asyncio.Lock()

    def _cache_figi_key(self, namespace: str, figi: str) -> str:
        return f"{namespace}:{figi}"

    @staticmethod
    def _is_bybit_broker(broker: BrokerFacade) -> bool:
        return str(getattr(broker, "broker_type", "") or "").lower() == "bybit"

    @staticmethod
    def _bootstrap_interval(strategy_interval: str, broker: Optional[BrokerFacade] = None) -> str:
        # ByBit: bootstrap на интервале стратегии (M5 и т.п.). T-Invest: REST 10m.
        if broker is not None and IndicatorService._is_bybit_broker(broker):
            return strategy_interval or "CANDLE_INTERVAL_5_MIN"
        return BOOTSTRAP_INTERVAL

    async def _load_bybit_candles_with_stats(
        self,
        broker: BrokerFacade,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> Tuple[List[Dict], Dict[str, int]]:
        empty_stats = {"db_before": 0, "db_after": 0, "api_fetched": 0, "loaded": 0}
        symbol = str(figi or "").strip().upper()
        if not symbol:
            return [], empty_stats
        try:
            # Prefer DB candles_cache when present, then fill gaps via broker REST.
            from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows
            from app.modules.robots.trading.intervals import resolve_strategy_interval

            resolved = resolve_strategy_interval(interval)
            # code_num is minutes for intraday (5, 15, 60…); day/week use MOEX special codes.
            interval_num = int(getattr(resolved, "code_num", None) or 5)
            db = SessionLocal()
            try:
                cached_rows = query_candles_cache_rows(
                    db,
                    market="bybit",
                    ticker=symbol,
                    interval_code=resolved.cache_label,
                    interval_code_num=interval_num,
                    from_dt=from_date,
                    to_dt_exclusive=to_date,
                )
            finally:
                db.close()
            db_before = len(cached_rows or [])
            candles: List[Dict] = []
            for row in cached_rows or []:
                # SQLAlchemy Row: attribute or mapping access
                if hasattr(row, "_mapping"):
                    m = dict(row._mapping)
                elif isinstance(row, dict):
                    m = row
                else:
                    m = {
                        "candle_time": getattr(row, "candle_time", None),
                        "open": getattr(row, "open", 0),
                        "high": getattr(row, "high", 0),
                        "low": getattr(row, "low", 0),
                        "close": getattr(row, "close", 0),
                        "volume": getattr(row, "volume", 0),
                    }
                ct = m.get("candle_time")
                candles.append(
                    {
                        "time": ct.isoformat() if hasattr(ct, "isoformat") else str(ct or ""),
                        "open": float(m.get("open") or 0),
                        "high": float(m.get("high") or 0),
                        "low": float(m.get("low") or 0),
                        "close": float(m.get("close") or 0),
                        "volume": float(m.get("volume") or 0),
                    }
                )

            span_days = max(1, int((to_date - from_date).days or 1))
            need = self.estimate_candles_needed(span_days, interval, crypto_24_7=True)
            # Crypto 24/7: if cache is thin, fill via ByBit REST.
            api_fetched = 0
            if len(candles) < max(50, need // 4):
                rest = await broker.get_candles(symbol, from_date, to_date, interval)
                api_fetched = len(rest or [])
                if rest:
                    # Merge by time, prefer REST for overlapping bars.
                    by_t = {str(c.get("time")): c for c in candles}
                    for c in rest:
                        by_t[str(c.get("time"))] = c
                    candles = [by_t[k] for k in sorted(by_t.keys())]

            stats = {
                "db_before": db_before,
                "db_after": db_before,
                "api_fetched": api_fetched,
                "loaded": len(candles),
            }
            if api_log_func:
                try:
                    await api_log_func(
                        endpoint="bybit.market.get_kline",
                        request_data={
                            "symbol": symbol,
                            "interval": interval,
                            "from": from_date.isoformat(),
                            "to": to_date.isoformat(),
                        },
                        response_data=stats,
                        response_status=200,
                    )
                except Exception:
                    pass
            return candles, stats
        except Exception as e:
            logger.warning("ByBit candle load failed symbol=%s: %s", symbol, e)
            if api_log_func:
                try:
                    await api_log_func(
                        endpoint="bybit.market.get_kline",
                        request_data={"symbol": symbol, "interval": interval},
                        error_message=str(e),
                    )
                except Exception:
                    pass
            return [], empty_stats

    async def _load_candles_with_stats(
        self,
        broker: BrokerFacade,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> Tuple[List[Dict], Dict[str, int]]:
        if self._is_bybit_broker(broker):
            return await self._load_bybit_candles_with_stats(
                broker, figi, from_date, to_date, interval, api_log_func=api_log_func
            )
        return await self._load_tinvest_candles_with_stats(
            broker, figi, from_date, to_date, interval, api_log_func=api_log_func
        )

    @staticmethod
    def _stream_interval(strategy_interval: str) -> str:
        # Live stream: используем интервал стратегии (обычно 10m).
        return strategy_interval or BOOTSTRAP_INTERVAL

    def _resolve_request_days(self, strategy_params: Dict, interval: str) -> int:
        raw = strategy_params.get("candle_days", strategy_params.get("request_candle_days", 14))
        try:
            days = int(raw)
        except Exception:
            days = 14
        days = max(1, days)
        cap = MAX_DAYS_BY_INTERVAL.get(interval, 14)
        if days > cap:
            logger.warning(
                "candle_days=%s exceeds cap=%s for interval=%s; clamped",
                days,
                cap,
                interval,
            )
            days = cap
        return days

    @staticmethod
    def estimate_candles_needed(days: int, interval: str, *, crypto_24_7: bool = False) -> int:
        bar_minutes = _INTERVAL_MINUTES.get(interval, 10)
        session_minutes = 1440 if crypto_24_7 else _TRADING_MINUTES_PER_DAY
        bars_per_day = max(1, session_minutes // bar_minutes)
        return max(1, days) * bars_per_day

    async def _load_candles(
        self,
        broker: BrokerFacade,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> List[Dict]:
        candles, _ = await self._load_candles_with_stats(
            broker, figi, from_date, to_date, interval, api_log_func=api_log_func
        )
        return candles

    async def _load_tinvest_candles(
        self,
        broker: BrokerFacade,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> List[Dict]:
        candles, _ = await self._load_tinvest_candles_with_stats(
            broker, figi, from_date, to_date, interval, api_log_func=api_log_func
        )
        return candles

    async def _load_tinvest_candles_with_stats(
        self,
        broker: BrokerFacade,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> Tuple[List[Dict], Dict[str, int]]:
        empty_stats = {"db_before": 0, "db_after": 0, "api_fetched": 0, "loaded": 0}
        if not str(figi or "").upper().startswith("BBG"):
            logger.warning("Skip T-Bank candles for non-FIGI key=%s", figi)
            return [], empty_stats
        schema = settings.DB_SCHEMA
        db = SessionLocal()
        try:
            db_before = md_repo.count_candles_in_range(
                db, schema, figi, interval, from_date, to_date
            )
            stages = await md_service.ensure_candles_cover_window(
                db=db,
                figi=figi,
                interval=interval,
                from_dt=from_date,
                to_dt=to_date,
                token=broker.auth_token,
                data_source="tinvest",
            )
            db_after = md_repo.count_candles_in_range(
                db, schema, figi, interval, from_date, to_date
            )
            candles = md_service.load_candles_for_backtest(
                db=db,
                figi=figi,
                interval=interval,
                from_dt=from_date,
                to_dt=to_date,
            )
            loaded = len(candles or [])
            stats = {
                "db_before": db_before,
                "db_after": db_after,
                "api_fetched": max(0, db_after - db_before),
                "loaded": loaded,
            }
            if api_log_func:
                try:
                    await api_log_func(
                        endpoint="tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
                        request_data={
                            "figi": figi,
                            "interval": interval,
                            "from": from_date.isoformat(),
                            "to": to_date.isoformat(),
                        },
                        response_data={
                            "candles_count": loaded,
                            "stages": stages,
                            **stats,
                        },
                        response_status=200,
                    )
                except Exception:
                    pass
            return list(candles or []), stats
        except Exception as e:
            db.rollback()
            logger.warning(
                "T-Bank candle fetch skipped figi=%s interval=%s error=%s",
                figi,
                interval,
                e,
            )
            if api_log_func:
                try:
                    await api_log_func(
                        endpoint="tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
                        request_data={
                            "figi": figi,
                            "interval": interval,
                            "from": from_date.isoformat(),
                            "to": to_date.isoformat(),
                        },
                        error_message=str(e),
                    )
                except Exception:
                    pass
            return [], empty_stats
        finally:
            db.close()

    async def bootstrap_candles_at_startup(
        self,
        robot_id: int,
        broker: BrokerFacade,
        figis: List[str],
        strategy_params: Dict,
        log_func: Optional[Callable[[str], None]] = None,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> None:
        """Предзагрузка истории в кэш + диагностика по БД/API в лог сессии."""
        interval = strategy_params.get("interval")
        if not interval:
            if log_func:
                log_func("📊 [Свечи] Интервал не задан — bootstrap пропущен")
            return

        days = self._resolve_request_days(strategy_params, interval)
        bootstrap_iv = self._bootstrap_interval(interval, broker)
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)
        crypto = self._is_bybit_broker(broker)
        needed_per_figi = self.estimate_candles_needed(days, bootstrap_iv, crypto_24_7=crypto)
        cache = get_candles_cache()
        namespace = broker.cache_namespace

        def _log(msg: str) -> None:
            logger.info(msg)
            if log_func:
                log_func(msg)

        _log(
            f"📊 [Свечи] Bootstrap: бумаг={len(figis)}, период={days}д, "
            f"стратегия={interval}, REST={bootstrap_iv}, "
            f"broker={'bybit' if crypto else 'tinvest'}, "
            f"окно {from_date.date()}..{to_date.date()}, нужно~{needed_per_figi}/FIGI"
        )

        sum_needed = 0
        sum_db_before = 0
        sum_api = 0
        sum_loaded = 0

        for figi in figis:
            cache_figi = self._cache_figi_key(namespace, figi)
            cached = cache.get(cache_figi, interval, days)
            if cached is not None and len(cached) > 0:
                _log(
                    f"📊 [Свечи] {figi}: уже в кэше={len(cached)} "
                    f"(нужно~{needed_per_figi})"
                )
                sum_loaded += len(cached)
                sum_needed += needed_per_figi
                continue

            candles, stats = await self._load_candles_with_stats(
                broker,
                figi,
                from_date,
                to_date,
                bootstrap_iv,
                api_log_func=api_log_func,
            )
            cache.set(cache_figi, interval, days, candles)
            _log(
                f"📊 [Свечи] {figi}: нужно~{needed_per_figi}, "
                f"в БД до={stats['db_before']}, запрошено API={stats['api_fetched']}, "
                f"в БД после={stats['db_after']}, загружено={stats['loaded']}"
            )
            sum_needed += needed_per_figi
            sum_db_before += stats["db_before"]
            sum_api += stats["api_fetched"]
            sum_loaded += stats["loaded"]

        _log(
            f"📊 [Свечи] Итого: нужно~{sum_needed}, в БД до={sum_db_before}, "
            f"запрошено API={sum_api}, в кэше/загружено={sum_loaded}"
        )

    async def on_closed_candle(
        self,
        robot_id: int,
        broker: BrokerFacade,
        figi: str,
        candle: Dict,
        strategy_params: Dict,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
        *,
        persist_to_db: bool = True,
    ) -> None:
        """Добавляет закрытую свечу из WS-потока в кэш."""
        interval = strategy_params.get("interval") or BOOTSTRAP_INTERVAL
        days = self._resolve_request_days(strategy_params, interval)
        namespace = broker.cache_namespace
        cache_figi = self._cache_figi_key(namespace, figi)
        cache = get_candles_cache()

        existing = cache.get(cache_figi, interval, days)
        if not existing:
            # Если bootstrap ещё не был — подгрузим историю.
            to_date = datetime.now(timezone.utc)
            from_date = to_date - timedelta(days=days)
            bootstrap_iv = self._bootstrap_interval(interval, broker)
            historical = await self._load_candles(
                broker, figi, from_date, to_date, bootstrap_iv, api_log_func=api_log_func
            )
            cache.set(cache_figi, interval, days, historical)

        if cache.append_candle(cache_figi, interval, days, candle):
            logger.info(
                "Closed candle appended robot_id=%s figi=%s interval=%s time=%s",
                robot_id,
                figi,
                interval,
                candle.get("time"),
            )
        else:
            cache.set(cache_figi, interval, days, [candle])

        is_bybit = self._is_bybit_broker(broker)
        if persist_to_db and not is_bybit:
            # Live T-Invest: каждую закрытую свечу persist'им в БД.
            # ByBit history живёт в candles_cache / REST bootstrap — не пишем в T-Invest schema.
            try:
                db = SessionLocal()
                try:
                    row = api_candle_to_db_tuple(candle, figi, interval)
                    md_repo.upsert_candles_batch(db, md_service.settings.DB_SCHEMA, [row])
                    db.commit()
                finally:
                    db.close()
            except Exception:
                logger.exception("Failed to persist closed candle figi=%s interval=%s", figi, interval)

        if api_log_func:
            try:
                endpoint = (
                    "bybit.ws.kline"
                    if is_bybit
                    else "tinkoff.public.invest.api.contract.v1.MarketDataStreamService/MarketDataStream"
                )
                await api_log_func(
                    endpoint=endpoint,
                    request_data={
                        "type": "candle_closed",
                        "figi": figi,
                        "interval": interval,
                    },
                    response_data={
                        "time": candle.get("time"),
                        "isComplete": candle.get("isComplete"),
                    },
                    response_status=200,
                )
            except Exception:
                pass

    async def register_robot(
        self,
        robot_id: int,
        broker: BrokerFacade,
        figis: List[str],
        strategy_params: Dict,
    ) -> None:
        interval = strategy_params.get("interval")
        if not interval:
            return
        days = self._resolve_request_days(strategy_params, interval)
        namespace = broker.cache_namespace

        async with self._lock:
            keys = self._robot_keys.setdefault(robot_id, set())
            for figi in figis:
                key = (namespace, figi, interval, days)
                keys.add(key)
                if key not in self._tracked:
                    self._tracked[key] = _TrackedIndicator(
                        robot_id=robot_id,
                        namespace=namespace,
                        figi=figi,
                        interval=interval,
                        days=days,
                        broker=broker,
                    )

    async def unregister_robot(self, robot_id: int) -> None:
        async with self._lock:
            keys = self._robot_keys.pop(robot_id, set())
            for key in keys:
                still_used = any(key in s for s in self._robot_keys.values())
                if not still_used:
                    self._tracked.pop(key, None)

    async def get_candles_batch(
        self,
        broker: BrokerFacade,
        figis: List[str],
        strategy_params: Dict,
        robot_id: Optional[int] = None,
        api_log_func: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> Dict[str, List[Dict]]:
        interval = strategy_params["interval"]
        days = self._resolve_request_days(strategy_params, interval)
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days)
        cache = get_candles_cache()
        result: Dict[str, List[Dict]] = {}
        namespace = broker.cache_namespace
        bootstrap_iv = self._bootstrap_interval(interval, broker)

        for figi in figis:
            cache_figi = self._cache_figi_key(namespace, figi)
            cached = cache.get(cache_figi, interval, days)
            if cached is not None and len(cached) > 0:
                result[figi] = cached
                continue

            candles = await self._load_candles(
                broker, figi, from_date, to_date, bootstrap_iv, api_log_func=api_log_func
            )
            logger.info(
                "Bootstrap candles figi=%s interval=%s count=%s robot_id=%s broker=%s",
                figi,
                bootstrap_iv,
                len(candles),
                robot_id,
                getattr(broker, "broker_type", None),
            )
            cache.set(cache_figi, interval, days, candles)
            result[figi] = candles
        return result


indicator_service = IndicatorService()
