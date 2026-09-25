"""Tests for OsEngine live ingest service."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.modules.osengine.ingest import ingest_candles, ingest_depth, ingest_ticks, read_live_status
from app.modules.osengine.schemas import (
    DepthLevel,
    IngestCandleItem,
    IngestDepthItem,
    IngestTickItem,
)


def test_ingest_candles_writes_and_heartbeat():
    executed = []

    def _execute(sql, params=None):
        executed.append((str(sql), params))
        return MagicMock(rowcount=1)

    db = MagicMock()
    db.execute.side_effect = _execute
    n = ingest_candles(
        db,
        [
            IngestCandleItem(
                ticker="SBER",
                interval="I1",
                time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
            )
        ],
        subscribed_instruments=3,
    )
    assert n == 1
    assert any("candles_cache" in s for s, _ in executed)
    assert any("osengine_ingest_heartbeat" in s for s, _ in executed)


def test_ingest_ticks_dedup_conflict():
    executed = []

    def _execute(sql, params=None):
        executed.append(params)
        return MagicMock(rowcount=1)

    db = MagicMock()
    db.execute.side_effect = _execute
    n = ingest_ticks(
        db,
        [
            IngestTickItem(
                ticker="GAZP",
                time=datetime(2024, 6, 1, 10, 0, 1, tzinfo=timezone.utc),
                price=150.0,
                quantity=2.0,
                side="buy",
                trade_id="t1",
            )
        ],
    )
    assert n == 1
    assert executed[0]["trade_id"] == "t1"
    assert executed[0]["ticker"] == "GAZP"


def test_ingest_depth_upsert():
    executed = []

    def _execute(sql, params=None):
        executed.append(params)
        return MagicMock(rowcount=1)

    db = MagicMock()
    db.execute.side_effect = _execute
    n = ingest_depth(
        db,
        [
            IngestDepthItem(
                ticker="SBER",
                bids=[DepthLevel(price=100.0, quantity=1.0)],
                asks=[DepthLevel(price=101.0, quantity=2.0)],
                time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            )
        ],
        subscribed_instruments=5,
    )
    assert n == 1
    assert '"100.0"' in executed[0]["bids"] or "100" in executed[0]["bids"]


def test_read_live_status_from_heartbeat():
    now = datetime.now(timezone.utc)

    class _Row(dict):
        def __getitem__(self, item):
            return dict.__getitem__(self, item)

    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [
        _Row(
            stream="ticks",
            last_at=now,
            subscribed_instruments=7,
            detail=None,
            updated_at=now,
        )
    ]
    st = read_live_status(db)
    assert st.bridge_connected is True
    assert st.subscribed_instruments == 7
    assert st.last_tick_at is not None
