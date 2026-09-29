"""Shim — canonical location: `app.modules.trading_core.data.stats`."""
from __future__ import annotations
import sys
import importlib
_canonical = importlib.import_module('app.modules.trading_core.data.stats')
sys.modules[__name__] = _canonical
