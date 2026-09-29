"""OpenAPI: robots_v2 is the sole robots HTTP surface (v1 router unmounted)."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")


def test_openapi_robots_v2_paths_present():
    from app.main import app

    openapi = app.openapi()
    paths = openapi.get("paths") or {}
    assert "/api/v2/robots/create" in paths
    assert "/api/v2/robots/module" in paths
    # Legacy v1 HTTP validate-config schema is gone with the unmounted router
    schemas = (openapi.get("components") or {}).get("schemas") or {}
    assert "RobotValidateConfigResponse" not in schemas


def test_openapi_exports_v2_robot_schemas():
    from app.main import app

    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    for key in (
        "RobotV2CreateRequest",
        "RobotV2Response",
        "RobotV2ValidateRequest",
        "RobotV2BacktestRequest",
    ):
        assert key in components
