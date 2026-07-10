from __future__ import annotations

import asyncio
import os
from datetime import date

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.robots.backtest_progress import phase_label_ru
from app.modules.robots.trading.backtest import crypto_screening_prefetch as csp


def test_phase_label_crypto_prefetch():
    assert phase_label_ru("prefetching_crypto_market") == "Кэш ByBit (D1 + funding)"


def test_schedule_crypto_screening_prefetch_enqueues_job():
    db = MagicMock()
    db.get_bind.return_value = MagicMock()
    enqueue = MagicMock(return_value="job-uuid")

    async def _run():
        with patch(
            "app.core.background_jobs.repository.enqueue_background_job",
            enqueue,
        ), patch(
            "app.modules.robots.trading.backtest.crypto_screening_prefetch.estimate_crypto_prefetch_units",
            AsyncMock(return_value=200),
        ), patch(
            "app.modules.robots.backtest_progress.persist_backtest_progress",
        ):
            return await csp.schedule_crypto_screening_prefetch(
                db,
                run_id=42,
                user_id=7,
                body={"strategy": "grain_seed"},
                trade_dates=[date(2024, 1, 1)],
                config={"broker_type": "bybit"},
                progress_bind=MagicMock(),
            )

    scheduled = asyncio.run(_run())
    assert scheduled is True
    enqueue.assert_called_once()
    call_kw = enqueue.call_args.kwargs
    assert call_kw["job_type"] == "crypto_screening_prefetch"
    assert call_kw["idempotency_key"] == "crypto_screening_prefetch:42"
    db.commit.assert_called()


def test_resolve_crypto_screening_symbols_prefers_live_universe(monkeypatch):
    from app.modules.robots.trading.data.providers import bybit_market

    async def _fake_api(**_kwargs):
        return [
            {"symbol": "BTCUSDT", "contract_type": "LinearPerpetual"},
            {"symbol": "ETHUSDT", "contract_type": "LinearPerpetual"},
            {"symbol": "BTCUSDT-10JUL26", "contract_type": "LinearFutures"},
        ]

    monkeypatch.setattr(
        "app.modules.bybit.instruments.list_instruments",
        _fake_api,
    )
    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.historical_liquidity.list_bybit_symbols_from_cache",
        lambda _db: ["OLDUSDT"],
    )

    async def _run():
        return await bybit_market.resolve_crypto_screening_symbols(
            MagicMock(),
            config={"bybit": {"instrument_category": "linear"}},
            prefer_live_universe=True,
        )

    symbols = asyncio.run(_run())
    assert symbols == ["BTCUSDT", "ETHUSDT"]


def test_resolve_crypto_screening_symbols_api_failure_uses_cache(monkeypatch):
    from app.modules.robots.trading.data.providers import bybit_market

    async def _fail_api(**_kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(
        "app.modules.bybit.instruments.list_instruments",
        _fail_api,
    )
    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.historical_liquidity.list_bybit_symbols_from_cache",
        lambda _db: ["CACHEUSDT"],
    )

    async def _run():
        return await bybit_market.resolve_crypto_screening_symbols(
            MagicMock(),
            config={"bybit": {"instrument_category": "linear"}},
            prefer_live_universe=True,
        )

    symbols = asyncio.run(_run())
    assert symbols == ["CACHEUSDT"]
