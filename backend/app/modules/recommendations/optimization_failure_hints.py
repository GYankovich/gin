from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_REJECT_PREFIX_RULES: List[Tuple[str, str, str, float]] = [
    ("volume_below_min", "crypto_universe.min_volume_24h_usd", "decrease", 0.35),
    ("spread_above_max", "crypto_universe.max_spread_bps", "increase", 0.35),
    ("price_below_min", "crypto_universe.min_last_price", "decrease", 0.35),
    ("funding_below_min", "crypto_universe.min_funding_rate", "decrease", 0.35),
    ("funding_above_max", "crypto_universe.max_funding_rate", "increase", 0.35),
    ("oi_below_min", "crypto_universe.min_open_interest_usd", "decrease", 0.35),
    ("lsr_below_min", "crypto_universe.min_lsr", "decrease", 0.35),
    ("lsr_above_max", "crypto_universe.max_lsr", "increase", 0.35),
    ("rvol_below_min", "crypto_universe.min_rvol", "decrease", 0.35),
    ("atr_below_min", "crypto_universe.min_atr_percent", "decrease", 0.35),
    ("atr_above_max", "crypto_universe.max_atr_percent", "increase", 0.35),
]

_DEFAULTS: Dict[str, float] = {
    "crypto_universe.min_volume_24h_usd": 50_000_000.0,
    "crypto_universe.max_spread_bps": 15.0,
    "crypto_universe.min_last_price": 0.01,
    "crypto_universe.min_funding_rate": -0.01,
    "crypto_universe.max_funding_rate": 0.01,
    "crypto_universe.min_open_interest_usd": 10_000_000.0,
    "crypto_universe.min_lsr": 0.8,
    "crypto_universe.max_lsr": 1.5,
    "crypto_universe.min_rvol": 1.0,
    "crypto_universe.min_atr_percent": 1.0,
    "crypto_universe.max_atr_percent": 15.0,
}

_REASON_LABELS: Dict[str, str] = {
    "volume_below_min": "объём 24h ниже порога",
    "spread_above_max": "спред выше допустимого",
    "price_below_min": "цена ниже минимума",
    "funding_below_min": "funding rate ниже минимума",
    "funding_above_max": "funding rate выше максимума",
    "oi_below_min": "open interest ниже порога",
    "lsr_below_min": "long/short ratio ниже минимума",
    "lsr_above_max": "long/short ratio выше максимума",
    "rvol_below_min": "относительный объём ниже порога",
    "atr_below_min": "ATR% ниже минимума",
    "atr_above_max": "ATR% выше максимума",
}


def _nested_get(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def parse_top_rejects(error_message: str) -> Dict[str, int]:
    if not error_message:
        return {}
    match = re.search(r"top_rejects=([^)]+)", error_message)
    if not match:
        return {}
    out: Dict[str, int] = {}
    for part in match.group(1).split(";"):
        chunk = part.strip()
        if " x" not in chunk:
            continue
        key, cnt = chunk.rsplit(" x", 1)
        key = key.strip()
        try:
            out[key] = int(cnt.strip())
        except ValueError:
            continue
    return out


def classify_backtest_failure(error_message: Optional[str]) -> str:
    msg = str(error_message or "").strip()
    if not msg:
        return "unknown"
    if "Нет бумаг для бэктеста" in msg:
        return "no_universe"
    if "Ошибка загрузки данных" in msg or "enqueue-failed" in msg:
        return "data_load"
    if "persist-failed" in msg:
        return "persist"
    return "other"


def _normalize_reject_key(reason: str) -> str:
    base = str(reason or "").strip()
    if ":" in base:
        base = base.split(":", 1)[0]
    return base


def _match_rule(reject_key: str) -> Optional[Tuple[str, str, float]]:
    norm = _normalize_reject_key(reject_key)
    for prefix, path, operation, delta_pct in _REJECT_PREFIX_RULES:
        if norm == prefix or norm.startswith(f"{prefix}:"):
            return path, operation, delta_pct
    return None


def _round_suggested(path: str, value: float) -> float:
    if "volume" in path or "interest" in path:
        step = 100_000.0
        return max(0.0, round(value / step) * step)
    if "spread_bps" in path:
        return max(0.0, round(value * 10) / 10)
    if "funding_rate" in path:
        return round(value, 6)
    if path.endswith("_lsr") or "lsr" in path:
        return round(value, 4)
    if "percent" in path or "rvol" in path:
        return round(value, 4)
    return round(value, 6)


def _suggest_value(path: str, current: Optional[float], operation: str, delta_pct: float) -> float:
    base = float(current if current is not None else _DEFAULTS.get(path, 1.0))
    if operation == "decrease":
        next_val = base * (1.0 - delta_pct)
    else:
        next_val = base * (1.0 + delta_pct)
    return _round_suggested(path, next_val)


def build_suggested_changes(
    top_rejects: Dict[str, int],
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if not top_rejects:
        return []
    cfg = config if isinstance(config, dict) else {}
    ordered = sorted(top_rejects.items(), key=lambda x: x[1], reverse=True)
    seen_paths: set[str] = set()
    out: List[Dict[str, Any]] = []
    for reject_key, count in ordered:
        rule = _match_rule(reject_key)
        if not rule:
            continue
        path, operation, delta_pct = rule
        if path in seen_paths:
            continue
        seen_paths.add(path)
        current = _nested_get(cfg, path)
        if current is None and path.startswith("crypto_universe."):
            cu = cfg.get("crypto_universe") if isinstance(cfg.get("crypto_universe"), dict) else {}
            leaf = path.removeprefix("crypto_universe.")
            current = cu.get(leaf)
        suggested = _suggest_value(path, _to_float(current), operation, delta_pct)
        label = _REASON_LABELS.get(_normalize_reject_key(reject_key), reject_key)
        verb = "Снизить" if operation == "decrease" else "Повысить"
        out.append(
            {
                "path": path,
                "current_value": current,
                "suggested_value": suggested,
                "reason": f"{verb} ({label}; отклонений: {count})",
            }
        )
    return out


def build_failure_insights(
    error_message: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    msg = str(error_message or "").strip()
    category = classify_backtest_failure(msg)
    top_rejects = parse_top_rejects(msg)
    suggested = build_suggested_changes(top_rejects, config) if category == "no_universe" else []
    if category == "no_universe" and not suggested:
        broker = str((config or {}).get("broker_type") or "").lower()
        has_crypto_universe = isinstance((config or {}).get("crypto_universe"), dict)
        if broker == "bybit" or has_crypto_universe:
            suggested = build_suggested_changes(
                {"volume_below_min": 1, "spread_above_max": 1},
                config,
            )
    summary = msg
    if category == "no_universe" and top_rejects and not suggested:
        summary = f"{msg} — смягчите фильтры crypto-universe"
    return {
        "failure_category": category,
        "failure_summary": summary[:500] if summary else None,
        "top_rejects": top_rejects,
        "suggested_changes": suggested,
    }


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
