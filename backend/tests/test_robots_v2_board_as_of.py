"""Causal OsEngine board membership for backtest screener."""

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

import asyncio

from app.modules.robots_v2.universe.board_as_of import (
    fetch_moex_board_secids_on_day,
    list_moex_board_tickers_as_of,
)


def test_fetch_board_secids_uses_cache_not_iss():
    db = MagicMock()
    with patch(
        "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_cache",
        return_value=["SBER", "GAZP"],
    ) as cache_fn, patch(
        "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_snapshot",
        return_value=[],
    ) as snap_fn:
        out = fetch_moex_board_secids_on_day("TQBR", date(2024, 6, 3), db=db)
    assert out == ["SBER", "GAZP"]
    cache_fn.assert_called_once()
    snap_fn.assert_not_called()


def test_fetch_board_secids_falls_back_to_snapshot():
    db = MagicMock()
    with patch(
        "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_cache",
        return_value=[],
    ), patch(
        "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_snapshot",
        return_value=["LKOH"],
    ):
        out = fetch_moex_board_secids_on_day("TQBR", date(2024, 6, 3), db=db)
    assert out == ["LKOH"]


def test_list_board_tickers_as_of_skips_empty_session():
    async def _run():
        db = MagicMock()
        calls: list[date] = []

        def _cache(_db, day, **_kw):
            calls.append(day)
            if day == date(2024, 5, 31):
                return ["LKOH"]
            return []

        with patch(
            "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_cache",
            side_effect=_cache,
        ), patch(
            "app.modules.robots_v2.universe.board_as_of.fetch_osengine_board_secids_from_snapshot",
            return_value=[],
        ), patch(
            "app.modules.robots_v2.universe.board_as_of.list_osengine_day_tickers_from_data",
            return_value=[],
        ), patch(
            "app.modules.robots_v2.universe.board_as_of.list_board_tickers_from_tqbr",
            return_value=[],
        ):
            return await list_moex_board_tickers_as_of("TQBR", date(2024, 6, 3), db=db)

    out = asyncio.run(_run())
    assert out == ["LKOH"]


def test_screener_as_of_ensures_osengine_before_pit():
    from app.modules.robots_v2.config.v4_schema import UniverseConfig
    from app.modules.robots_v2.universe.service import UniverseService

    svc = UniverseService()
    universe = UniverseConfig.model_validate({
        "mode": "screener",
        "screener": {"preset": "high_liquidity"},
        "maxAssets": 5,
        "excluded": [],
    })
    ctx = MagicMock(user_id=1)

    async def _run():
        with patch(
            "app.modules.robots_v2.universe.board_as_of.list_moex_board_tickers_as_of",
            new=AsyncMock(return_value=["SBER", "GAZP", "LKOH"]),
        ), patch(
            "app.modules.robots_v2.universe.board_as_of.ensure_osengine_d1_for_screener",
            new=AsyncMock(return_value=["SBER", "GAZP"]),
        ) as ensure, patch(
            "app.modules.robots_v2.universe.service._apply_point_in_time_screen",
            return_value=(
                [{"ticker": "SBER", "last_price": 250.0, "value_today": 80_000_000, "volume24h": 80_000_000, "atr": 0}],
                [],
            ),
        ), patch(
            "app.modules.robots_v2.universe.service.dms_service.preview_pipeline_setup",
            new=AsyncMock(),
        ) as dms:
            assets, _ = await svc._preview_moex_screener(
                MagicMock(),
                ctx,
                universe,
                "stock",
                "high_liquidity",
                None,
                "all",
                set(),
                as_of=date(2024, 6, 3),
                robot_id=13,
            )
            dms.assert_not_called()
            ensure.assert_awaited_once()
            kwargs = ensure.await_args.kwargs
            assert kwargs["as_of"] == date(2024, 6, 3)
            assert kwargs["run_id"] == 13
            return assets

    assets = asyncio.run(_run())
    assert [a["ticker"] for a in assets] == ["SBER"]


def test_narrow_prefers_data_day_tickers():
    from app.modules.robots_v2.universe.board_as_of import narrow_screener_candidates_for_osengine

    with patch(
        "app.modules.robots_v2.universe.board_as_of.list_osengine_day_tickers_from_data",
        return_value=["SBER", "ZZZZ"],
    ):
        out = narrow_screener_candidates_for_osengine(["GAZP", "SBER", "LKOH"], limit=10)
    assert out == ["SBER"]
