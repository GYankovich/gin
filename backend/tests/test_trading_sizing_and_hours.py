from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.modules.robots.config.risk_crypto import CryptoRiskConfig
from app.modules.robots.trading.costs import calculate_position_size
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_calculate_position_size_caps_by_portfolio_percent():
    # 20% of 10_000 = 2000 → 20 units at 100
    assert calculate_position_size(10_000, 100, max_position_percent=20, free_funds=10_000) == 20


def test_calculate_position_size_respects_existing_coin_exposure():
    # Already 15% in coin; room left = 5% of 10_000 = 500 → 5 units
    qty = calculate_position_size(
        10_000,
        100,
        max_position_percent=20,
        free_funds=10_000,
        existing_position_value=1_500,
    )
    assert qty == 5


def test_calculate_position_size_returns_zero_when_unaffordable():
    assert calculate_position_size(0, 1000, max_position_percent=50, free_funds=0) == 0
    # Existing already at/above cap
    assert (
        calculate_position_size(
            10_000,
            100,
            max_position_percent=20,
            free_funds=10_000,
            existing_position_value=2_000,
        )
        == 0
    )


def test_calculate_position_size_allows_fractional_when_budget_below_one_unit():
    # 50 USDT budget / 1000 price = 0.05 coin
    assert calculate_position_size(10_000, 1000, max_position_percent=50, free_funds=50) == 0.05


def test_calculate_position_size_no_longer_forces_min_one():
    # Old bug: max(1, lots) even with empty wallet
    assert calculate_position_size(0, 100, max_position_percent=20, free_funds=0) == 0


def test_crypto_risk_defaults_disable_session_hours():
    cfg = CryptoRiskConfig()
    assert cfg.enforce_session_hours is False
    assert cfg.allowed_weekdays == 127


def test_stage6_skips_msk_hours_when_enforce_disabled():
    class _Broker:
        async def get_last_price(self, user_id, figi):
            _ = (user_id, figi)
            return 100.0

        async def post_order(self, figi, quantity, price, direction, account_id, *, reduce_only: bool = False):
            _ = (figi, quantity, price, direction, account_id, reduce_only)
            return {"orderId": "oid-1", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

    # Sunday 03:00 UTC = Sunday 06:00 MSK — outside MOEX window
    async def _run():
        s6 = Stage6Orders(
            db=None,
            schema="ganaly",
            broker=_Broker(),
            account_id="A",
            robot_id=1,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            account_positions={},
            now_fn=lambda: datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc),  # Sunday
        )
        out = await s6.execute_signals(
            [{"figi": "BTCUSDT", "signal": "BUY", "quantity": 1, "price": 100.0}],
            risk_params={
                "enforce_session_hours": False,
                "allow_short": False,
                "min_trade_amount_rub": 1,
            },
        )
        assert out and out[0].get("error") not in {"TRADING_TIME_NOT_ALLOWED", "TRADING_WINDOW_CLOSED"}
        assert out[0]["status"] in {"open", "pending"}

    asyncio.run(_run())


def test_map_fill_keeps_entry_open_and_closes_exit():
    assert Stage6Orders.map_execution_status_to_trade_status("EXECUTION_REPORT_STATUS_FILL") == "open"
    assert (
        Stage6Orders.map_execution_status_to_trade_status("EXECUTION_REPORT_STATUS_FILL", closing=True)
        == "closed"
    )
