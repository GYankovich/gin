"""Shim — canonical location: `app.modules.trading_core.brokers.margin`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import margin as _canonical
sys.modules[__name__] = _canonical
