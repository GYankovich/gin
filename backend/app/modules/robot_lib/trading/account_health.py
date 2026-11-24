"""Shim — canonical location: `app.modules.trading_core.account_health`."""
from __future__ import annotations
import sys
from app.modules.trading_core import account_health as _canonical
sys.modules[__name__] = _canonical
