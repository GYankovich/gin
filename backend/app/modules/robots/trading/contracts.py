"""Shim — canonical location: ``app.modules.trading_core.contracts``."""

from __future__ import annotations

import sys

from app.modules.trading_core import contracts as _canonical

sys.modules[__name__] = _canonical
