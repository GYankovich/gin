"""Shim — canonical location: ``app.modules.trading_core.risk.params``."""

from __future__ import annotations

import sys

from app.modules.trading_core.risk import params as _canonical

sys.modules[__name__] = _canonical
