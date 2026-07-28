"""Unit tests for harden_crypto_robot_configs script helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Allow importing the script module.
_scripts = Path(__file__).resolve().parents[1] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from harden_crypto_robot_configs import harden_crypto_robot_config  # noqa: E402


def test_harden_bumps_weak_price_and_oi():
    cfg, notes = harden_crypto_robot_config(
        {
            "broker_type": "bybit",
            "crypto_universe": {"min_last_price": 0.01, "min_open_interest_usd": 5_000_000},
            "bybit": {"leverage": 1},
            "risk": {},
        }
    )
    assert cfg["crypto_universe"]["min_last_price"] == 0.05
    assert cfg["crypto_universe"]["min_open_interest_usd"] == 20_000_000.0
    assert cfg["risk"]["max_leverage"] == 1
    assert cfg["risk"]["margin_mm_rate_halt"] == 0.80
    assert any("min_last_price" in n for n in notes)


def test_harden_preserves_explicit_zero_min_last_price():
    cfg, _ = harden_crypto_robot_config(
        {
            "broker_type": "bybit",
            "crypto_universe": {"min_last_price": 0},
            "bybit": {"leverage": 2},
            "risk": {"max_leverage": 2},
        }
    )
    assert cfg["crypto_universe"]["min_last_price"] == 0


def test_harden_force_no_margin():
    cfg, notes = harden_crypto_robot_config(
        {
            "broker_type": "bybit",
            "crypto_universe": {"min_last_price": 0.1},
            "bybit": {"leverage": 5},
            "risk": {"max_leverage": 5},
        },
        force_no_margin=True,
    )
    assert cfg["bybit"]["leverage"] == 0
    assert cfg["risk"]["max_leverage"] == 0
    assert any("no-margin" in n for n in notes)


def test_harden_skips_non_bybit():
    raw = {"broker_type": "tinvest", "crypto_universe": {"min_last_price": 0.01}}
    cfg, notes = harden_crypto_robot_config(raw)
    assert cfg == raw or cfg["crypto_universe"]["min_last_price"] == 0.01
    assert notes == []
