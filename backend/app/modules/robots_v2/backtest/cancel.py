"""Shim — canonical: `app.modules.trading_core.cancel`."""
from __future__ import annotations
import sys, importlib
sys.modules[__name__] = importlib.import_module('app.modules.trading_core.cancel')
