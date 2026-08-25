"""Tests for price-based audit fill PnL."""

from app.modules.robots_v2.audit_pnl import (
    build_round_trips,
    enrich_fills_realized_pnl,
    normalize_live_fill_price,
)


def test_live_fill_notional_not_qty_minus_one_with_stale_ref():
    """VKCO 2026-08-24: broker 10×122.7 (pay 1227); stale last=129.7 must not pick 1227/9."""
    assert normalize_live_fill_price(1227.0, 10, ref_px=129.7) == 122.7
    assert normalize_live_fill_price(122.7, 10, ref_px=129.7) == 122.7
    assert abs(normalize_live_fill_price(968.0, 8, ref_px=129.7) - 121.0) < 1e-9


def test_enrich_realized_pnl_sell_leg():
    timeline = [
        {"id": "1", "ticker": "SBER", "side": "BUY", "quantity": 10, "price": 100.0, "filledAt": "t1"},
        {"id": "2", "ticker": "SBER", "side": "SELL", "quantity": 10, "price": 101.0, "filledAt": "t2"},
    ]
    page = [
        {
            "id": "2",
            "orderId": "o2",
            "robotId": 1,
            "ticker": "SBER",
            "side": "SELL",
            "quantity": 10,
            "price": 101.0,
            "pnl": 9999.0,
            "kind": "exit_sl_tp",
            "filledAt": "t2",
        },
    ]
    out = enrich_fills_realized_pnl(
        page, commission_rate=0.0, tax_rate=0.13, all_fills_chronological=timeline,
    )
    assert out[0]["ledgerPnl"] == 9999.0
    assert out[0]["realizedPnl"] == 10.0
    assert out[0]["netPnl"] == 8.7
    assert out[0]["entryPrice"] == 100.0
    assert "pnl" not in out[0]


def test_net_pnl_loss_has_no_tax():
    timeline = [
        {"id": "1", "ticker": "SBER", "side": "BUY", "quantity": 10, "price": 100.0, "filledAt": "t1"},
        {"id": "2", "ticker": "SBER", "side": "SELL", "quantity": 10, "price": 99.0, "filledAt": "t2"},
    ]
    page = [{"id": "2", "ticker": "SBER", "side": "SELL", "quantity": 10, "price": 99.0, "filledAt": "t2"}]
    out = enrich_fills_realized_pnl(
        page, commission_rate=0.0, tax_rate=0.13, all_fills_chronological=timeline,
    )
    assert out[0]["realizedPnl"] == -10.0
    assert out[0]["netPnl"] == -10.0


def test_buy_leg_has_no_realized_pnl():
    timeline = [
        {"id": "1", "ticker": "GAZP", "side": "BUY", "quantity": 1, "price": 150.0, "filledAt": "t1"},
    ]
    page = [{"id": "1", "ticker": "GAZP", "side": "BUY", "quantity": 1, "price": 150.0, "pnl": 0, "filledAt": "t1"}]
    out = enrich_fills_realized_pnl(page, all_fills_chronological=timeline)
    assert out[0]["realizedPnl"] is None


def test_fifo_pairs_sell_across_sessions():
    """OZON-style: buy in session 1, sell after restart in session 2."""
    timeline = [
        {"id": "b1", "ticker": "OZON", "side": "BUY", "quantity": 1, "price": 2888.0, "filledAt": "t1", "sessionId": "s1"},
        {"id": "s1", "ticker": "OZON", "side": "SELL", "quantity": 1, "price": 2975.5, "filledAt": "t2", "sessionId": "s2"},
    ]
    page = [{"id": "s1", "ticker": "OZON", "side": "SELL", "quantity": 1, "price": 2975.5, "filledAt": "t2"}]
    out = enrich_fills_realized_pnl(page, commission_rate=0.0, tax_rate=0.0, all_fills_chronological=timeline)
    assert out[0]["entryPrice"] == 2888.0
    assert out[0]["realizedPnl"] == 87.5
    trips = build_round_trips(timeline, {}, commission_rate=0.0, tax_rate=0.0)
    assert len(trips) == 1
    assert trips[0]["status"] == "closed"
    assert trips[0]["ticker"] == "OZON"
    assert trips[0]["buyPrice"] == 2888.0
    assert trips[0]["sellFillPrice"] == 2975.5


def test_fifo_complete_round_trips_in_two_sessions():
    timeline = [
        {"id": "b1", "ticker": "SMLT", "side": "BUY", "quantity": 7, "price": 387.8, "filledAt": "t1", "sessionId": "s1"},
        {"id": "s1", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 384.8, "filledAt": "t2", "sessionId": "s1"},
        {"id": "b2", "ticker": "SMLT", "side": "BUY", "quantity": 7, "price": 384.6, "filledAt": "t3", "sessionId": "s2"},
        {"id": "s2", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 381.2, "filledAt": "t4", "sessionId": "s2"},
    ]
    page = [{"id": "s2", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 381.2, "filledAt": "t4"}]
    out = enrich_fills_realized_pnl(page, commission_rate=0.0, tax_rate=0.0, all_fills_chronological=timeline)
    assert out[0]["entryPrice"] == 384.6
    assert out[0]["realizedPnl"] == -23.8


