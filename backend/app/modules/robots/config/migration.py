"""Миграция config v1 (pipeline/universe_mode) → v2 (П1/П2/П3)."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Tuple

from app.modules.robots.config.v2_schema import (
    CONFIG_VERSION_V2,
    HISTORICAL_FILTER_TYPES,
    PAPER_FILTER_TYPES,
    HistoricalScreeningConfig,
    PaperSelectionConfig,
    RefreshSchedule,
    SignalGenerationConfig,
    TradingRobotConfigV2,
)
from app.modules.robots.trading.intervals import DEFAULT_MOEX_ANALYSIS_INTERVAL

CONFIG_VERSION_V3 = 3

_DEFAULT_PIPELINE_FILTERS: List[Dict[str, Any]] = [
    {"type": "security_status", "eq": "A", "direction": "BOTH"},
    {"type": "trading_status", "eq": "T", "direction": "BOTH"},
    {"type": "volume", "min": 50_000_000, "direction": "BOTH"},
    {"type": "num_trades", "min": 100, "direction": "BOTH"},
    {"type": "gap", "max_percent": 2.5, "direction": "BOTH"},
    {"type": "spread", "max_percent": 0.15, "direction": "BOTH"},
    {"type": "atr", "min_percent": 1.5, "period": 14, "direction": "BOTH"},
    {"type": "turnover", "min_percent": 0.1, "direction": "BOTH"},
    {"type": "gap_retention", "min_ratio": 0.5, "direction": "BOTH"},
]

_DEFAULT_HISTORICAL_ATR_FILTER: Dict[str, Any] = {
    "type": "atr",
    "min_percent": 1.5,
    "period": 14,
    "direction": "BOTH",
}


def config_json_dumps(cfg: Dict[str, Any]) -> str:
    """Стабильная сериализация для сравнения до/после миграции."""
    return json.dumps(cfg or {}, ensure_ascii=False, sort_keys=True, default=str)


def config_equals(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return config_json_dumps(a) == config_json_dumps(b)


def repair_v2_filter_split(data: Dict[str, Any]) -> Dict[str, Any]:
    """Переразнести pipeline.filters в historical_screening / paper_selection."""
    out = copy.deepcopy(dict(data or {}))
    hs = dict(out.get("historical_screening") or {})
    ps = dict(out.get("paper_selection") or {})
    pipeline = dict(out.get("pipeline") or {})
    hist_f = list(hs.get("filters") or [])
    paper_f = list(ps.get("filters") or [])
    combined = hist_f + paper_f
    if not combined:
        combined = list(pipeline.get("filters") or [])
    if not combined:
        return out
    h, p = _split_pipeline_filters(combined)
    hs["filters"] = h
    ps["filters"] = p
    out["historical_screening"] = hs
    out["paper_selection"] = ps
    return out


def _split_pipeline_filters(
    filters: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    historical: List[Dict[str, Any]] = []
    paper: List[Dict[str, Any]] = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        ftype = str(f.get("type") or "").strip().lower()
        if ftype in HISTORICAL_FILTER_TYPES:
            historical.append(dict(f))
        elif ftype in PAPER_FILTER_TYPES or not ftype:
            paper.append(dict(f))
        else:
            paper.append(dict(f))
    return historical, paper


def _legacy_universe_mode(raw: Dict[str, Any]) -> str:
    from app.modules.robots.universe import CRYPTO_UNIVERSE_MODES, is_crypto_type2_config

    mode = str(raw.get("universe_mode") or "dms_pipeline").strip().lower()
    if is_crypto_type2_config(raw) and mode in CRYPTO_UNIVERSE_MODES:
        return mode
    if mode in ("fixed", "dms_pipeline", "tqbr_scan"):
        return mode
    fixed = raw.get("fixed_tickers") or []
    if isinstance(fixed, list) and fixed:
        return "fixed"
    return "dms_pipeline"


def migrate_legacy_to_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Построить блоки v2 из legacy-конфига (idempotent для уже v2)."""
    data = copy.deepcopy(dict(raw or {}))
    if int(data.get("config_version") or 0) >= CONFIG_VERSION_V2:
        if all(k in data for k in ("historical_screening", "paper_selection", "signal_generation")):
            return sync_legacy_from_v2(data)

    pipeline = dict(data.get("pipeline") or {})
    pipeline_filters = list(pipeline.get("filters") or _DEFAULT_PIPELINE_FILTERS)
    hist_filters, paper_filters = _split_pipeline_filters(pipeline_filters)
    mode = _legacy_universe_mode(data)
    fixed = [
        str(x).strip().upper()
        for x in (data.get("fixed_tickers") or [])
        if str(x).strip()
    ]
    universe_refresh = max(0, int(data.get("universe_refresh_minutes") or 0))

    sp = dict(data.get("strategy_params") or {})
    strategy = str(data.get("strategy") or "grain_seed").strip().lower()
    broker = str(data.get("broker_type") or sp.get("broker_type") or "tinvest").strip().lower()

    if mode == "fixed":
        historical = HistoricalScreeningConfig(
            enabled=False,
            universe="fixed",
            fixed_tickers=fixed,
            filters=[],
        )
        paper = PaperSelectionConfig(
            enabled=True,
            input="fixed",
            fixed_tickers=fixed,
            mode=str(pipeline.get("mode") or "ALL").upper(),  # type: ignore[arg-type]
            filters=paper_filters,
            refresh=RefreshSchedule(
                every_minutes=universe_refresh or 30,
                only_trading_hours=True,
            ),
        )
    elif mode == "tqbr_scan":
        historical = HistoricalScreeningConfig(
            enabled=True,
            universe="tqbr_all",
            interval=str(sp.get("moex_analysis_interval") or DEFAULT_MOEX_ANALYSIS_INTERVAL),
            lookback_days=max(7, int(sp.get("candle_days") or 14)),
            filters=hist_filters or [
                {"type": "atr", "min_percent": 1.5, "period": 14, "direction": "BOTH"},
            ],
            refresh=RefreshSchedule(every_minutes=0, daily_at_msk="07:00"),
        )
        paper = PaperSelectionConfig(
            enabled=True,
            input="candidate_pool",
            mode=str(pipeline.get("mode") or "ALL").upper(),  # type: ignore[arg-type]
            filters=paper_filters,
            refresh=RefreshSchedule(
                every_minutes=universe_refresh or 30,
                only_trading_hours=True,
            ),
        )
    else:
        # dms_pipeline → П1 (MOEX) + П2 (candidate_pool); ATR по умолчанию в П1
        if not hist_filters:
            hist_filters = [dict(_DEFAULT_HISTORICAL_ATR_FILTER)]
        historical = HistoricalScreeningConfig(
            enabled=True,
            universe="tqbr_all",
            interval=str(sp.get("moex_analysis_interval") or DEFAULT_MOEX_ANALYSIS_INTERVAL),
            lookback_days=max(7, int(sp.get("candle_days") or 14)),
            filters=hist_filters,
            refresh=RefreshSchedule(every_minutes=0, daily_at_msk="07:00"),
        )
        paper = PaperSelectionConfig(
            enabled=True,
            input="candidate_pool",
            mode=str(pipeline.get("mode") or "ALL").upper(),  # type: ignore[arg-type]
            filters=paper_filters,
            refresh=RefreshSchedule(
                every_minutes=universe_refresh or 30,
                only_trading_hours=True,
            ),
        )

    signal = SignalGenerationConfig(
        strategy=strategy,
        params=sp,
        data_source=broker if broker in ("tinvest", "vtb", "alfa") else "tinvest",
        update_interval_seconds=max(1, int(data.get("update_interval_seconds") or 10)),
        indicator_update_schedule=dict(
            data.get("indicator_update_schedule")
            or {
                "CANDLE_INTERVAL_DAY": "10:00 MSK",
                "CANDLE_INTERVAL_HOUR": "every hour at :05",
            }
        ),
    )

    v2 = TradingRobotConfigV2(
        config_version=CONFIG_VERSION_V2,
        historical_screening=historical,
        paper_selection=paper,
        signal_generation=signal,
        allowed_figis=list(data.get("allowed_figis") or []),
        risk=dict(data.get("risk") or {}),
        costs=dict(data.get("costs") or {}),
        execution_model=data.get("execution_model"),
    )
    out = v2.model_dump()
    return sync_legacy_from_v2(out)


