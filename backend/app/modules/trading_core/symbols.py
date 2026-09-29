"""Small symbol helpers shared by risk and guards."""

from __future__ import annotations

from typing import Any


def normalize_figi(figi: Any) -> str:
    return str(figi or "").upper().strip()
