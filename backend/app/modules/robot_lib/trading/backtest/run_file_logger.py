"""Shim — canonical: `app.modules.trading_core.logging.run_file_logger`."""
from __future__ import annotations
import sys, importlib
sys.modules[__name__] = importlib.import_module('app.modules.trading_core.logging.run_file_logger')
