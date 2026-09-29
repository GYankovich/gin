"""Shim — canonical location: ``app.modules.trading_core.risk.manager``."""

from __future__ import annotations

import sys

from app.modules.trading_core.risk import manager as _canonical

sys.modules[__name__] = _canonical
