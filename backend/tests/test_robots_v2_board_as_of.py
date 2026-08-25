"""Causal MOEX board membership for backtest screener."""

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


def test_history_url_tqbr():
    from app.modules.robots_v2.universe.board_as_of import _history_url

    url = _history_url("TQBR")
    assert "engines/stock/markets/shares/boards/TQBR" in url
    assert "history" in url


def test_fetch_board_secids_parses_history_page():
    class _Resp:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "history": {
                    "columns": ["BOARDID", "SECID", "CLOSE"],
                    "data": [
                        ["TQBR", "SBER", 250],
                        ["TQBR", "GAZP", 120],
                    ],
                }
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _Resp()

    class _Gate:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    with patch("app.modules.robots_v2.universe.board_as_of.httpx.AsyncClient", return_value=_Client()), patch(
        "app.modules.robots_v2.universe.board_as_of.moex_http_acquire", return_value=_Gate(),
    ):
        out = asyncio.run(fetch_moex_board_secids_on_day("TQBR", date(2024, 6, 3)))
    assert out == ["SBER", "GAZP"]


def test_list_board_tickers_as_of_skips_empty_session():
    async def _fake(board, day):
        if day == date(2024, 6, 3):
            return []
        if day == date(2024, 6, 2):
            return []
        if day == date(2024, 5, 31):
            return ["LKOH"]
        return []

    with patch(
        "app.modules.robots_v2.universe.board_as_of.fetch_moex_board_secids_on_day",
        side_effect=_fake,
    ):
        out = asyncio.run(list_moex_board_tickers_as_of("TQBR", date(2024, 6, 3)))
    assert out == ["LKOH"]


def test_screener_as_of_does_not_call_live_dms():
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
            new=AsyncMock(return_value=["SBER", "NEWIPO"]),
        ), patch(
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
            )
            dms.assert_not_called()
            return assets

    assets = asyncio.run(_run())
    assert [a["ticker"] for a in assets] == ["SBER"]
