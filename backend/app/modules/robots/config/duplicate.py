"""Build config for POST /robots/duplicate (§7.8)."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from app.modules.robots.trading.brokers.routing import normalize_broker_type

ALLOWED_COPY_SECTIONS = frozenset({"signal_generation", "risk", "costs", "schedule"})
ALLOWED_RESET_SECTIONS = frozenset({
    "universe",
    "allowed_figis",
    "allowed_symbols",
    "candidate_pool",
})

DEFAULT_COPY_SECTIONS: List[str] = ["signal_generation", "risk", "costs", "schedule"]
DEFAULT_RESET_SECTIONS: List[str] = [
    "universe",
    "allowed_figis",
    "allowed_symbols",
    "candidate_pool",
]

_SHARED_RISK_KEYS = (
    "stop_loss_percent",
    "take_profit_percent",
    "max_position_percent",
    "max_position_rub",
    "max_daily_loss",
    "min_trade_amount_rub",
)


def validate_duplicate_sections(
    copy_sections: List[str],
    reset_sections: List[str],
) -> None:
    invalid_copy = set(copy_sections) - ALLOWED_COPY_SECTIONS
    if invalid_copy:
        raise ValueError(f"Invalid copy_sections: {sorted(invalid_copy)}")
    invalid_reset = set(reset_sections) - ALLOWED_RESET_SECTIONS
    if invalid_reset:
        raise ValueError(f"Invalid reset_sections: {sorted(invalid_reset)}")


def _profile_shell(robot_type: int, broker_type: str) -> Dict[str, Any]:
    from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config

    model = validate_robot_config(
        robot_type=int(robot_type),
        raw={},
        broker_type=broker_type,
    )
    return dump_robot_config(model)


def _copy_signal_generation(
    target: Dict[str, Any],
    source: Dict[str, Any],
    target_broker: str,
) -> None:
    src_sg = source.get("signal_generation")
    if isinstance(src_sg, dict):
        target["signal_generation"] = copy.deepcopy(src_sg)
    strategy = source.get("strategy")
    params = source.get("strategy_params")
    if strategy:
        target["strategy"] = strategy
    if isinstance(params, dict):
        target["strategy_params"] = copy.deepcopy(params)
    if target_broker == "bybit":
        sg = dict(target.get("signal_generation") or {})
        if strategy:
            sg["strategy"] = str(strategy)
        if isinstance(params, dict) and params:
            sg["params"] = copy.deepcopy(params)
        if sg:
            target["signal_generation"] = sg


def _copy_risk(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    src_risk = source.get("risk")
    if not isinstance(src_risk, dict):
        return
    dst_risk = dict(target.get("risk") or {})
    for key in _SHARED_RISK_KEYS:
        if key in src_risk:
            dst_risk[key] = src_risk[key]
    if dst_risk:
        target["risk"] = dst_risk


def _copy_costs(
    target: Dict[str, Any],
    source: Dict[str, Any],
    *,
    target_broker: str,
    source_broker: str,
) -> None:
    src_costs = source.get("costs")
    if not isinstance(src_costs, dict):
        return
    if target_broker == source_broker:
        target["costs"] = copy.deepcopy(src_costs)
        return
    dst_costs = dict(target.get("costs") or {})
    if target_broker == "bybit":
        for key in ("maker_fee_rate", "taker_fee_rate", "funding_rate_enabled"):
            if key in src_costs:
                dst_costs[key] = src_costs[key]
    elif target_broker == "tinvest":
        for key in ("broker_commission_rate", "ndfl_rate"):
            if key in src_costs:
                dst_costs[key] = src_costs[key]
    if dst_costs:
        target["costs"] = dst_costs


def apply_reset_sections(
    cfg: Dict[str, Any],
    reset_sections: List[str],
    *,
    robot_type: int,
    target_broker: str,
) -> None:
    if "candidate_pool" in reset_sections:
        cfg.pop("candidate_pool", None)

    if "allowed_figis" in reset_sections:
        cfg["allowed_figis"] = []

    if "allowed_symbols" in reset_sections:
        cfg["allowed_symbols"] = []
        cfg["instruments"] = []
        cfg["fixed_tickers"] = []

    if "universe" in reset_sections:
        cfg.pop("historical_screening", None)
        cfg.pop("paper_selection", None)
        cfg.pop("daily_universe", None)
        cfg.pop("instrument_map", None)
        cfg.pop("universe_refresh_minutes", None)
        if target_broker == "bybit":
            cfg["universe_mode"] = "fixed"
            cfg.setdefault("crypto_universe", {"enabled": False})
        elif int(robot_type) == 2:
            cfg["universe_mode"] = "dms_pipeline"
            cfg["allowed_figis"] = []
            cfg["fixed_tickers"] = []


def resolve_schedule_from_source(
    source_config: Dict[str, Any],
    source_schedule: Optional[Dict[str, Any]],
    *,
    copy_schedule: bool,
) -> Tuple[float, str, str, int]:
    if not copy_schedule:
        return (5 / 60, "10:00", "18:45", 31)

    schedule = source_schedule or {}
    risk = source_config.get("risk") if isinstance(source_config.get("risk"), dict) else {}

    interval_seconds = schedule.get("interval_seconds")
    if interval_seconds is not None:
        poll_h = max(1 / 60, float(interval_seconds) / 3600.0)
    else:
        poll_h = max(1 / 60, float(source_config.get("poll_interval_hours") or (5 / 60)))

    def _hhmm(raw: Any, fallback: str) -> str:
        text = str(raw or "").replace(" MSK", "").strip()
        parts = text.split(":")
        if len(parts) >= 2:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
        return fallback

    start = _hhmm(risk.get("trading_hours_start"), _hhmm(schedule.get("start_time"), "10:00"))
    end = _hhmm(risk.get("trading_hours_end"), _hhmm(schedule.get("end_time"), "18:45"))
    weekdays = int(risk.get("allowed_weekdays") or schedule.get("weekdays") or 31)
    return poll_h, start, end, max(0, min(127, weekdays))


def build_duplicated_config(
    *,
    robot_type: int,
    source_config: Dict[str, Any],
    target_broker: str,
    copy_sections: Optional[List[str]] = None,
    reset_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Merge source config into a new robot config for the target broker profile."""
    copy_list = list(copy_sections or DEFAULT_COPY_SECTIONS)
    reset_list = list(reset_sections or DEFAULT_RESET_SECTIONS)
    validate_duplicate_sections(copy_list, reset_list)

    source = dict(source_config or {})
    source_broker = normalize_broker_type(str(source.get("broker_type") or "tinvest"))
    broker = normalize_broker_type(str(target_broker or source_broker))

    if broker != source_broker:
        cfg = _profile_shell(robot_type, broker)
    else:
        cfg = copy.deepcopy(source)

    if "signal_generation" in copy_list:
        _copy_signal_generation(cfg, source, broker)
    if "risk" in copy_list:
        _copy_risk(cfg, source)
    if "costs" in copy_list:
        _copy_costs(cfg, source, target_broker=broker, source_broker=source_broker)

    apply_reset_sections(cfg, reset_list, robot_type=robot_type, target_broker=broker)

    from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config

    model = validate_robot_config(
        robot_type=int(robot_type),
        raw=cfg,
        broker_type=broker,
    )
    return dump_robot_config(model)


__all__ = [
    "ALLOWED_COPY_SECTIONS",
    "ALLOWED_RESET_SECTIONS",
    "DEFAULT_COPY_SECTIONS",
    "DEFAULT_RESET_SECTIONS",
    "apply_reset_sections",
    "build_duplicated_config",
    "resolve_schedule_from_source",
    "validate_duplicate_sections",
]
