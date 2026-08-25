"""Universe resolve retry during trading hours."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.session import TradingSessionV2
from app.modules.robots_v2.engine.types import SessionState


def _screener_config() -> dict:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "mode": "paper",
            "instrumentType": "stock",
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:40",
                "pollInterval": "5m",
            },
        },
        "universe": {
            "mode": "screener",
            "screener": {"preset": "volatile"},
            "maxAssets": 20,
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0, "breakoutLookback": 20},
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
        },
    }


def test_resolve_universe_retries_until_screener_returns_symbols():
    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)

    calls = {"n": 0}

    async def _resolve_once_side_effect():
        calls["n"] += 1
        if calls["n"] < 3:
            return [], {}
        return ["SBER", "GAZP"], {"SBER": "FIGI_SBER", "GAZP": "FIGI_GAZP"}

    async def _run() -> tuple[bool, dict[str, str]]:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(side_effect=_resolve_once_side_effect),
        ), patch.object(
            session,
            "_fallback_universe_tickers",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            session,
            "_sleep_until_universe_retry",
            new=AsyncMock(return_value=True),
        ), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=True,
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ), patch.object(session, "_set_stage", new=AsyncMock()):
            return await session._resolve_universe_for_session()

    ok, resolved_map = asyncio.run(_run())
    assert ok is True
    assert session.universe == ["SBER", "GAZP"]
    assert session._universe_resolve_pending is False
    assert calls["n"] == 3
    assert resolved_map["SBER"] == "FIGI_SBER"


def test_resolve_universe_uses_fallback_and_keeps_pending():
    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)

    async def _run() -> tuple[bool, dict[str, str]]:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(return_value=([], {})),
        ), patch.object(
            session,
            "_fallback_universe_tickers",
            new=AsyncMock(return_value=["X5", "ROSN"]),
        ), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=True,
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            return await session._resolve_universe_for_session()

    ok, _ = asyncio.run(_run())
    assert ok is True
    assert session.universe == ["X5", "ROSN"]
    assert session._universe_resolve_pending is True
    assert session._universe_using_fallback is True


def test_maybe_refresh_universe_clears_pending_when_screener_recovers():
    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.universe = ["X5", "ROSN"]
    session._universe_resolve_pending = True
    session._universe_using_fallback = True
    session._universe_last_retry_at = 0.0
    session.ledger = MagicMock(positions={"X5": MagicMock()})
    session._ensure_instrument_map = AsyncMock()

    async def _run() -> None:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(return_value=(["SBER", "GAZP", "LKOH"], {
                "SBER": "FIGI_SBER",
                "GAZP": "FIGI_GAZP",
                "LKOH": "FIGI_LKOH",
            })),
        ), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=True,
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            await session._maybe_refresh_universe()

    asyncio.run(_run())
    assert session._universe_resolve_pending is False
    assert session._universe_using_fallback is False
    assert "X5" in session.universe
    assert "SBER" in session.universe
    assert "GAZP" in session.universe


def test_maybe_refresh_universe_on_new_trade_date():
    from datetime import date

    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.universe = ["SBER"]
    session._universe_resolve_pending = False
    session._universe_trade_date = date(2026, 8, 19)
    session._universe_last_retry_at = 0.0
    session._ensure_instrument_map = AsyncMock()
    session.ledger = MagicMock(positions={})

    async def _run() -> None:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(return_value=(["OZON", "VKUS"], {"OZON": "F1", "VKUS": "F2"})),
        ), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=True,
        ), patch(
            "app.modules.robots_v2.engine.session.trade_date_msk",
            return_value=date(2026, 8, 21),
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            await session._maybe_refresh_universe()

    asyncio.run(_run())
    assert "OZON" in session.universe
    assert "VKUS" in session.universe
    assert "SBER" not in session.universe
    assert session._universe_trade_date == date(2026, 8, 21)


def test_maybe_refresh_universe_skips_same_trade_date():
    from datetime import date

    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.universe = ["SBER"]
    session._universe_resolve_pending = False
    session._universe_trade_date = date(2026, 8, 21)
    session._universe_last_retry_at = 0.0
    resolve = AsyncMock(return_value=(["OZON"], {"OZON": "F1"}))

    async def _run() -> None:
        with patch.object(session, "_resolve_universe_once", new=resolve), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=True,
        ), patch(
            "app.modules.robots_v2.engine.session.trade_date_msk",
            return_value=date(2026, 8, 21),
        ):
            await session._maybe_refresh_universe()

    asyncio.run(_run())
    resolve.assert_not_called()
    assert session.universe == ["SBER"]


def test_force_refresh_universe_rebuilds_candidates():
    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.state = SessionState.RUNNING
    session.universe = ["SBER"]
    session._ensure_instrument_map = AsyncMock()
    session.ledger = MagicMock(positions={})

    async def _run() -> dict:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(return_value=(["OZON"], {"OZON": "F1"})),
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            return await session.refresh_universe(reason="force")

    payload = asyncio.run(_run())
    assert payload["reason"] == "force"
    assert payload["universe"] == ["OZON"]
    assert payload["added"] == ["OZON"]
    assert payload["removed"] == ["SBER"]
    assert payload["keptPrevious"] is False


def test_force_refresh_universe_rejects_fixed_mode():
    cfg = _screener_config()
    cfg["universe"] = {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 5}
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.state = SessionState.RUNNING

    async def _run() -> None:
        await session.refresh_universe(reason="force")

    try:
        asyncio.run(_run())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert str(exc) == "UNIVERSE_REFRESH_UNSUPPORTED"


def test_resolve_universe_fails_outside_session_without_fallback():
    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=cfg,
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)

    async def _run() -> tuple[bool, dict[str, str]]:
        with patch.object(
            session,
            "_resolve_universe_once",
            new=AsyncMock(return_value=([], {})),
        ), patch.object(
            session,
            "_fallback_universe_tickers",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.modules.robots_v2.engine.session.is_within_trading_session",
            return_value=False,
        ), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            return await session._resolve_universe_for_session()

    ok, _ = asyncio.run(_run())
    assert ok is False
    assert session.state == SessionState.ERROR


def test_commit_universe_syncs_figi_into_execution():
    from app.modules.robots_v2.engine.execution import ExecutionService
    from app.modules.robots_v2.engine.paper_ledger import PaperLedger

    cfg = _screener_config()
    session = TradingSessionV2(
        robot_id=3,
        user_id=1,
        token_id=27,
        config=cfg,
        virtual_capital=10_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)
    session.universe = ["NVTK"]
    session._instrument_map = {"NVTK": "BBG00475KKY8"}
    session.ledger = PaperLedger(cash=5_000, commission_rate=0.0)
    session.execution = ExecutionService(
        mode="live",
        robot_id=3,
        ledger=session.ledger,
        instrument_map=dict(session._instrument_map),
    )
    session._ensure_instrument_map = AsyncMock()

    async def _run() -> None:
        with patch.object(session, "_resync_price_subscriptions", new=AsyncMock()), patch(
            "app.modules.robots_v2.engine.session.event_bus.publish",
            new=AsyncMock(),
        ):
            await session._commit_universe(
                ["NVTK", "GMKN"],
                {"NVTK": "BBG00475KKY8", "GMKN": "BBG004S68614"},
                "pending",
            )

    asyncio.run(_run())
    assert session.execution._instrument_id("NVTK") == "BBG00475KKY8"
    assert session.execution._instrument_id("GMKN") == "BBG004S68614"
