from __future__ import annotations

from app.modules.recommendations.optimization_engine import (
    BacktestScoreInput,
    calculate_score,
    check_overfitting_warnings,
    generate_grid_configs,
    optimizable_params,
)


def test_calculate_score_balanced_penalizes_low_trades():
    rich = BacktestScoreInput(
        total_return_pct=20.0,
        max_drawdown_pct=10.0,
        sharpe=1.5,
        win_rate_pct=55.0,
        trades_total=50,
    )
    poor_trades = BacktestScoreInput(
        total_return_pct=20.0,
        max_drawdown_pct=10.0,
        sharpe=1.5,
        win_rate_pct=55.0,
        trades_total=5,
    )
    assert calculate_score(rich, "balanced") > calculate_score(poor_trades, "balanced")


def test_calculate_score_max_return_prefers_return():
    a = BacktestScoreInput(total_return_pct=30.0, max_drawdown_pct=15.0, sharpe=1.0, trades_total=40)
    b = BacktestScoreInput(total_return_pct=10.0, max_drawdown_pct=5.0, sharpe=2.0, trades_total=40)
    assert calculate_score(a, "max_return") > calculate_score(b, "max_return")


def test_overfitting_warnings():
    ranked = [
        {"score": 12.0, "trades_total": 10, "sharpe": 3.0},
        {"score": 8.0, "trades_total": 30, "sharpe": 1.2},
    ]
    warnings = check_overfitting_warnings(ranked)
    assert any("overfitting" in w.lower() or "Мало сделок" in w for w in warnings)


def test_generate_grid_configs_speed_mode():
    base = {
        "strategy": "reversion_to_ma",
        "risk": {
            "stop_loss_percent": 2.0,
            "take_profit_percent": 3.0,
            "max_position_percent": 10.0,
            "max_daily_loss": 5.0,
        },
        "strategy_params": {
            "ma_period": 20,
            "deviation_pct": 2.0,
            "rsi_period": 14,
            "max_hold_candles": 10,
        },
    }
    params = optimizable_params(base, "reversion_to_ma")
    assert len(params) >= 4
    variants = generate_grid_configs(base, "reversion_to_ma", mode="speed")
    assert 1 <= len(variants) <= 20
    assert variants[0]["risk"]["stop_loss_percent"] is not None
