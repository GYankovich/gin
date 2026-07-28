"""Trading core — единый цикл решений (live + backtest). См. docs/BRD-ARCH-04."""

from .cycle import CycleStatsDelta
from .trading_core import TradingCore, run_single_trading_cycle

__all__ = ["CycleStatsDelta", "TradingCore", "run_single_trading_cycle"]
