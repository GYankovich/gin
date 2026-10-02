"""Tests for historical DMS filter adapter."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.universe.historical_dms import apply_dms_filters_historical


def test_apply_dms_filters_historical_accepts_when_evaluator_ok():
    rows = [{"ticker": "SBER", "last_price": 100.0, "value_today": 1e9}]
    with patch(
        "app.modules.robots_v2.universe.historical_dms.dms_service._evaluate_pipeline_row",
        return_value={"accepted": True},
    ):
        kept, rejected = apply_dms_filters_historical(
            rows,
            dms_filters=[{"type": "volume", "min": 1}],
            mode="ALL",
        )
    assert [r["ticker"] for r in kept] == ["SBER"]
    assert rejected == []


def test_apply_dms_filters_historical_rejects():
    rows = [{"ticker": "TRASH", "last_price": 1.0, "value_today": 0}]
    with patch(
        "app.modules.robots_v2.universe.historical_dms.dms_service._evaluate_pipeline_row",
        return_value={"accepted": False, "reason": "volume"},
    ):
        kept, rejected = apply_dms_filters_historical(
            rows,
            dms_filters=[{"type": "volume", "min": 1}],
            mode="ALL",
        )
    assert kept == []
    assert rejected[0]["ticker"] == "TRASH"
    assert rejected[0]["reason"] == "volume"


def test_empty_filters_passthrough():
    rows = [{"ticker": "A"}]
    kept, rejected = apply_dms_filters_historical(rows, dms_filters=[], mode="ALL")
    assert kept == rows
    assert rejected == []
