"""Tests for broker position mapping / audit open-ticker hints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.robots_v2.engine.broker_positions import (
    apply_opened_at_hints,
    map_broker_meta_to_positions,
    open_tickers_from_audit_fills,
    paper_positions_to_rows,
)
from app.modules.robots_v2.engine.paper_ledger import PaperPosition


def test_map_broker_meta_includes_extra_tickers_outside_universe():
    meta = {
        "BBG001": {"qty": 7, "avg_price": 400.0, "mark_price": 401.0},
        "BBG002": {"qty": 1, "avg_price": 100.0, "mark_price": 99.0},
    }
    instrument_map = {"SMLT": "BBG001", "SBER": "BBG002"}
    pos = map_broker_meta_to_positions(
        meta,
        instrument_map=instrument_map,
        universe=["SBER"],
        extra_tickers={"SMLT"},
    )
    assert set(pos) == {"SMLT", "SBER"}
    assert pos["SMLT"].quantity == 7
    assert pos["SMLT"].avg_entry_price == 400.0


def test_map_broker_meta_filters_unknown_outside_universe():
    meta = {"BBG999": {"qty": 3, "avg_price": 10.0, "mark_price": 10.0}}
    pos = map_broker_meta_to_positions(
        meta,
        instrument_map={"SBER": "BBG002"},
        universe=["SBER"],
        extra_tickers=None,
    )
    assert pos == {}


def test_paper_positions_to_rows_source():
    p = PaperPosition(ticker="GAZP", side="LONG", quantity=10, avg_entry_price=150.0)
    rows = paper_positions_to_rows({"GAZP": p}, prices={"GAZP": 151.0}, source="broker")
    assert rows[0]["source"] == "broker"
    assert rows[0]["current_price"] == 151.0
    assert rows[0]["entry_price"] == 150.0


def test_apply_opened_at_hints():
    p = PaperPosition(ticker="SMLT", side="LONG", quantity=1, avg_entry_price=400.0)
    hint = datetime(2026, 8, 13, 13, 14, 32, tzinfo=timezone.utc)
    apply_opened_at_hints({"SMLT": p}, {"SMLT": hint})
    assert p.opened_at == hint


def test_open_tickers_from_audit_fills_fifo():
    db = MagicMock()
    rows = [
        SimpleNamespace(ticker="SMLT", side="BUY", quantity=7, filled_at=datetime(2026, 8, 13, 16, 14, tzinfo=timezone.utc)),
        SimpleNamespace(ticker="PLZL", side="BUY", quantity=2, filled_at=datetime(2026, 8, 13, 16, 14, tzinfo=timezone.utc)),
        SimpleNamespace(ticker="PLZL", side="SELL", quantity=2, filled_at=datetime(2026, 8, 13, 16, 15, tzinfo=timezone.utc)),
    ]
    db.execute.return_value.fetchall.return_value = rows
    open_map = open_tickers_from_audit_fills(db, robot_id=1, schema="public")
    assert set(open_map) == {"SMLT"}
    assert open_map["SMLT"] is not None
