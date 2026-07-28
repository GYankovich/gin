"""ByBit qty formatting: ceil + minOrderAmt for notional sizing."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade


def _facade_with_lot(*, qty_step: float = 0.1, min_qty: float = 0.1, min_amt: float = 5.0) -> ByBitBrokerFacade:
    fac = ByBitBrokerFacade.__new__(ByBitBrokerFacade)
    fac._instrument_category = "linear"
    fac._lot_filters = {
        "XLMUSDT": {
            "qty_step": qty_step,
            "min_qty": min_qty,
            "min_order_amt": min_amt,
        }
    }
    fac._http = MagicMock()
    return fac


def test_format_order_qty_floor_can_fall_below_min_notional():
    fac = _facade_with_lot(qty_step=0.1, min_qty=0.1, min_amt=5.0)
    # 5 / 0.192 = 26.0416… → floor 26.0 → 26*0.192 = 4.992 < 5
    qty = asyncio.run(fac._format_order_qty("XLMUSDT", 5.0 / 0.192, round_up=False, price=0.192))
    assert float(qty) == 26.0
    assert float(qty) * 0.192 < 5.0


def test_format_order_qty_round_up_meets_min_order_amt():
    fac = _facade_with_lot(qty_step=0.1, min_qty=0.1, min_amt=5.0)
    qty = asyncio.run(
        fac._format_order_qty("XLMUSDT", 5.0 / 0.192, round_up=True, price=0.192)
    )
    assert float(qty) * 0.192 + 1e-9 >= 5.0
    # ceil(26.0416→26.1) already >= 5; if not, bump steps
    assert float(qty) >= 26.1


def test_post_order_notional_path_uses_round_up():
    fac = _facade_with_lot(qty_step=0.1, min_qty=0.1, min_amt=5.0)
    fac._order_symbols = {}
    fac._http.create_order = AsyncMock(
        return_value={"result": {"orderId": "x1"}, "retCode": 0}
    )
    fac._map_side = ByBitBrokerFacade._map_side  # type: ignore[method-assign]

    result = asyncio.run(
        ByBitBrokerFacade.post_order(
            fac,
            figi="XLMUSDT",
            quantity=5.0 / 0.192,
            price=0.192,
            direction="ORDER_DIRECTION_BUY",
            account_id="a",
            qty_round_up=True,
        )
    )
    sent_qty = float(fac._http.create_order.await_args.kwargs["qty"])
    assert sent_qty * 0.192 + 1e-9 >= 5.0
    assert result["orderId"] == "x1"
