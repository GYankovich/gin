from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .backtest_analytics import derive_payload_metrics, bybit_metrics, general_metrics, moex_metrics, universe_metrics
from .context import AnalysisContext
from .rule_config import RULE_DEFINITIONS, RULE_ENGINE_ENABLED, RULES_VERSION
from .schemas import (
    RecommendationCategory,
    RecommendationItem,
    RecommendationSeverity,
    SuggestedChange,
)

ConditionOp = Literal[">", "<", ">=", "<=", "==", "!="]
Operation = Literal["increase", "decrease", "set", "toggle", "suggest"]


@dataclass
class RuleCondition:
    metric: str
    op: ConditionOp
    value: Any
    and_: List["RuleCondition"] = field(default_factory=list)
    or_: List["RuleCondition"] = field(default_factory=list)


@dataclass
class RecommendationTemplate:
    field: str
    operation: Operation
    value: Any
    reasoning: str
    expected_impact: str


@dataclass
class AnalysisRule:
    id: str
    category: Literal["risk", "performance", "execution", "universe", "market_specific"]
    priority: Literal["critical", "high", "medium", "low"]
    description: str
    when: RuleCondition
    recommendations: List[RecommendationTemplate]


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


def _compare(left: Any, op: ConditionOp, right: Any) -> bool:
    lf = _to_float(left)
    rf = _to_float(right)
    if lf is not None and rf is not None:
        if op == ">":
            return lf > rf
        if op == "<":
            return lf < rf
        if op == ">=":
            return lf >= rf
        if op == "<=":
            return lf <= rf
        if op == "==":
            return lf == rf
        if op == "!=":
            return lf != rf
        return False

    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


def _condition_match(cond: RuleCondition, snapshot: Dict[str, Any]) -> bool:
    val = _nested_get(snapshot, cond.metric)
    if val is None:
        return False
    base = _compare(val, cond.op, cond.value)
    if not base:
        return False
    if cond.and_ and not all(_condition_match(c, snapshot) for c in cond.and_):
        return False
    if cond.or_ and not any(_condition_match(c, snapshot) for c in cond.or_):
        return False
    return True


def _severity(priority: str) -> RecommendationSeverity:
    if priority == "critical":
        return RecommendationSeverity.CRITICAL
    if priority == "high":
        return RecommendationSeverity.WARNING
    return RecommendationSeverity.INFO


def _category(cat: str) -> RecommendationCategory:
    if cat == "risk":
        return RecommendationCategory.RISK
    if cat == "execution":
        return RecommendationCategory.OPERATIONAL
    if cat == "universe":
        return RecommendationCategory.PARAMS
    if cat == "market_specific":
        return RecommendationCategory.STRATEGY
    return RecommendationCategory.BACKTEST


def _current_value(path: str, ctx: AnalysisContext) -> Any:
    if path.startswith("risk."):
        key = path.removeprefix("risk.")
        v = _nested_get(ctx.risk, key)
        if v is not None:
            return v
        aliases = {
            "max_position_size_pct": "max_position_percent",
            "max_position_percent": "max_position_percent",
        }
        alt = aliases.get(key)
        if alt:
            return _nested_get(ctx.risk, alt)
        return None
    if path.startswith("strategy_params."):
        return _nested_get(ctx.strategy_params, path.removeprefix("strategy_params."))
    if path.startswith("execution_model."):
        exec_cfg = ctx.config.get("execution_model") if isinstance(ctx.config, dict) else None
        return _nested_get(exec_cfg or {}, path.removeprefix("execution_model."))
    if path.startswith("costs."):
        costs = ctx.config.get("costs") if isinstance(ctx.config, dict) else None
        return _nested_get(costs or {}, path.removeprefix("costs."))
    if path.startswith("pipeline."):
        pipeline = ctx.config.get("pipeline") if isinstance(ctx.config, dict) else None
        return _nested_get(pipeline or {}, path.removeprefix("pipeline."))
    if path.startswith("bybit."):
        bybit = ctx.config.get("bybit") if isinstance(ctx.config, dict) else None
        return _nested_get(bybit or {}, path.removeprefix("bybit."))
    if path.startswith("crypto_universe."):
        cu = ctx.config.get("crypto_universe") if isinstance(ctx.config, dict) else None
        return _nested_get(cu or {}, path.removeprefix("crypto_universe."))
    return None


