"""Shim — canonical location: `app.modules.trading_core.brokers.sim_backtest`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import sim_backtest as _canonical
sys.modules[__name__] = _canonical
