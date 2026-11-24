"""Shim — canonical location: ``app.modules.trading_core.intervals``."""

from __future__ import annotations

import sys

from app.modules.trading_core import intervals as _canonical

sys.modules[__name__] = _canonical