def _resolve_suggested_value(
    tpl: RecommendationTemplate,
    ctx: AnalysisContext,
    snapshot: Dict[str, Any],
) -> Any:
    if tpl.operation == "clear_weekday_bit":
        bit = _nested_get(snapshot, "moex.worstWeekdayBit")
        cur = int(_current_value(tpl.field, ctx) or 0)
        if bit is not None:
            return int(cur) & ~int(bit)
        return cur

    if tpl.operation == "narrow_trading_hour":
        worst_hour = _nested_get(snapshot, "general.worstTradingHour")
        if worst_hour is not None:
            return f"exclude_hour_{int(worst_hour)}"
        return tpl.value

    if tpl.operation == "expand_trading_hour":
        best_hour = _nested_get(snapshot, "general.bestTradingHour")
        if best_hour is not None:
            return f"focus_hour_{int(best_hour)}"
        return tpl.value

    suggested_value: Any = tpl.value
    if tpl.operation == "decrease":
        cur = _to_float(_current_value(tpl.field, ctx))
        if cur is not None:
            pct = _to_float(tpl.value) or 0.0
            suggested_value = round(cur * (1.0 - pct), 4)
    elif tpl.operation == "increase":
        cur = _to_float(_current_value(tpl.field, ctx))
        if cur is not None:
            pct = _to_float(tpl.value) or 0.0
            suggested_value = round(cur * (1.0 + pct), 4)
    return suggested_value


def build_metrics_snapshot(ctx: AnalysisContext) -> Dict[str, Any]:
    best = ctx.best_backtest
    lm = ctx.live_metrics or {}
    derived = derive_payload_metrics(ctx.best_backtest_payload, best)
    payload = ctx.best_backtest_payload if isinstance(ctx.best_backtest_payload, dict) else {}
    trades = payload.get("trades") if isinstance(payload.get("trades"), list) else []
    universe = universe_metrics(payload, trades)
    costs = ctx.config.get("costs") if isinstance(ctx.config, dict) else {}
    moex = moex_metrics(
        payload,
        trades,
        risk_config=ctx.risk,
        costs_config=costs if isinstance(costs, dict) else {},
    )
    broker = str(ctx.config.get("broker_type") or "").lower()
    bybit: Dict[str, Any] = {}
    if broker == "bybit":
        slip_pct = 0.0
        exec_cfg = ctx.config.get("execution_model") if isinstance(ctx.config, dict) else {}
        if isinstance(exec_cfg, dict):
            slip_pct = float(exec_cfg.get("slippage_pct") or 0)
        bybit = bybit_metrics(payload, trades, config=ctx.config, slippage_pct=slip_pct)
        bybit_cfg = ctx.config.get("bybit") if isinstance(ctx.config.get("bybit"), dict) else {}
        bybit["instrumentCategory"] = str(bybit_cfg.get("instrument_category") or "linear").lower()
    signals = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    vol_pct = None
    hs = payload.get("history_stats") if isinstance(payload.get("history_stats"), dict) else {}
    vol_pct = _to_float(hs.get("volatilityAnnualPct"))
    general = general_metrics(
        payload,
        trades,
        signals,
        broker_type=broker or "tinvest",
        volatility_annual_pct=vol_pct,
    )
    max_pos = (
        ctx.risk.get("max_position_percent")
        or ctx.risk.get("max_position_size_pct")
        or ctx.strategy_params.get("max_position_size_pct")
    )
    return {
        "backtest": {
            "totalReturnPct": best.total_return_percent if best else None,
            "maxDrawdownPct": best.max_drawdown_percent if best else None,
            "winRatePct": best.win_rate_percent if best else None,
            "tradesTotal": best.trades_total if best else None,
            "sharpe": best.sharpe_ratio if best else None,
            **derived,
        },
        "live": {
            "totalPnl": lm.get("total_pnl"),
            "maxDrawdown": lm.get("max_drawdown"),
            "fillRatePct": lm.get("fill_rate"),
            "closedTrades": lm.get("closed_trades"),
            "signalExecutionRatePct": ctx.signal_execution_rate_pct,
            "riskEvents7d": ctx.risk_events_7d,
        },
        "risk": {
            "maxPositionSizePct": max_pos,
            "maxDailyLossPct": ctx.risk.get("max_daily_loss") or ctx.strategy_params.get("max_daily_loss"),
            "stopLossPct": ctx.risk.get("stop_loss_percent") or ctx.strategy_params.get("stop_loss_percent"),
            "takeProfitPct": ctx.risk.get("take_profit_percent") or ctx.strategy_params.get("take_profit_percent"),
        },
        "strategy": {
            "name": ctx.strategy,
            "interval": ctx.strategy_params.get("interval"),
        },
        "market": {
            "brokerType": str(ctx.config.get("broker_type") or "").lower(),
        },
        "universe": universe,
        "moex": moex,
        "bybit": bybit,
        "general": general,
    }


