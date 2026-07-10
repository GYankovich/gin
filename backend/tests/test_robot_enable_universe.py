"""Universe bootstrap when enabling trading robots."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.modules.robots.service import RobotService


def test_enable_crypto_auto_runs_screening_not_dms():
    svc = RobotService()
    cfg = {
        "broker_type": "bybit",
        "schema_profile": "type2_bybit",
        "universe_mode": "auto",
        "allowed_symbols": [],
        "crypto_universe": {"enabled": True},
    }
    with patch.object(
        svc,
        "run_crypto_screening_job",
        new=AsyncMock(return_value={"symbols": ["BTCUSDT"], "accepted": 1, "scanned": 10}),
    ) as screening, patch.object(
        svc,
        "sync_live_universe_from_pipeline",
        new=AsyncMock(),
    ) as dms_sync:
        asyncio.run(svc._ensure_trading_universe_on_enable(None, robot_id=24, user_id=1, cfg=cfg))
        screening.assert_awaited_once()
        dms_sync.assert_not_awaited()


def test_enable_crypto_with_symbols_skips_screening():
    svc = RobotService()
    cfg = {
        "broker_type": "bybit",
        "universe_mode": "fixed",
        "allowed_symbols": ["ETHUSDT"],
    }
    with patch.object(svc, "run_crypto_screening_job", new=AsyncMock()) as screening:
        asyncio.run(svc._ensure_trading_universe_on_enable(None, robot_id=24, user_id=1, cfg=cfg))
        screening.assert_not_awaited()


def test_enable_crypto_fixed_without_symbols_rejected():
    svc = RobotService()
    cfg = {
        "broker_type": "bybit",
        "universe_mode": "fixed",
        "allowed_symbols": [],
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc._ensure_trading_universe_on_enable(None, robot_id=24, user_id=1, cfg=cfg))
    assert exc.value.status_code == 400
    assert "allowed_symbols" in str(exc.value.detail)
