"""Shim — canonical location: `app.modules.trading_core.brokers.routing`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import routing as _canonical
sys.modules[__name__] = _canonical
