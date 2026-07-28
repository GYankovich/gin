"""Tests for broker position import, fatal halt codes, leverage=0 no-margin."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.bybit.http_client import BybitApiError
from app.modules.robots.trading.broker_position_sync import (
    broker_positions_missing_in_db,
    configured_leverage,
    extract_account_position_meta,
    is_fatal_broker_error,
)
from app.modules.robots.trading.brokers.margin import resolve_margin_params
from app.modules.robots.trading.risk import RiskManager, RiskParams
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_resolve_margin_disabled_when_leverage_zero():
    m = resolve_margin_params(
        {
            "broker_type": "bybit",
            "bybit": {"instrument_category": "linear", "leverage": 0},
            "risk": {"max_leverage": 0},
        }
    )
    assert m["enabled"] is False
    assert m["leverage"] == 0.0


def test_resolve_margin_enabled_at_leverage_one():
    m = resolve_margin_params(
        {
            "broker_type": "bybit",
            "bybit": {"instrument_category": "linear", "leverage": 1},
        }
    )
    assert m["enabled"] is True
    assert m["leverage"] == 1.0


def test_configured_leverage_preserves_zero():
    assert configured_leverage({"bybit": {"leverage": 0}, "risk": {"max_leverage": 5}}) == 0.0


def test_is_synthetic_broker_order_id():
    from app.modules.robots.trading.broker_position_sync import is_synthetic_broker_order_id

    assert is_synthetic_broker_order_id("broker_import:24:XLMUSDT:buy")
    assert is_synthetic_broker_order_id("broker_import:XLMUSDT:buy")
    assert not is_synthetic_broker_order_id("1234567890")
    assert not is_synthetic_broker_order_id(None)
    meta = extract_account_position_meta(
        [
            {
                "figi": "TREEUSDT",
                "ticker": "TREEUSDT",
                "instrument_type": "crypto_perpetual",
                "quantity": {"decimal": -39016.8},
                "side": "Sell",
                "average_position_price": {"decimal": 0.04},
                "current_price": {"decimal": 0.03},
            }
        ]
    )
    assert meta["TREEUSDT"]["qty"] == -39016.8
    missing = broker_positions_missing_in_db(meta, open_positions=[], robot_id=24)
    assert len(missing) == 1
    assert missing[0]["side"] == "sell"
    assert missing[0]["quantity"] == 39016.8
    assert missing[0]["status"] == "open"
    assert missing[0]["filled_quantity"] == 39016.8
    assert missing[0]["order_id"] == "broker_import:24:TREEUSDT:sell"

    # Already in DB → no import.
    assert (
        broker_positions_missing_in_db(
            meta,
            open_positions=[
                {"figi": "TREEUSDT", "side": "sell", "quantity": 39016.8, "status": "open"}
            ],
            robot_id=24,
        )
        == []
    )


def test_fatal_broker_error_codes():
    assert is_fatal_broker_error(BybitApiError("ab not enough", ret_code=110007))
    assert is_fatal_broker_error(BybitApiError("reduce-only", ret_code=110017))
    assert is_fatal_broker_error("ByBit API error retCode=110017: xxx")
    assert not is_fatal_broker_error(BybitApiError("rate limit", ret_code=10006))


def test_risk_manager_zero_leverage_blocks_sizing():
    rm = RiskManager(RiskParams(allow_short=True, max_leverage=0, max_position_pct=100.0))
    from app.modules.robots.trading.contracts import Signal

    qty = rm.compute_quantity(
        Signal(secid="BTCUSDT", side="BUY", target_price=100.0),
        cash=10_000,
        equity=10_000,
        entry_price=100.0,
    )
    assert qty == 0


def test_stage6_blocks_entry_when_leverage_zero_linear():
    class _Broker:
        async def get_last_price(self, user_id, figi):
            return 100.0

        async def post_order(self, *a, **k):
            raise AssertionError("must not place")

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
            [{"figi": "BTCUSDT", "signal": "BUY", "quantity": 1, "price": 100.0}],
            risk_params={
                "max_leverage": 0,
                "instrument_category": "linear",
                "margin_enabled": False,
                "enforce_session_hours": False,
                "free_funds": 10_000,
                "min_trade_amount_rub": 0,
            },
        )
        assert out[0]["status"] == "skipped"
        assert out[0]["error"] == "MARGIN_TRADING_DISABLED"

    asyncio.run(_run())


def test_stage6_allows_exit_when_leverage_zero():
    class _Broker:
        def __init__(self):
            self.posts = []

        async def get_last_price(self, user_id, figi):
            return 100.0

        async def post_order(self, figi, quantity, price, direction, account_id, *, reduce_only=False):
            self.posts.append({"figi": figi, "reduce_only": reduce_only, "direction": direction})
            return {"orderId": "oid-1", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

    async def _run():
        broker = _Broker()
        s6 = Stage6Orders(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=1,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            account_positions={"BTCUSDT": 2.0},
            now_fn=lambda: datetime.now(timezone.utc),
        )
        out = await s6.execute_signals(
            [{
                "figi": "BTCUSDT",
                "signal": "SELL",
                "quantity": 2,
                "price": 100.0,
                "reduce_only": True,
                "intent_kind": "exit_sl_tp",
            }],
            risk_params={
                "max_leverage": 0,
                "instrument_category": "linear",
                "margin_enabled": False,
                "enforce_session_hours": False,
                "min_trade_amount_rub": 0,
            },
        )
        assert out[0]["status"] in {"open", "pending"}
        assert broker.posts and broker.posts[0]["reduce_only"] is True

    asyncio.run(_run())
