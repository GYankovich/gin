"""Shim — canonical location: ``app.modules.trading_core.costs``."""

from __future__ import annotations

import sys

from app.modules.trading_core import costs as _canonical

sys.modules[__name__] = _canonical
