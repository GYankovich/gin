import math
import unittest
from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.backtest.engine import run_backtest_simulation


def make_candles(count: int, base: float, amp: float, trend: float, step_minutes: int = 10):
    candles = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        price = base + amp * math.sin(i / 12.0) + trend * i
        units = int(price)
        nano = int((price - units) * 1_000_000_000)
        q = {"units": units, "nano": nano}
        candles.append(
            {
                "time": (start + timedelta(minutes=step_minutes * i)).isoformat().replace("+00:00", "Z"),
                "open": q,
                "high": q,
                "low": q,
                "close": q,
                "volume": 1000 + i,
            }
        )
    return candles


class BacktestStrategiesTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_all_strategies_execute(self):
        cases = [
            ("ma_cross", {"fast_period": 10, "slow_period": 30}, {"FIGI1": make_candles(260, 100, 8, 0.05)}),
            ("conservative", {"volatility_lookback": 60, "max_volatility": 0.5}, {"FIGI1": make_candles(260, 100, 9, 0.01)}),
            (
                "aggressive_momentum",
                {"momentum_periods": [21, 63, 126], "top_n": 2},
                {
                    "FIGI1": make_candles(280, 100, 5, 0.03),
                    "FIGI2": make_candles(280, 120, 12, -0.01),
                    "FIGI3": make_candles(280, 80, 4, 0.06),
                },
            ),
            (
                "defensive_cash",
                {"volatility_threshold": 0.5},
                {"FIGI1": make_candles(220, 100, 6, 0.01), "FIGI2": make_candles(220, 90, 7, 0.02)},
            ),
        ]
        risk = {"max_position_percent": 10, "max_position_rub": 50_000, "stop_loss_percent": 2, "take_profit_percent": 3}

        for strategy_name, strategy_params, candles_by_figi in cases:
            with self.subTest(strategy=strategy_name):
                result = await run_backtest_simulation(
                    candles_by_figi=candles_by_figi,
                    strategy_name=strategy_name,
                    strategy_params=strategy_params,
                    risk_params=risk,
                    initial_capital=1_000_000,
                )
                self.assertGreater(len(result.equity_curve), 0)
                self.assertIsInstance(result.final_equity, float)

    async def test_conservative_produces_executable_signals(self):
        result = await run_backtest_simulation(
            candles_by_figi={"FIGI1": make_candles(260, 100, 9, 0.01)},
            strategy_name="conservative",
            strategy_params={"volatility_lookback": 60, "max_volatility": 0.5},
            risk_params={"max_position_percent": 10},
            initial_capital=1_000_000,
        )
        sides = {t["side"] for t in result.trades}
        self.assertTrue(sides.issubset({"buy", "sell"}))


if __name__ == "__main__":
    unittest.main()
