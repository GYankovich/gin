"""
TradingOrchestrator — единая точка запуска live/backtest replay (BRD-ARCH-04 §4.4).

Фаза simulating history-backtest идёт только через `run_backtest_replay`.
Legacy: `engine.run_backtest_simulation`, `unified_runner` — не для prod.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.robots.trading.backtest.types import BacktestResult, candle_time_iso
from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.costs import resolve_backtest_fee_model, resolve_backtest_sim_rates
from app.modules.robots.trading.data.stats import CandlePrefetchStats, FundingPrefetchStats
from app.modules.robots.trading.intervals import ResolvedInterval
from app.modules.robots.trading.session_factory import create_trading_session

logger = logging.getLogger(__name__)

_default_orchestrator: Optional["TradingOrchestrator"] = None


def _cache_row_to_candle_dict(row: Any) -> Dict[str, Any]:
    close = float(row["close"] or 0)
    units = int(close)
    nano = int(round((close - units) * 1_000_000_000))
    ct = row["candle_time"]
    time_iso = ct.isoformat() if hasattr(ct, "isoformat") else str(ct or "")
    return {
        "time": time_iso,
        "open": {"units": int(float(row["open"] or 0)), "nano": 0},
        "high": {"units": int(float(row["high"] or 0)), "nano": 0},
        "low": {"units": int(float(row["low"] or 0)), "nano": 0},
        "close": {"units": units, "nano": nano},
        "volume": int(row["volume"] or 0),
    }


def build_allowed_figis_by_date(
    candles_by_figi: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """День → список тикеров с барами в этот день (для pipeline/universe в backtest)."""
    by_day: Dict[str, List[str]] = {}
    for figi, series in (candles_by_figi or {}).items():
        tk = str(figi).strip().upper()
        if not tk:
            continue
        for c in series or []:
            iso = candle_time_iso(c)
            if not iso or len(iso) < 10:
                continue
            day = iso[:10]
            lst = by_day.setdefault(day, [])
            if tk not in lst:
                lst.append(tk)
    return by_day


def build_allowed_symbols_by_date(
    candles_by_symbol: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """Alias for crypto replay: symbol → day → tradable symbols."""
    return build_allowed_figis_by_date(candles_by_symbol)


class TradingOrchestrator:
    """Оркестратор: backtest replay через BacktestTradingSession (то же ядро, что live)."""

    async def run_live_session(
        self,
        *,
        schema: str,
        robot_id: int,
        user_id: int,
        token_id: int,
        token: str,
        config: Dict[str, Any],
        db: Optional[Session] = None,
        log_func=None,
        token_extra_data: Optional[Dict[str, Any]] = None,
        token_type: int | None = None,
    ) -> Dict[str, Any]:
        """
        Единая точка входа для live-цикла (target §9.1).

        Scheduler обязан вызывать orchestrator, а не напрямую session_factory.
        """
        from app.modules.robots.trading.brokers.routing import enforce_broker_for_token

        cfg = dict(config or {})
        broker_type = enforce_broker_for_token(
            cfg,
            token_type=token_type,
            mutate=True,
            require_token=token_type is not None,
        )
        session = create_trading_session(
            ExecutionMode.LIVE,
            db=db,
            schema=schema,
            robot_id=int(robot_id),
            user_id=int(user_id),
            token_id=int(token_id),
            token=token or "",
            config=cfg,
            log_func=log_func,
            token_extra_data=dict(token_extra_data or {}),
            token_type=token_type,
        )
        session.running = True
        strategy = str(cfg.get("strategy") or getattr(session, "strategy_name", "") or "")
        logger.info(
            "TradingOrchestrator.run_live_session robot_id=%s broker_type=%s strategy=%s",
            robot_id,
            broker_type,
            strategy,
        )
        return await session.run()

    def load_candles_by_symbol_from_cache(
        self,
        db: Session,
        *,
        symbols: List[str],
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
        market: str = "bybit",
        batch_size: int = 200,
    ) -> Dict[str, List[Dict[str, Any]]]:
        from app.modules.robots.trading.data import get_market_data_facade

        market_data = get_market_data_facade()
        normalized = [str(raw or "").strip().upper() for raw in symbols if str(raw or "").strip()]
        if not normalized:
            return {}

        bulk_rows = market_data.read_candles_cache_rows_bulk(
            db,
            market=market,
            instrument_ids=normalized,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
            batch_size=batch_size,
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for symbol in normalized:
            rows = bulk_rows.get(symbol) or []
            if rows:
                out[symbol] = [_cache_row_to_candle_dict(r) for r in rows]
        return out

    async def prefetch_crypto_candles_for_replay(
        self,
        db: Session,
        *,
        symbols: List[str],
        resolved: ResolvedInterval,
        from_date: date,
        till_date: date,
        instrument_category: str = "linear",
        testnet: bool = True,
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        load_cached_candles: bool = False,
    ) -> tuple[CandlePrefetchStats, Dict[str, List[Dict[str, Any]]]]:
        """
        ByBit historical kline prefetch (market=bybit) → candles_cache.

        По умолчанию свечи в память не грузит (один bulk SELECT на фазе loading_candles).
        """
        from app.modules.robots.trading.data.providers.bybit_market import ensure_candles_bybit_market

        stats = await ensure_candles_bybit_market(
            db,
            symbols=symbols,
            resolved=resolved,
            from_date=from_date,
            till_date=till_date,
            instrument_category=instrument_category,
            testnet=testnet,
            user_id=user_id,
            run_id=run_id,
            api_key=api_key,
            api_secret=api_secret,
            is_cancelled=is_cancelled,
            progress_callback=progress_callback,
        )
        if not load_cached_candles:
            return stats, {}

        from_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_dt_exclusive = datetime.combine(till_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        candles_by_symbol = self.load_candles_by_symbol_from_cache(
            db,
            symbols=list(symbols),
            interval_code=resolved.cache_label,
            interval_code_num=resolved.code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )
        return stats, candles_by_symbol

    async def prefetch_crypto_funding_for_replay(
        self,
        db: Session,
        *,
        symbols: List[str],
        from_date: date,
        till_date: date,
        instrument_category: str = "linear",
        testnet: bool = True,
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> FundingPrefetchStats:
        """ByBit funding history prefetch → bybit_funding_history for replay."""
        from app.modules.robots.trading.data.providers.bybit_market import ensure_funding_bybit_market

        return await ensure_funding_bybit_market(
            db,
            symbols=symbols,
            from_date=from_date,
            till_date=till_date,
            instrument_category=instrument_category,
            testnet=testnet,
            user_id=user_id,
            run_id=run_id,
            api_key=api_key,
            api_secret=api_secret,
            is_cancelled=is_cancelled,
            progress_callback=progress_callback,
        )

    async def run_backtest_replay(
        self,
        *,
        db: Session,
        schema: str,
        robot_id: int,
        user_id: int,
        token_id: int,
        token: str,
        config: Dict[str, Any],
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        allowed_figis_by_date: Dict[str, List[str]],
        initial_capital: float,
        log_func=None,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
        cancel_check_sync: Optional[Callable[[], bool]] = None,
        progress_callback_sync: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResult:
        br, maker_fee, taker_fee, ndfl = resolve_backtest_sim_rates(config)
        sim = SimBacktestBrokerFacade(
            initial_capital=float(initial_capital),
            candles_by_figi=candles_by_figi,
            commission_rate=br,
            maker_fee_rate=maker_fee,
            taker_fee_rate=taker_fee,
            ndfl_rate=ndfl,
            backtest_fee_model=resolve_backtest_fee_model(config),
            robot_config=config,
        )
        session = create_trading_session(
            ExecutionMode.BACKTEST,
            db=db,
            schema=schema,
            robot_id=robot_id,
            user_id=user_id,
            token_id=token_id,
            token=token or "",
            config=config,
            log_func=log_func,
            sim_broker=sim,
            allowed_figis_by_date=allowed_figis_by_date,
        )
        session.running = True
        strategy = str(config.get("strategy") or getattr(session, "strategy_name", "") or "")
        logger.info(
            "TradingOrchestrator.run_backtest_replay robot_id=%s strategy=%s tickers=%s",
            robot_id,
            strategy,
            len(candles_by_figi),
        )
        return await session.run_history_replay(
            candles_by_figi=candles_by_figi,
            cancel_check=cancel_check,
            cancel_check_sync=cancel_check_sync,
            progress_callback_sync=progress_callback_sync,
        )

    async def run_backtest_quick(
        self,
        *,
        db: Session,
        schema: str,
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        strategy_name: str,
        strategy_params: Dict[str, Any],
        risk_params: Dict[str, Any],
        initial_capital: float = 1_000_000.0,
        robot_config: Optional[Dict[str, Any]] = None,
        allowed_figis_by_date: Optional[Dict[str, List[str]]] = None,
        user_id: int = 0,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
        cancel_check_sync: Optional[Callable[[], bool]] = None,
        progress_callback_sync: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResult:
        """
        Синхронный/лёгкий бэктест без robot row (market API, smoke).

        Не использует `engine.run_backtest_simulation`.
        """
        sp = dict(strategy_params or {})
        sp["figis"] = list(candles_by_figi.keys())
        config = dict(robot_config or {})
        config.setdefault("strategy", strategy_name)
        config["strategy_params"] = {**dict(config.get("strategy_params") or {}), **sp}
        config["risk"] = {**dict(config.get("risk") or {}), **dict(risk_params or {})}
        allowed = allowed_figis_by_date or build_allowed_figis_by_date(candles_by_figi)
        return await self.run_backtest_replay(
            db=db,
            schema=schema,
            robot_id=0,
            user_id=user_id,
            token_id=0,
            token="",
            config=config,
            candles_by_figi=candles_by_figi,
            allowed_figis_by_date=allowed,
            initial_capital=initial_capital,
            cancel_check=cancel_check,
            cancel_check_sync=cancel_check_sync,
            progress_callback_sync=progress_callback_sync,
        )


def get_trading_orchestrator() -> TradingOrchestrator:
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = TradingOrchestrator()
    return _default_orchestrator


__all__ = [
    "TradingOrchestrator",
    "build_allowed_figis_by_date",
    "build_allowed_symbols_by_date",
    "get_trading_orchestrator",
]
