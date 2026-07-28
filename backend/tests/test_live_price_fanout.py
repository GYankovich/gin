"""Session → Live UI price fan-out (inline PG NOTIFY payloads)."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.live_events import expand_inline_live_payload


def test_expand_single_price_payload():
    out = expand_inline_live_payload(
        24,
        {"type": "price", "figi": "treeusdt", "price": 0.035, "time": "2026-07-20T15:00:00Z"},
    )
    assert len(out) == 1
    assert out[0]["type"] == "price"
    assert out[0]["figi"] == "TREEUSDT"
    assert out[0]["price"] == 0.035
    assert out[0]["source"] == "session"
    assert out[0]["robot_id"] == 24


def test_expand_prices_batch_payload():
    out = expand_inline_live_payload(
        24,
        {
            "type": "prices",
            "items": [
                {"figi": "AAAUSDT", "price": 1.0},
                {"figi": "BBBUSDT", "price": "2.5"},
                {"figi": "", "price": 3.0},
            ],
            "time": "t1",
            "source": "session",
        },
    )
    assert len(out) == 2
    assert {x["figi"] for x in out} == {"AAAUSDT", "BBBUSDT"}
    assert all(x["time"] == "t1" for x in out)


def test_expand_ignores_db_ref_shape():
    assert expand_inline_live_payload(24, {"type": "log", "id": 9}) == []


def test_expand_error_alert_payload():
    out = expand_inline_live_payload(
        24,
        {
            "type": "error",
            "message": "HALT: margin_health: mm_rate",
            "time": "2026-07-21T12:00:00Z",
            "source": "session",
        },
    )
    assert len(out) == 1
    assert out[0]["type"] == "error"
    assert out[0]["message"].startswith("HALT:")
    assert out[0]["robot_id"] == 24
