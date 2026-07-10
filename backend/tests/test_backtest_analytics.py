from app.modules.recommendations.backtest_analytics import (
    bybit_metrics,
    derive_payload_metrics,
    exit_reason_metrics,
    gap_metrics_from_decisions,
    general_metrics,
    long_short_metrics,
    moex_metrics,
    universe_metrics,
)


def test_exit_reason_metrics_from_signals():
    trades = [{"side": "sell", "pnl_net": -10}] * 5
    signals = [
        {"signal_type": "sell", "was_executed": 1, "reason": "stop_loss"},
        {"signal_type": "sell", "was_executed": 1, "reason": "take_profit"},
    ]
    m = exit_reason_metrics(trades, signals)
    assert m["stopLossHitRate"] == 20.0
    assert m["takeProfitHitRate"] == 20.0


def test_universe_metrics_from_daily_summary():
    payload = {
        "daily_summary": [
            {"candidates_accept": 3, "candidates_reject": 2},
            {"candidates_accept": 5, "candidates_reject": 0},
        ]
    }
    trades = [{"figi": "AAA"}, {"figi": "BBB"}, {"figi": "AAA"}]
    m = universe_metrics(payload, trades)
    assert m["avgUniverseSize"] == 5.0
    assert m["instrumentsTraded"] == 2.0
    assert m["universeUtilizationRatio"] == 0.4


def test_derive_payload_metrics_reads_history_stats():
    payload = {
        "initial_capital": 100_000,
        "history_stats": {"stopLossHitRate": 55.0, "takeProfitHitRate": 12.0},
        "trades": [{"pnl_net": 100}, {"pnl_net": -50}],
        "fee_summary": {"total_commission": 10},
    }

    class _Best:
        total_return_percent = 5.0

    m = derive_payload_metrics(payload, _Best())
    assert m["stopLossHitRate"] == 55.0
    assert m["takeProfitHitRate"] == 12.0
    assert m["profitFactor"] == 2.0


def test_gap_metrics_from_decisions():
    rows = [
        {
            "result": "REJECT",
            "reason": "Гэп 1.20% не прошел",
            "payload": {"eval": {"gap_percent": 1.2}},
        },
        {
            "result": "ACCEPT",
            "payload": {"eval": {"gap_percent": 0.4}},
        },
    ]
    m = gap_metrics_from_decisions(rows)
    assert m["avgGapImpactPct"] == 0.8
    assert m["gapRejectCount"] == 1.0


def test_moex_trading_hours_ratio():
    payload = {
        "initial_capital": 100_000,
        "total_return_percent": 10,
        "equity_curve": [
            {"time": "2024-01-01T15:00:00", "equity": 100_000},
            {"time": "2024-01-02T15:00:00", "equity": 101_000},
            {"time": "2024-01-03T15:00:00", "equity": 99_000},
        ],
    }
    m = moex_metrics(
        payload,
        [{"side": "sell", "pnl_net": 500}],
        risk_config={"trading_hours_start": "12:00 MSK", "trading_hours_end": "16:00 MSK"},
        costs_config={"ndfl_rate": 0.13},
    )
    assert m["tradingHoursUsedRatio"] is not None
    assert m["tradingHoursUsedRatio"] < 0.5


def test_bybit_slippage_ratio():
    payload = {
        "initial_capital": 10_000,
        "total_return_percent": 10,
        "margin_summary": {"enabled": True, "leverage": 5},
        "equity_curve": [{"time": "2024-01-01", "equity": 10_000}],
    }
    trades = [{"side": "buy", "price": 100, "quantity": 10}]
    m = bybit_metrics(payload, trades, config={"bybit": {"instrument_category": "linear"}}, slippage_pct=1.0)
    assert m["slippageToReturnRatio"] is not None
    assert m["instrumentIsPerp"] == 1.0
    assert m["leverageUsed"] is not None


def test_long_short_bias_flags():
    signals = [
        {"figi": "BTC", "signal_type": "buy", "was_executed": 1, "bar_time": "2024-01-01T10:00:00"},
        {"figi": "BTC", "signal_type": "buy", "was_executed": 1, "bar_time": "2024-01-01T11:00:00"},
        {"figi": "BTC", "signal_type": "buy", "was_executed": 1, "bar_time": "2024-01-01T12:00:00"},
        {"figi": "ETH", "signal_type": "short", "was_executed": 1, "bar_time": "2024-01-01T10:30:00"},
    ]
    trades = [
        {"figi": "BTC", "pnl_net": 10, "bar_time": "2024-01-01T15:00:00"},
        {"figi": "ETH", "pnl_net": 50, "bar_time": "2024-01-01T16:00:00"},
    ]
    m = long_short_metrics(trades, signals)
    assert m["longBiasWithWeakProfit"] == 1.0


def test_general_beta_estimate():
    payload = {"initial_capital": 10_000, "total_return_percent": 5}
    m = general_metrics(payload, [], [], broker_type="tinvest", volatility_annual_pct=25.0)
    assert m["betaEstimate"] is not None
    assert m["betaEstimate"] > 1.2
