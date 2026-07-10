from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.modules.robots.trading.contracts import Position, Signal
from app.modules.robots.trading.risk import RiskManager, RiskParams
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_risk_manager_blocks_short_when_disabled():
    rm = RiskManager(RiskParams(allow_short=False))
    rm.begin_day(equity_at_open=100_000)
    sig = Signal(secid="BTCUSDT", side="SELL", target_price=60_000.0)
    res = rm.pre_trade_check(sig, cash=100_000, equity=100_000, positions={})
    assert not res.allow
    assert res.reason == "short_not_allowed"


def test_risk_manager_allow_short_and_leverage_caps_quantity():
    rm = RiskManager(RiskParams(allow_short=True, max_leverage=0.5, max_position_pct=100.0, free_funds_reserve_pct=0.0))
    sig = Signal(secid="BTCUSDT", side="BUY", target_price=100.0)
    qty = rm.compute_quantity(sig, cash=1_000_000, equity=1_000, entry_price=100.0)
    assert qty == 5  # 1000 * 0.5 / 100


def test_stage6_allow_short_sell_without_asset():
    class _Broker:
        async def get_last_price(self, user_id, figi):
            _ = (user_id, figi)
            return 100.0

        async def post_order(self, figi, quantity, price, direction, account_id):
            _ = (figi, quantity, price, direction, account_id)
            return {"orderId": "oid-1", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

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
            now_fn=lambda: datetime.now(timezone.utc),
        )
        out = await s6.execute_signals(
            [{"figi": "BTCUSDT", "signal": "SELL", "quantity": 10, "price": 100.0}],
            risk_params={
                "allow_short": True,
                "enforce_session_hours": False,
                "trading_hours_start": "00:00",
                "trading_hours_end": "23:59",
            },
        )
        assert out and out[0]["status"] in {"open", "pending"}

    asyncio.run(_run())