def sync_legacy_from_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Заполнить legacy-поля из v2 (для старого кода и UI)."""
    out = copy.deepcopy(dict(data or {}))
    out["config_version"] = CONFIG_VERSION_V2

    hs = dict(out.get("historical_screening") or {})
    ps = dict(out.get("paper_selection") or {})
    sg = dict(out.get("signal_generation") or {})

    hist_filters = list(hs.get("filters") or [])
    paper_filters = list(ps.get("filters") or [])
    combined_filters = hist_filters + paper_filters

    strategy = str(sg.get("strategy") or out.get("strategy") or "grain_seed")
    params = dict(sg.get("params") or out.get("strategy_params") or {})
    if hs.get("interval") and not params.get("moex_analysis_interval"):
        params["moex_analysis_interval"] = hs.get("interval")
    if hs.get("lookback_days") and not params.get("candle_days"):
        params["candle_days"] = hs.get("lookback_days")

    paper_input = str(ps.get("input") or "candidate_pool")
    fixed = list(ps.get("fixed_tickers") or hs.get("fixed_tickers") or [])
    hist_enabled = bool(hs.get("enabled", True))
    hist_universe = str(hs.get("universe") or "tqbr_all")

    if paper_input == "fixed" or (not hist_enabled and fixed):
        universe_mode = "fixed"
    elif hist_enabled and hist_universe == "tqbr_all" and hist_filters:
        universe_mode = "tqbr_scan"
    else:
        universe_mode = "dms_pipeline"

    paper_refresh = dict(ps.get("refresh") or {})
    universe_refresh_minutes = max(
        0,
        int(
            paper_refresh.get("every_minutes")
            or out.get("universe_refresh_minutes")
            or 0
        ),
    )

    broker = str(out.get("broker_type") or sg.get("data_source") or "tinvest")

    out.update({
        "strategy": strategy,
        "strategy_params": params,
        "broker_type": broker,
        "pipeline": {
            "mode": str(ps.get("mode") or "ALL"),
            "filters": combined_filters if combined_filters else paper_filters,
        },
        "universe_mode": universe_mode,
        "fixed_tickers": fixed,
        "universe_refresh_minutes": universe_refresh_minutes,
        "update_interval_seconds": int(sg.get("update_interval_seconds") or 10),
        "indicator_update_schedule": dict(sg.get("indicator_update_schedule") or {}),
    })
    return out


def merge_config_v2(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Глубокое слияние patch в config с последующей нормализацией v2."""
    out = copy.deepcopy(dict(base or {}))
    inc = dict(patch or {})

    for key in (
        "historical_screening",
        "paper_selection",
        "signal_generation",
        "risk",
        "costs",
        "execution_model",
        "allowed_figis",
    ):
        if key not in inc:
            continue
        val = inc[key]
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            merged.update(val)
            out[key] = merged
        else:
            out[key] = val

    for key in (
        "strategy",
        "broker_type",
        "strategy_params",
        "pipeline",
        "universe_mode",
        "fixed_tickers",
        "universe_refresh_minutes",
        "update_interval_seconds",
        "indicator_update_schedule",
    ):
        if key in inc and inc[key] is not None:
            out[key] = inc[key]

    return ensure_config_v2(out)


