"""Shim — canonical location: `app.modules.trading_core.brokers.rate_limiter`."""
from __future__ import annotations
import sys
from app.modules.trading_core.brokers import rate_limiter as _canonical
sys.modules[__name__] = _canonical
