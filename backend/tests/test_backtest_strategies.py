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
    async def test_grain_seed_executes(self):
        cases = [(
            "grain_seed",
            {
                "gap_filter_pct": 3.0,
                "spread_limit_pct": 0.2,
                "atr_period": 14,
                "atr_min_pct": 0.3,
                "adx_period": 14,
                "adx_threshold": 20.0,
                "ma_fast_period": 5,
                "ma_slow_period": 20,
                "bb_period": 20,
                "bb_stddev": 2.0,
                "commission_pct": 0.05,
                "min_profit_target_pct": 0.35,
            },
            {"FIGI1": make_candles(320, 100, 7, 0.02), "FIGI2": make_candles(320, 120, 6, -0.01)},
        )]
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

    async def test_grain_seed_produces_executable_signals(self):
        result = await run_backtest_simulation(
            candles_by_figi={"FIGI1": make_candles(260, 100, 9, 0.01)},
            strategy_name="grain_seed",
            strategy_params={"atr_period": 14, "ma_fast_period": 5, "ma_slow_period": 20},
            risk_params={"max_position_percent": 10},
            initial_capital=1_000_000,
        )
        sides = {t["side"] for t in result.trades}
        self.assertTrue(sides.issubset({"buy", "sell"}))


if __name__ == "__main__":
    unittest.main()