def ensure_config_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализовать конфиг: v2 + legacy-зеркало."""
    from app.modules.robots.universe import is_crypto_type2_config

    data = repair_v2_filter_split(copy.deepcopy(dict(raw or {})))
    if is_crypto_type2_config(data):
        return data
    if int(data.get("config_version") or 0) >= CONFIG_VERSION_V2 and all(
        k in data for k in ("historical_screening", "paper_selection", "signal_generation")
    ):
        try:
            validated = TradingRobotConfigV2.model_validate(data)
            merged = sync_legacy_from_v2(validated.model_dump())
        except Exception:
            merged = sync_legacy_from_v2(data)
    else:
        merged = migrate_legacy_to_v2(data)

    try:
        TradingRobotConfigV2.model_validate(merged)
    except Exception:
        merged = migrate_legacy_to_v2(merged)
    return sync_legacy_from_v2(merged)


def resolve_schema_profile_v3(
    *,
    robot_type: int,
    config: Dict[str, Any],
    broker_type: Optional[str] = None,
) -> str:
    bt = str(broker_type or (config or {}).get("broker_type") or "tinvest").strip().lower()
    if int(robot_type) == 2 and bt == "sandbox":
        return "type2_tinvest"
    return f"type{int(robot_type)}_{bt}"


def migrate_v2_to_v3(
    raw: Dict[str, Any],
    *,
    robot_type: int,
    broker_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Проставить поля v3 поверх нормализованного v2 конфига.

    На этапе R2.4 runtime остаётся обратно совместимым с v2-полями;
    миграция добавляет `config_version=3` и `schema_profile`.
    """
    cfg = ensure_config_v2(raw or {})
    profile = resolve_schema_profile_v3(
        robot_type=robot_type,
        config=cfg,
        broker_type=broker_type,
    )
    cfg["config_version"] = CONFIG_VERSION_V3
    cfg["schema_profile"] = profile
    if int(robot_type) == 2 and str(cfg.get("broker_type") or "tinvest").lower() == "tinvest":
        cfg.setdefault("instrument_id_type", "figi")
    return cfg


