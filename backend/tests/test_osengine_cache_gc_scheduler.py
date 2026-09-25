"""OsEngine cache GC scheduler tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.modules.osengine.scheduler import (
    run_osengine_cache_gc_once,
    start_osengine_cache_gc_scheduler,
    stop_osengine_cache_gc_scheduler,
)
from app.modules.osengine.stats import CacheGcStats


def test_run_osengine_cache_gc_once_commits():
    db = MagicMock()
    facade = MagicMock()
    facade.market = "osengine"
    facade.gc_cache.return_value = CacheGcStats(expired_leases=2, deleted_candle_rows=10)

    with patch("app.modules.osengine.scheduler.SessionLocal", return_value=db), patch(
        "app.modules.osengine.get_osengine_facade", return_value=facade
    ):
        result = run_osengine_cache_gc_once()

    facade.gc_cache.assert_called_once_with(db)
    db.commit.assert_called_once()
    db.close.assert_called_once()
    assert result["expired_leases"] == 2
    assert result["deleted_candle_rows"] == 10


def test_run_osengine_cache_gc_once_rolls_back_on_error():
    db = MagicMock()
    facade = MagicMock()
    facade.gc_cache.side_effect = RuntimeError("boom")

    with patch("app.modules.osengine.scheduler.SessionLocal", return_value=db), patch(
        "app.modules.osengine.get_osengine_facade", return_value=facade
    ):
        try:
            run_osengine_cache_gc_once()
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_scheduler_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr(
        "app.modules.osengine.scheduler.settings.OSENGINE_CACHE_GC_ENABLED",
        False,
    )

    async def _run():
        await start_osengine_cache_gc_scheduler()
        await stop_osengine_cache_gc_scheduler()

    asyncio.run(_run())
