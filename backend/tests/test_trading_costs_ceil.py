"""Break-even and SL/TP money rounding formulas."""

from decimal import Decimal

from app.modules.robots.trading.costs import (
    TradingCosts,
    calculate_break_even_price,
    calculate_stop_loss_price,
    calculate_take_profit_price,
    ceil_money,
    floor_money,
)


def test_ceil_money_example():
    assert ceil_money(2065.06351575) == 2065.07
    assert ceil_money(Decimal("2065.06000000")) == 2065.06
    assert ceil_money("2065.06000001") == 2065.07


def test_break_even_exact_formula_ceils():
    costs = TradingCosts(
        2063.0,
        1,
        broker_commission_rate=0.0005,
        ndfl_rate=0.13,  # must not affect BE
    )
    # 2063 * 1.0005 / 0.9995 = 2065.064032… → 2065.07
    assert costs.calculate_break_even_price() == 2065.07
    assert calculate_break_even_price(2063.0, is_long=True, broker_commission_rate=0.0005) == 2065.07


def test_break_even_short_floors():
    # 1000 * 0.9995 / 1.0005 ≈ 999.0005 → floor 999.00
    px = calculate_break_even_price(1000.0, is_long=False, broker_commission_rate=0.0005)
    assert px == floor_money(1000.0 * 0.9995 / 1.0005)


def test_stop_loss_net_loss_after_fees_long():
    # Exit*(1-f)-Entry*(1+f) = -Entry*0.02
    # → 2063 * (1.0005-0.02)/0.9995 = 2023.7833… → ceil 2023.79
    px = calculate_stop_loss_price(
        2063.0,
        2.0,
        is_long=True,
        broker_commission_rate=0.0005,
    )
    assert px == 2023.79


def test_stop_loss_without_fees_matches_simple_pct():
    px = calculate_stop_loss_price(1000.0, 2.0, is_long=True, broker_commission_rate=0.0)
    assert px == 980.0


def test_stop_loss_short_floors():
    # Entry*(1-f)-Exit*(1+f) = -Entry*0.02
    # → 1000 * (0.9995+0.02)/1.0005 ≈ 1019.4902 → floor 1019.49
    px = calculate_stop_loss_price(
        1000.0,
        2.0,
        is_long=False,
        broker_commission_rate=0.0005,
    )
    assert px == floor_money(1000.0 * (0.9995 + 0.02) / 1.0005)


def test_take_profit_net_in_pocket_long():
    # Exit = Entry * ((1+f) + 0.04/0.87) / (1-f) → 2159.962… → ceil 2159.97
    px = calculate_take_profit_price(
        2063.0,
        4.0,
        is_long=True,
        broker_commission_rate=0.0005,
        ndfl_rate=0.13,
    )
    assert px == 2159.97


def test_take_profit_zero_equals_break_even():
    px = calculate_take_profit_price(
        2063.0,
        0.0,
        is_long=True,
        broker_commission_rate=0.0005,
        ndfl_rate=0.13,
    )
    assert px == 2065.07
    costs = TradingCosts(2063.0, 1, broker_commission_rate=0.0005, ndfl_rate=0.13)
    assert px == costs.calculate_break_even_price()
