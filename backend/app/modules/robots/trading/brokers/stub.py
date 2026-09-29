"""Shim — canonical location: `app.modules.trading_core.brokers.stub`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import stub as _canonical
sys.modules[__name__] = _canonical
