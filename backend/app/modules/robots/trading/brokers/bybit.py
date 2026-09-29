"""Shim — canonical location: `app.modules.trading_core.brokers.bybit`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import bybit as _canonical
sys.modules[__name__] = _canonical
