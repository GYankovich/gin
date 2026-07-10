from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from .optimization_config import COMMON_RISK_PARAMS, MAX_COMBINATIONS, STRATEGY_PARAM_RANGES

OptimizationGoalType = Literal["balanced", "max_return", "min_drawdown", "max_sharpe"]
OptimizationMode = Literal["speed", "full"]


@dataclass
class BacktestScoreInput:
    total_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe: Optional[float] = None
    win_rate_pct: Optional[float] = None
    trades_total: Optional[int] = None


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _nested_get(data: Dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _nested_set(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def calculate_score(
    metrics: BacktestScoreInput,
    goal: OptimizationGoalType = "balanced",
) -> float:
    ret = _to_float(metrics.total_return_pct) or 0.0
    dd = _to_float(metrics.max_drawdown_pct) or 0.0
    sharpe = _to_float(metrics.sharpe) or 0.0
    wr = _to_float(metrics.win_rate_pct) or 0.0
    trades = int(metrics.trades_total or 0)

    if goal == "max_return":
        score = ret * 0.6 - dd * 0.25 + sharpe * 0.15
    elif goal == "min_drawdown":
        score = -dd * 0.5 + ret * 0.3 + sharpe * 0.2
    elif goal == "max_sharpe":
        score = sharpe * 0.6 - dd * 0.2 + ret * 0.2
    else:
        score = ret * 0.35 - dd * 0.30 + sharpe * 0.20 + wr * 0.15

    if trades < 10:
        score *= 0.5
    if dd > 30:
        score *= 0.7
    return round(score, 4)


def check_overfitting_warnings(ranked: List[Dict[str, Any]]) -> List[str]:
    if not ranked:
        return []
    warnings: List[str] = []
    best = ranked[0]
    if len(ranked) >= 2:
        second_score = _to_float(ranked[1].get("score")) or 0.0
        best_score = _to_float(best.get("score")) or 0.0
        if second_score > 0 and best_score > second_score * 1.2:
            warnings.append("Лучший score > 20% выше второго — возможен overfitting")
    trades = int(best.get("trades_total") or 0)
    if trades < 20:
        warnings.append("Мало сделок у лучшего варианта (< 20) — результат нестабилен")
    sharpe = _to_float(best.get("sharpe"))
    if sharpe is not None and sharpe > 2.5:
        warnings.append("Sharpe > 2.5 — подозрительно высокий результат")
    return warnings


def optimizable_params(config: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
    strategy = str(strategy or "").lower()
    defs = list(COMMON_RISK_PARAMS)
    defs.extend(STRATEGY_PARAM_RANGES.get(strategy, []))
    out: List[Dict[str, Any]] = []
    for spec in defs:
        field = str(spec["field"])
        current = _nested_get(config, field)
        if current is None:
            continue
        cur_f = _to_float(current)
        if cur_f is None:
            continue
        out.append(
            {
                **spec,
                "field": field,
                "current": cur_f,
            }
        )
    return out


def _value_grid(spec: Dict[str, Any], mode: OptimizationMode) -> List[float]:
    lo = float(spec["min"])
    hi = float(spec["max"])
    step = float(spec["step"])
    cur = float(spec.get("current") or lo)
    values: List[float] = []
    v = lo
    while v <= hi + 1e-9:
        values.append(round(v, 6))
        v += step
    if not values:
        return [cur]
    if mode == "speed":
        mid = values[len(values) // 2]
        candidates = sorted({values[0], mid, values[-1], cur})
        narrowed = [x for x in candidates if lo - 1e-9 <= x <= hi + 1e-9]
        return narrowed[:4] or [cur]
    if len(values) > 8:
        stride = max(1, len(values) // 6)
        values = values[::stride]
    if cur not in values:
        values.append(cur)
        values.sort()
    return values[:8]


def _sample_combinations(combos: List[Dict[str, float]], limit: int) -> List[Dict[str, float]]:
    if len(combos) <= limit:
        return combos
    step = max(1, len(combos) // limit)
    sampled = combos[::step][:limit]
    if combos[0] not in sampled:
        sampled[0] = combos[0]
    return sampled[:limit]


def generate_grid_configs(
    base_config: Dict[str, Any],
    strategy: str,
    mode: OptimizationMode = "speed",
) -> List[Dict[str, Any]]:
    params = optimizable_params(base_config, strategy)
    if not params:
        return []
    param_values: Dict[str, List[float]] = {
        p["field"]: _value_grid(p, mode) for p in params
    }
    keys = list(param_values.keys())
    combos: List[Dict[str, float]] = []
    for prod in itertools.product(*[param_values[k] for k in keys]):
        combos.append(dict(zip(keys, prod)))
    limit = MAX_COMBINATIONS.get(mode, 20)
    combos = _sample_combinations(combos, limit)
    out: List[Dict[str, Any]] = []
    for combo in combos:
        cfg = copy.deepcopy(base_config)
        for field, val in combo.items():
            _nested_set(cfg, field, val)
        out.append(cfg)
    return out


def param_summary_from_config(config: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for spec in optimizable_params(config, strategy):
        summary[spec["field"]] = _nested_get(config, spec["field"])
    return summary


def rank_backtest_rows(
    rows: List[Any],
    goal: OptimizationGoalType = "balanced",
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for row in rows:
        run_id = int(row[0])
        metrics = BacktestScoreInput(
            total_return_pct=_to_float(row[6]),
            max_drawdown_pct=_to_float(row[7]),
            win_rate_pct=_to_float(row[8]),
            trades_total=int(row[9] or 0) if row[9] is not None else None,
            sharpe=_to_float(row[10]),
        )
        score = calculate_score(metrics, goal)
        snap = row[4] if isinstance(row[4], dict) else {}
        strategy = str((snap or {}).get("strategy") or "")
        ranked.append(
            {
                "run_id": run_id,
                "score": score,
                "total_return_percent": metrics.total_return_pct,
                "max_drawdown_percent": metrics.max_drawdown_pct,
                "win_rate_percent": metrics.win_rate_pct,
                "trades_total": metrics.trades_total,
                "sharpe_ratio": metrics.sharpe,
                "requested_from": row[2],
                "requested_to": row[3],
                "started_at": row[5],
                "param_summary": param_summary_from_config(snap, strategy) if snap else {},
                "config_snapshot": snap,
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i
    return ranked
