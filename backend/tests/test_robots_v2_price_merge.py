"""WS vs REST last-price merge: trade marks vs UI gap-fill."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.engine.market_data import merge_ws_and_rest_prices


def test_rest_does_not_clobber_live_ws_on_scalper_tick():
    trade, gap = merge_ws_and_rest_prices(
        last_prices={"OZON": 100.0, "SBER": 310.0, "VKCO": 122.7},
        rest_prices={"OZON": 95.0, "VKCO": 129.7},
        tickers=["OZON", "SBER", "VKCO"],
        seed_from_ws=True,
    )
    assert trade["OZON"] == 100.0
    assert trade["SBER"] == 310.0
    assert trade["VKCO"] == 122.7
    assert gap == {}


def test_poll_cycle_rest_overwrites_held_marks():
    trade, gap = merge_ws_and_rest_prices(
        last_prices={"OZON": 100.0, "SBER": 310.0},
        rest_prices={"OZON": 95.0},
        tickers=["OZON", "SBER"],
        seed_from_ws=False,
    )
    assert trade["OZON"] == 95.0
    assert trade["SBER"] == 310.0
    assert gap == {}


def test_missing_ws_mark_is_gap_filled_from_rest():
    trade, gap = merge_ws_and_rest_prices(
        last_prices={},
        rest_prices={"OZON": 95.0},
        tickers=["OZON"],
        seed_from_ws=False,
    )
    assert trade["OZON"] == 95.0
    assert gap == {"OZON": 95.0}
