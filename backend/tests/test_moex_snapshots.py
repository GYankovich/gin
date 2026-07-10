"""MOEX snapshots provider — facade integration."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.modules.robots.trading.data import get_market_data_facade


def test_ensure_snapshot_day_cache_hit():
    import asyncio

    db = MagicMock()
    db.execute.return_value.first.return_value = (42, 200)

    facade = get_market_data_facade()
    sid = asyncio.run(
        facade.ensure_snapshot_day(
            db,
            day=date(2024, 6, 3),
            board="TQBR",
            run_id=None,
        )
    )
    assert sid == 42
