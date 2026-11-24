"""Shim — canonical location: `app.modules.trading_core.data.facade`."""
from __future__ import annotations
import sys
import importlib
_canonical = importlib.import_module('app.modules.trading_core.data.facade')
sys.modules[__name__] = _canonical
