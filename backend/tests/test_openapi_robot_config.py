"""OpenAPI oneOf for robot config profiles (R8.7)."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")


def test_openapi_robot_validate_config_has_config_profile_oneof():
    from app.main import app

    openapi = app.openapi()
    schema = openapi["components"]["schemas"]["RobotValidateConfigResponse"]
    normalized = schema["properties"]["normalized_config"]
    assert "oneOf" in normalized or "anyOf" in normalized
    discriminator = normalized.get("discriminator") or {}
    assert discriminator.get("propertyName") == "schema_profile"
    mapping = discriminator.get("mapping") or {}
    assert "type2_tinvest" in mapping
    assert "type2_bybit" in mapping
    assert "type1_tinvest" in mapping
    assert "type1_bybit" in mapping


def test_openapi_exports_profile_schema_components():
    from app.main import app

    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    for key in ("Type1TinvestConfig", "Type1BybitConfig", "Type2TinvestConfig", "Type2BybitConfig"):
        assert key in components
