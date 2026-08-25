"""Tests for universe mode normalization in DMS setup."""

from app.modules.robots.universe import (
    UNIVERSE_MODE_TQBR,
    normalize_universe_mode_arg,
)


def test_normalize_universe_mode_arg_accepts_raw_string():
    assert normalize_universe_mode_arg("tqbr_scan") == UNIVERSE_MODE_TQBR
    assert normalize_universe_mode_arg({"universe_mode": "tqbr_scan"}) == UNIVERSE_MODE_TQBR