def migrate_robot_config_row(config: Any) -> tuple[Dict[str, Any], bool]:
    """Нормализовать config из БД; второй элемент — нужен ли UPDATE."""
    if isinstance(config, str):
        try:
            raw = json.loads(config)
        except json.JSONDecodeError:
            raw = {}
    elif isinstance(config, dict):
        raw = dict(config)
    else:
        raw = {}
    normalized = ensure_config_v2(raw)
    return normalized, not config_equals(raw, normalized)


def effective_pipeline_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pipeline для DMS/history-backtest из v2 или legacy."""
    cfg = ensure_config_v2(config)
    ps = cfg.get("paper_selection") or {}
    return {
        "mode": str(ps.get("mode") or (cfg.get("pipeline") or {}).get("mode") or "ALL"),
        "filters": list(ps.get("filters") or (cfg.get("pipeline") or {}).get("filters") or []),
    }


def effective_universe_mode_from_config(config: Dict[str, Any]) -> str:
    cfg = ensure_config_v2(config)
    return str(cfg.get("universe_mode") or "dms_pipeline")


def historical_screening_from_config(config: Dict[str, Any]) -> HistoricalScreeningConfig:
    cfg = ensure_config_v2(config)
    return HistoricalScreeningConfig.model_validate(cfg.get("historical_screening") or {})


def paper_selection_from_config(config: Dict[str, Any]) -> PaperSelectionConfig:
    cfg = ensure_config_v2(config)
    return PaperSelectionConfig.model_validate(cfg.get("paper_selection") or {})


def signal_generation_from_config(config: Dict[str, Any]) -> SignalGenerationConfig:
    cfg = ensure_config_v2(config)
    return SignalGenerationConfig.model_validate(cfg.get("signal_generation") or {})
