"""Shim — canonical location: `app.modules.trading_core.brokers.global_websocket`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import global_websocket as _canonical
sys.modules[__name__] = _canonical