def _condition_from_dict(raw: Dict[str, Any]) -> RuleCondition:
    return RuleCondition(
        metric=str(raw["metric"]),
        op=raw["op"],
        value=raw.get("value"),
        and_=[_condition_from_dict(x) for x in raw.get("and", [])],
        or_=[_condition_from_dict(x) for x in raw.get("or", [])],
    )


def _rules_from_config() -> List[AnalysisRule]:
    out: List[AnalysisRule] = []
    for raw in RULE_DEFINITIONS:
        out.append(
            AnalysisRule(
                id=str(raw["id"]),
                category=raw["category"],
                priority=raw["priority"],
                description=str(raw["description"]),
                when=_condition_from_dict(raw["when"]),
                recommendations=[
                    RecommendationTemplate(
                        field=str(r["field"]),
                        operation=r["operation"],
                        value=r.get("value"),
                        reasoning=str(r["reasoning"]),
                        expected_impact=str(r["expected_impact"]),
                    )
                    for r in raw.get("recommendations", [])
                ],
            )
        )
    return out


def generate_rule_engine_recommendations(ctx: AnalysisContext) -> List[RecommendationItem]:
    if not RULE_ENGINE_ENABLED:
        return []
    snapshot = build_metrics_snapshot(ctx)
    out: List[RecommendationItem] = []
    rules = _rules_from_config()
    for rule in rules:
        if not _condition_match(rule.when, snapshot):
            continue
        suggested_changes: List[SuggestedChange] = []
        for tpl in rule.recommendations:
            suggested_value = _resolve_suggested_value(tpl, ctx, snapshot)

            suggested_changes.append(
                SuggestedChange(
                    path=tpl.field,
                    current_value=_current_value(tpl.field, ctx),
                    suggested_value=suggested_value,
                    reason=tpl.reasoning,
                )
            )

        out.append(
            RecommendationItem(
                id=f"rule-{rule.id}",
                category=_category(rule.category),
                severity=_severity(rule.priority),
                title=rule.description,
                message=f"{rule.description}. {rule.recommendations[0].expected_impact}",
                suggested_changes=suggested_changes,
                evidence={
                    "rule_id": rule.id,
                    "rules_version": RULES_VERSION,
                    "rule_engine_enabled": RULE_ENGINE_ENABLED,
                    "snapshot": snapshot,
                },
            )
        )
    return out