def test_fifo_survives_legacy_notional_buys():
    """SMLT-style: old session stored buy notional; later sells must pair correctly."""
    timeline = [
        {"id": "b1", "ticker": "SMLT", "side": "BUY", "quantity": 4, "price": 1587.2, "filledAt": "t0"},
        {"id": "s1", "ticker": "SMLT", "side": "SELL", "quantity": 4, "price": 1586.4, "filledAt": "t0b"},
        {"id": "b2", "ticker": "SMLT", "side": "BUY", "quantity": 7, "price": 2801.4, "filledAt": "t1"},
        {"id": "s2", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 380.0, "filledAt": "t1b"},
        {"id": "b3", "ticker": "SMLT", "side": "BUY", "quantity": 7, "price": 369.8, "filledAt": "t2"},
        {"id": "s3", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 370.2, "filledAt": "t3"},
    ]
    page = [{"id": "s3", "ticker": "SMLT", "side": "SELL", "quantity": 7, "price": 370.2, "filledAt": "t3"}]
    out = enrich_fills_realized_pnl(
        page, commission_rate=0.0005, tax_rate=0.13, all_fills_chronological=timeline,
    )
    assert out[0]["entryPrice"] == 369.8
    assert out[0]["realizedPnl"] is not None
    assert float(out[0]["realizedPnl"]) > 0
    assert float(out[0]["netPnl"]) > 0


def test_net_pnl_repairs_notional_buy_price():
    """SFIN-style bug: buy stored as unit×qty (1767.6), sell unit 602.4."""
    timeline = [
        {"id": "1", "ticker": "SFIN", "side": "BUY", "quantity": 3, "price": 1767.6, "filledAt": "t1"},
        {"id": "2", "ticker": "SFIN", "side": "SELL", "quantity": 3, "price": 602.4, "filledAt": "t2"},
    ]
    page = [{"id": "2", "ticker": "SFIN", "side": "SELL", "quantity": 3, "price": 602.4, "filledAt": "t2"}]
    out = enrich_fills_realized_pnl(
        page, commission_rate=0.0, tax_rate=0.13, all_fills_chronological=timeline,
    )
    # unit entry 589.2 → gross (602.4-589.2)*3 = 39.6
    assert out[0]["realizedPnl"] == 39.6
    assert out[0]["netPnl"] == round(39.6 * (1 - 0.13), 4)


def test_nvtk_notional_sell_price_normalized():
    from app.modules.robots_v2.audit_pnl import build_round_trips, enrich_fills_realized_pnl

    timeline = [
        {"id": "b1", "ticker": "NVTK", "side": "BUY", "quantity": 3, "price": 935.2, "filledAt": "t1"},
        {"id": "s1", "ticker": "NVTK", "side": "SELL", "quantity": 2, "price": 935.35, "filledAt": "t2"},
    ]
    out = enrich_fills_realized_pnl(
        [{"id": "s1", "ticker": "NVTK", "side": "SELL", "quantity": 2, "price": 935.35, "filledAt": "t2"}],
        commission_rate=0.0005,
        tax_rate=0.13,
        all_fills_chronological=timeline,
    )
    assert abs(out[0]["entryPrice"] - 311.73333333333335) < 1e-4
    # Tiny move (~0.05 ₽/share); commission on ~622 ₽ notional dominates.
    assert float(out[0]["realizedPnl"]) < 0
    assert abs(float(out[0]["realizedPnl"]) + 0.52) < 0.05
    trips = build_round_trips(timeline, {}, commission_rate=0.0005, tax_rate=0.13)
    assert abs(trips[0]["sellFillPrice"] - 311.78333333333336) < 1e-4


def test_build_round_trips_closed():
    from app.modules.robots_v2.audit_pnl import build_round_trips

    timeline = [
        {
            "id": "b1",
            "orderId": "ob1",
            "ticker": "SMLT",
            "side": "BUY",
            "quantity": 7,
            "price": 369.8,
            "kind": "entry",
            "filledAt": "2026-08-14T09:48:00Z",
            "sessionId": "s1",
        },
        {
            "id": "s1",
            "orderId": "os1",
            "ticker": "SMLT",
            "side": "SELL",
            "quantity": 7,
            "price": 370.2,
            "kind": "exit_strategy",
            "filledAt": "2026-08-14T09:50:00Z",
            "sessionId": "s1",
        },
    ]
    orders = {
        "os1": {
            "id": "os1",
            "cycleId": "c1",
            "ticker": "SMLT",
            "side": "SELL",
            "kind": "exit_strategy",
            "price": 370.5,
            "orderType": "MARKET",
        },
    }
    trips = build_round_trips(timeline, orders, commission_rate=0.0005, tax_rate=0.13)
    assert len(trips) == 1
    assert trips[0]["ticker"] == "SMLT"
    assert trips[0]["buyPrice"] == 369.8
    assert trips[0]["sellFillPrice"] == 370.2
    assert trips[0]["status"] == "closed"
    assert trips[0]["reason"] == "exit_strategy"
    assert float(trips[0]["realizedPnl"]) > 0
    assert float(trips[0]["netPnl"]) > 0
    assert float(trips[0]["netPnl"]) < float(trips[0]["realizedPnl"])


def test_build_round_trips_open_position():
    from app.modules.robots_v2.audit_pnl import build_round_trips

    timeline = [
        {
            "id": "b1",
            "orderId": "ob1",
            "ticker": "ROSN",
            "side": "BUY",
            "quantity": 10,
            "price": 500.0,
            "kind": "entry",
            "filledAt": "t1",
            "sessionId": "s1",
        },
    ]
    trips = build_round_trips(timeline, {}, commission_rate=0.0, tax_rate=0.0)
    assert len(trips) == 1
    assert trips[0]["status"] == "open"
    assert trips[0]["sellAt"] is None
    assert trips[0]["reason"] == "entry"
