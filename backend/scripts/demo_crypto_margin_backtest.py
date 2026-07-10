#!/usr/bin/env python3
"""
Демо crypto backtest с isolated margin (leverage 10x) без PostgreSQL.

Генерирует синтетические 1h-свечи BTCUSDT: откат → вход → падение → liquidation.
Печатает margin_summary, fee_summary и сделки.

  set PYTHONPATH=backend
  python backend/scripts/demo_crypto_margin_backtest.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("demo_margin")


def _candle(time_iso: str, close: float, volume: int = 1_000_000) -> Dict[str, Any]:
    units = int(close)
    nano = int(round((close - units) * 1_000_000_000))
    return {
        "time": time_iso,
        "open": {"units": units, "nano": 0},
        "high": {"units": units, "nano": 0},
        "low": {"units": units, "nano": 0},
        "close": {"units": units, "nano": nano},
        "volume": volume,
    }


def build_synthetic_btcusdt_series() -> List[Dict[str, Any]]:
    """Плато ~100k → резкий откат (BUY) → обвал ниже liq (~90.5k при 10x)."""
    start = datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc)  # 13:00 MSK — в торговом окне
    prices: List[float] = []
    for i in range(30):
        prices.append(100_000.0 + (i % 5) * 20.0)
    for p in (97_000.0, 95_500.0, 94_000.0, 92_500.0):
        prices.append(p)
    prices.extend([96_000.0, 97_500.0, 93_000.0, 89_000.0, 87_000.0])

    return [
        _candle((start + timedelta(hours=i)).isoformat(), px)
        for i, px in enumerate(prices)
    ]


async def _bootstrap_from_sim_broker(
    robot_id: int,
    broker,
    figis: List[str],
    strategy_params: Dict,
    log_func=None,
    **_,
) -> None:
    from app.modules.robots.trading.cache import get_candles_cache
    from app.modules.robots.trading.indicators.service import indicator_service

    interval = strategy_params.get("interval") or "1h"
    days = indicator_service._resolve_request_days(strategy_params, interval)
    cache = get_candles_cache()
    ns = broker.cache_namespace
    for figi in figis:
        series = list(getattr(broker, "candles_by_figi", {}).get(figi) or [])
        key = indicator_service._cache_figi_key(ns, figi)
        cache.set(key, interval, days, series)
    if log_func:
        log_func(f"📊 [Свечи] Demo bootstrap: {len(figis)} symbol(s), {len(series)} bars cached")


async def _on_closed_candle_no_db(
    robot_id: int,
    broker,
    figi: str,
    candle: Dict,
    strategy_params: Dict,
    **_,
) -> None:
    from app.modules.robots.trading.cache import get_candles_cache
    from app.modules.robots.trading.indicators.service import BOOTSTRAP_INTERVAL, indicator_service

    interval = strategy_params.get("interval") or BOOTSTRAP_INTERVAL
    days = indicator_service._resolve_request_days(strategy_params, interval)
    cache = get_candles_cache()
    key = indicator_service._cache_figi_key(broker.cache_namespace, figi)
    if not cache.get(key, interval, days):
        cache.set(key, interval, days, [candle])
    else:
        cache.append_candle(key, interval, days, candle) or cache.set(key, interval, days, [candle])


async def main() -> int:
    from unittest.mock import MagicMock, patch

    from app.core.config import settings
    from app.modules.robots.trading.brokers.margin import liquidation_price_long
    from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
    from app.modules.robots.trading.contracts import ExecutionMode
    from app.modules.robots.trading.costs import resolve_backtest_fee_model, resolve_backtest_sim_rates
    from app.modules.robots.trading.indicators import service as ind_svc
    from app.modules.robots.trading.runtime.orchestrator import build_allowed_figis_by_date
    from app.modules.robots.trading.session_factory import create_trading_session

    symbol = "BTCUSDT"
    candles = build_synthetic_btcusdt_series()
    candles_by_figi = {symbol: candles}
    allowed = build_allowed_figis_by_date(candles_by_figi)

    leverage = 10.0
    mmr = 0.005
    entry_hint = 100_000.0
    liq_hint = liquidation_price_long(entry_hint, leverage, mmr)

    config: Dict[str, Any] = {
        "broker_type": "bybit",
        "allowed_symbols": [symbol],
        "strategy": "reversion_to_ma",
        "strategy_params": {
            "figis": [symbol],
            "interval": "1h",
            "ma_period": 10,
            "rsi_period": 14,
            "deviation_pct": 1.5,
            "rsi_oversold": 35,
            "rsi_overbought": 70,
            "use_volume_filter": False,
        },
        "bybit": {
            "testnet": True,
            "instrument_category": "linear",
            "leverage": leverage,
            "maintenance_margin_rate": mmr,
        },
        "costs": {
            "funding_rate_enabled": False,
            "backtest_execution": "market_taker",
            "maker_fee_pct": 0.02,
            "taker_fee_pct": 0.055,
        },
        "risk": {
            "max_position_percent": 40,
            "max_daily_loss": 100,
            "stop_loss_percent": 50,
            "max_leverage": 10,
            "min_seconds_between_trades": 0,
            "trading_hours_start": "00:00 MSK",
            "trading_hours_end": "23:59 MSK",
            "allowed_weekdays": 127,
            "min_trade_amount_rub": 1,
        },
    }

    initial_capital = 10_000.0
    br, maker_fee, taker_fee, ndfl = resolve_backtest_sim_rates(config)
    sim = SimBacktestBrokerFacade(
        initial_capital=initial_capital,
        candles_by_figi=candles_by_figi,
        commission_rate=br,
        maker_fee_rate=maker_fee,
        taker_fee_rate=taker_fee,
        ndfl_rate=ndfl,
        backtest_fee_model=resolve_backtest_fee_model(config),
        robot_config=config,
    )

    mock_db = MagicMock()
    with patch("app.modules.robots.trading.session.SessionLocal", return_value=mock_db):
        session = create_trading_session(
            ExecutionMode.BACKTEST,
            db=mock_db,
            schema=settings.DB_SCHEMA,
            robot_id=0,
            user_id=0,
            token_id=0,
            token="demo",
            config=config,
            log_func=lambda msg: None,
            sim_broker=sim,
            allowed_figis_by_date=allowed,
        )

    async def _noop_refresh() -> None:
        return None

    session.refresh_config = _noop_refresh  # type: ignore[method-assign]

    print("=" * 60)
    print("CRYPTO MARGIN BACKTEST DEMO")
    print(f"  symbol={symbol}  leverage={leverage}x  MMR={mmr*100:.2f}%")
    print(f"  candles={len(candles)}  capital={initial_capital:,.0f} USDT")
    print(f"  theoretical liq @ entry {entry_hint:,.0f}: {liq_hint:,.2f}")
    print("=" * 60)

    with (
        patch.object(ind_svc.indicator_service, "bootstrap_candles_at_startup", _bootstrap_from_sim_broker),
        patch.object(ind_svc.indicator_service, "on_closed_candle", _on_closed_candle_no_db),
    ):
        result = await session.run_history_replay(candles_by_figi=candles_by_figi)

    print("\n--- RESULT ---")
    print(f"return_pct:        {result.total_return_percent:.4f}%")
    print(f"final_equity:      {result.final_equity:,.2f}")
    print(f"max_drawdown_pct:  {result.max_drawdown_percent}")
    print(f"trades:            {len(result.trades)}")

    print("\n--- MARGIN SUMMARY ---")
    print(json.dumps(result.margin_summary, indent=2, ensure_ascii=False))

    print("\n--- FEE SUMMARY ---")
    print(json.dumps(result.fee_summary, indent=2, ensure_ascii=False))

    liq_trades = [t for t in result.trades if t.get("liquidation")]
    if liq_trades:
        print(f"\n--- LIQUIDATIONS ({len(liq_trades)}) ---")
        for t in liq_trades:
            print(
                f"  {t.get('bar_time')} {t.get('figi')} qty={t.get('quantity')} "
                f"px={t.get('price')}"
            )

    print("\n--- TRADE LOG ---")
    for t in result.trades:
        print(
            f"  {str(t.get('bar_time',''))[:19]} {t.get('side'):4} {t.get('figi')} "
            f"qty={t.get('quantity')} px={t.get('price')} "
            f"fee={t.get('commission')} liq={t.get('liquidation')}"
        )

    ms = result.margin_summary or {}
    if ms.get("enabled") and result.trades:
        print("\nOK: margin model active in full session replay.")
        return 0
    print("\nFAIL: expected margin-enabled backtest with trades", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
