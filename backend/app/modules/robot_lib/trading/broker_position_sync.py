"""Shim — canonical location: `app.modules.trading_core.broker_position_sync`."""
from __future__ import annotations
import sys
from app.modules.trading_core import broker_position_sync as _canonical
sys.modules[__name__] = _canonical
