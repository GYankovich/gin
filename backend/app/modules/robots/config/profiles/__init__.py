"""Profile registry for robot config validation."""

from __future__ import annotations

from typing import Any, Dict, Type, Union

from app.modules.robots.config.profiles.type1_bybit import Type1BybitConfig
from app.modules.robots.config.profiles.type1_tinvest import Type1TinvestConfig
from app.modules.robots.config.profiles.type2_bybit import Type2BybitConfig
from app.modules.robots.config.profiles.type2_tinvest import Type2TinvestConfig

RobotConfigUnion = Union[Type1TinvestConfig, Type1BybitConfig, Type2TinvestConfig, Type2BybitConfig]

PROFILE_REGISTRY: Dict[str, Type[Type1TinvestConfig] | Type[Type1BybitConfig] | Type[Type2TinvestConfig] | Type[Type2BybitConfig]] = {
    "type1_tinvest": Type1TinvestConfig,
    "type1_bybit": Type1BybitConfig,
    "type2_tinvest": Type2TinvestConfig,
    "type2_bybit": Type2BybitConfig,
}


def resolve_schema_profile(
    robot_type: int,
    raw: Dict[str, Any],
    broker_type: str | None = None,
) -> str:
    cfg = dict(raw or {})
    broker = str(broker_type or cfg.get("broker_type") or "tinvest").strip().lower()
    if robot_type == 1 and broker == "tinvest":
        return "type1_tinvest"
    if robot_type == 1 and broker == "bybit":
        return "type1_bybit"
    if robot_type == 2 and broker in ("tinvest", "sandbox"):
        return "type2_tinvest"
    if robot_type == 2 and broker == "bybit":
        return "type2_bybit"
    raise ValueError(f"Unsupported schema profile for robot_type={robot_type}, broker_type={broker!r}")


def validate_robot_config(
    robot_type: int,
    raw: Dict[str, Any],
    *,
    broker_type: str | None = None,
) -> RobotConfigUnion:
    payload = dict(raw or {})
    broker = str(broker_type or payload.get("broker_type") or "tinvest").strip().lower()
    if int(robot_type) == 2 and broker in ("tinvest", "sandbox"):
        from app.modules.robots.config.migration import migrate_v2_to_v3

        normalized = migrate_v2_to_v3(payload, robot_type=robot_type, broker_type=broker)
        if broker == "sandbox":
            normalized["broker_type"] = "sandbox"
    else:
        normalized = payload
    profile = resolve_schema_profile(int(robot_type), normalized, broker_type)
    model_cls = PROFILE_REGISTRY[profile]
    return model_cls.model_validate(normalized)


def dump_robot_config(model: RobotConfigUnion) -> Dict[str, Any]:
    """Serialize profile model to robots.config JSON payload."""
    raw = model.model_dump()
    profile = str(getattr(model, "schema_profile", "") or raw.get("schema_profile") or "")
    broker = str(getattr(model, "broker_type", "") or raw.get("broker_type") or "").lower()
    if profile == "type2_bybit" or broker == "bybit":
        from app.modules.robots.universe import strip_moex_eod_flatten_from_config

        return strip_moex_eod_flatten_from_config(raw)
    return raw


def export_config_schema(schema_profile: str) -> Dict[str, Any]:
    """JSON Schema профиля для UI / OpenAPI tooling."""
    key = str(schema_profile or "").strip()
    model_cls = PROFILE_REGISTRY.get(key)
    if model_cls is None:
        raise KeyError(key)
    return model_cls.model_json_schema()


__all__ = [
    "RobotConfigUnion",
    "PROFILE_REGISTRY",
    "resolve_schema_profile",
    "validate_robot_config",
    "dump_robot_config",
    "export_config_schema",
]
