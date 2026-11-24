"""Брокерский ключ и секрет запечатываются одним шифром и открываются обратно."""
from app.core.secret_box import is_sealed, open_broker_material, open_secret, seal


def test_seal_roundtrip_hides_the_plaintext():
    sealed = seal("t.super-secret")
    assert sealed is not None
    assert is_sealed(sealed)
    assert "super-secret" not in sealed
    assert open_secret(sealed) == "t.super-secret"
    assert seal(sealed) == sealed


def test_open_leaves_legacy_plaintext():
    assert open_secret("plain-key") == "plain-key"
    assert open_secret(None) is None
    assert seal(None) is None
    assert seal("") == ""


def test_broker_material_prefers_the_column_and_drops_json_secret():
    sealed_key = seal("api-key")
    sealed_secret = seal("api-secret")
    plain, extra = open_broker_material(
        sealed_key,
        sealed_secret,
        {"testnet": False, "token_secret": "stale", "api_secret": "also-stale"},
    )
    assert plain == "api-key"
    assert extra["token_secret"] == "api-secret"
    assert "api_secret" not in extra
    assert extra["testnet"] is False
