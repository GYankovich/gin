"""Shim — canonical location: `app.modules.trading_core.brokers.factory`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import factory as _canonical
sys.modules[__name__] = _canonical
