"""Account health gates: MMR, equity drawdown, stale book, cheap-alt entry filter."""

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

from app.modules.robots.crypto_universe import resolve_crypto_universe_filters
from app.modules.robots.trading.account_health import (
    evaluate_equity_drawdown_halt,
    evaluate_margin_halt,
    evaluate_refresh_fail_halt,
    extract_wallet_margin_health,
    min_liq_distance_pct,
)
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_extract_wallet_margin_health_rates():
    h = extract_wallet_margin_health(
        {
            "totalEquity": "1000",
            "accountMMRate": "0.85",
            "accountIMRate": "0.4",
            "totalMaintenanceMargin": "850",
            "totalInitialMargin": "400",
        }
    )
    assert h["equity"] == 1000.0
    assert h["account_mm_rate"] == 0.85


def test_margin_halt_on_high_mm_rate():
    halt, reason = evaluate_margin_halt({"account_mm_rate": 0.81}, mm_rate_halt=0.80)
    assert halt is True
    assert "account_mm_rate" in reason


def test_margin_halt_near_liq():
    halt, reason = evaluate_margin_halt(
        {"account_mm_rate": 0.1, "min_liq_distance_pct": 0.03},
        mm_rate_halt=0.80,
        liq_distance_halt=0.05,
    )
    assert halt is True
    assert "near_liquidation" in reason


def test_equity_drawdown_halt():
    halt, reason = evaluate_equity_drawdown_halt(
        equity=700,
        peak_equity=1000,
        session_start_equity=1000,
        max_drawdown_percent=20.0,
    )
    assert halt is True
    assert "equity_drawdown" in reason


def test_refresh_fail_halt():
    halt, _ = evaluate_refresh_fail_halt(3, halt_after=3)
    assert halt is True
    halt2, _ = evaluate_refresh_fail_halt(2, halt_after=3)
    assert halt2 is False


def test_min_liq_distance_pct():
    dist = min_liq_distance_pct(
        [
            {
                "instrument_type": "crypto_perpetual",
                "mark_price": 100.0,
                "liq_price": 95.0,
            }
        ]
    )
    assert dist == 0.05


def test_universe_default_min_last_price_hardened():
    flt = resolve_crypto_universe_filters({"crypto_universe": {}})
    assert flt.min_last_price == 0.05
    assert flt.min_open_interest_usd == 20_000_000.0


def test_stage6_skips_cheap_entry_by_min_last_price():
    class _Broker:
        async def get_last_price(self, user_id, figi):
            return 0.04

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
            [{"figi": "TREEUSDT", "signal": "BUY", "quantity": 100, "price": 0.04}],
            risk_params={
                "max_leverage": 1,
                "instrument_category": "linear",
                "margin_enabled": True,
                "min_last_price": 0.05,
                "enforce_session_hours": False,
                "free_funds": 10_000,
                "min_trade_amount_rub": 0,
            },
        )
        assert out[0]["status"] == "skipped"
        assert out[0]["error"] == "MIN_LAST_PRICE"

    asyncio.run(_run())
