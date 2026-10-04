"""SPEC-04 P0: monitor day-summary balance on GET /status."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.session import TradingSessionV2
from app.modules.robots_v2.engine.types import SessionState, SessionStatus
from app.modules.robots_v2.schemas import RobotV2Response, RobotV2StatusResponse
from app.modules.robots_v2.service import RobotsV2Service, _IDLE_BROKER_CACHE


def _robot(
    *,
    robot_id: int = 13,
    mode: str = "paper",
    token_id: int | None = 1,
    metadata: dict | None = None,
    status: int = 1,
) -> RobotV2Response:
    return RobotV2Response(
        id=robot_id,
        name="BalanceBot",
        type=2,
        tokenId=token_id,
        status=status,
        configVersion=4,
        config={"core": {"mode": mode}},
        metadata=metadata or {},
        createdAt=datetime.now(timezone.utc),
    )


def test_idle_paper_exposes_last_virtual_capital_as_balance():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(
        metadata={
            "lastVirtualCapital": 1_250_000.5,
            "lastPaperEquityAt": "2026-10-05T10:00:00+00:00",
        },
    )

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.status.return_value = None
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["mode"] == "paper"
    assert payload["cash"] == 1_250_000.5
    assert payload["equity"] == 1_250_000.5
    assert payload["lastVirtualCapital"] == 1_250_000.5
    assert payload["balanceSource"] == "paper_last"
    assert payload["balanceAsOf"] == "2026-10-05T10:00:00+00:00"
    assert payload["sessionState"] is None
    validated = RobotV2StatusResponse.model_validate(payload)
    assert validated.balance_source == "paper_last"
    assert validated.last_virtual_capital == 1_250_000.5


def test_idle_paper_without_capital_keeps_null_balances():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(metadata={})

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.status.return_value = None
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["cash"] is None
    assert payload["equity"] is None
    assert payload["lastVirtualCapital"] is None
    assert payload["balanceSource"] is None
    assert payload["balanceAsOf"] is None


def test_idle_paper_zero_capital_treated_as_missing():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(metadata={"lastVirtualCapital": 0})

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.status.return_value = None
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["cash"] is None
    assert payload["equity"] is None
    assert payload["balanceSource"] is None


def test_idle_live_broker_snap_sets_balance_source_broker():
    import time

    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(mode="live", token_id=9)
    _IDLE_BROKER_CACHE.clear()
    _IDLE_BROKER_CACHE[13] = (
        time.monotonic(),
        {
            "positions": [{"ticker": "SBER", "quantity": 1}],
            "cash": 50_000.0,
            "equity": 75_000.0,
            "universe": ["SBER"],
            "updatedAt": "2026-10-05T11:00:00+00:00",
        },
    )

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm, patch(
        "app.modules.robots_v2.engine.broker_positions.open_tickers_from_audit_fills",
        return_value={},
    ):
        sm.status.return_value = None
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["cash"] == 50_000.0
    assert payload["equity"] == 75_000.0
    assert payload["balanceSource"] == "broker"
    assert payload["balanceAsOf"] == "2026-10-05T11:00:00+00:00"
    assert payload["positionsSource"] == "broker"
    _IDLE_BROKER_CACHE.clear()


def test_idle_live_broker_fail_keeps_null_balance_source():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(mode="live", token_id=9)
    _IDLE_BROKER_CACHE.clear()

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm, patch(
        "app.modules.robots_v2.engine.broker_positions.open_tickers_from_audit_fills",
        return_value={},
    ), patch.object(
        service,
        "_fetch_idle_broker_positions",
        new=AsyncMock(return_value=None),
    ):
        sm.status.return_value = None
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["cash"] is None
    assert payload["equity"] is None
    assert payload["balanceSource"] is None
    assert payload["positionsSource"] is None


def test_active_session_balance_source_session():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _robot(metadata={"lastVirtualCapital": 900_000})
    snap = SessionStatus(
        robot_id=13,
        session_state=SessionState.RUNNING,
        mode="paper",
        cycle_number=3,
        equity=910_000.0,
        cash=880_000.0,
        last_prices_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
    )

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.status.return_value = snap
        payload = asyncio.run(service.get_status(db, user_id=7, robot_id=13))

    assert payload["equity"] == 910_000.0
    assert payload["cash"] == 880_000.0
    assert payload["balanceSource"] == "session"
    assert payload["positionsSource"] == "session"
    assert payload["lastVirtualCapital"] == 900_000.0
    assert payload["balanceAsOf"] == "2026-10-05T12:00:00+00:00"


def test_persist_paper_last_virtual_capital_writes_metadata():
    import json

    session = TradingSessionV2(
        robot_id=55,
        user_id=1,
        token_id=1,
        config={"core": {"mode": "paper"}},
        virtual_capital=100_000,
    )
    session.ledger = PaperLedger(cash=95_000.0)
    session.last_prices = {}

    captured: dict = {}

    def _execute(stmt, params=None):
        sql = str(stmt)
        if "SELECT metadata" in sql:
            return SimpleNamespace(first=lambda: ({"sessionDesired": "stopped"},))
        if "UPDATE" in sql:
            captured.update(params or {})
            return MagicMock()
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = _execute

    with patch(
        "app.modules.robots_v2.engine.session.SessionLocal",
        return_value=db,
    ), patch("app.core.config.settings") as settings_mock:
        settings_mock.DB_SCHEMA = "public"
        session._persist_paper_last_virtual_capital()

    assert captured.get("rid") == 55
    meta_raw = captured.get("metadata")
    assert meta_raw is not None
    meta = json.loads(meta_raw)
    assert meta["lastVirtualCapital"] == 95_000.0
    assert "lastPaperEquityAt" in meta
    db.commit.assert_called()


def test_persist_paper_last_virtual_capital_skips_live():
    session = TradingSessionV2(
        robot_id=56,
        user_id=1,
        token_id=1,
        config={"core": {"mode": "live"}},
        virtual_capital=0,
    )
    session.ledger = PaperLedger(cash=10_000.0)

    with patch(
        "app.modules.robots_v2.engine.session.SessionLocal",
    ) as session_local:
        session._persist_paper_last_virtual_capital()
    session_local.assert_not_called()
