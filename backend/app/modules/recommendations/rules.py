from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .context import AnalysisContext
from .schemas import (
    RecommendationCategory,
    RecommendationItem,
    RecommendationSeverity,
    SuggestedChange,
)
from .rule_config import MAX_INFO_RECOMMENDATIONS, MAX_WARNING_RECOMMENDATIONS
from .rule_engine import generate_rule_engine_recommendations


def _rid(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in (prefix, *parts))
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _nested_diff(
    base: Dict[str, Any],
    other: Dict[str, Any],
    prefix: str = "",
) -> List[Tuple[str, Any, Any]]:
    diffs: List[Tuple[str, Any, Any]] = []
    keys = set(base.keys()) | set(other.keys())
    for k in sorted(keys):
        path = f"{prefix}.{k}" if prefix else k
        bv = base.get(k)
        ov = other.get(k)
        if isinstance(bv, dict) and isinstance(ov, dict):
            diffs.extend(_nested_diff(bv, ov, path))
        elif bv != ov:
            diffs.append((path, bv, ov))
    return diffs


def _item(
    prefix: str,
    category: RecommendationCategory,
    severity: RecommendationSeverity,
    title: str,
    message: str,
    *,
    suggested_changes: Optional[List[SuggestedChange]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    key: str = "",
) -> RecommendationItem:
    return RecommendationItem(
        id=_rid(prefix, key or title),
        category=category,
        severity=severity,
        title=title,
        message=message,
        suggested_changes=suggested_changes or [],
        evidence=evidence or {},
    )


def generate_recommendations(ctx: AnalysisContext) -> List[RecommendationItem]:
    items: List[RecommendationItem] = []
    sp = ctx.strategy_params
    risk = ctx.risk

    # --- Бэктесты ---
    if not ctx.successful_backtests and ctx.latest_backtest is None:
        items.append(
            _item(
                "bt",
                RecommendationCategory.BACKTEST,
                RecommendationSeverity.WARNING,
                "Нет завершённых бэктестов",
                "Запустите history-backtest на странице «Тестирование», чтобы оценить параметры "
                "стратегии и риск до лайва.",
                key="no_backtests",
            )
        )
    elif ctx.latest_backtest and (ctx.latest_backtest.status or "").upper() not in (
        "SUCCESS",
        "",
    ):
        items.append(
            _item(
                "bt",
                RecommendationCategory.BACKTEST,
                RecommendationSeverity.WARNING,
                "Последний бэктест неуспешен",
                f"Статус прогона #{ctx.latest_backtest.run_id}: {ctx.latest_backtest.status}. "
                "Исправьте период, universe или параметры и повторите прогон.",
                evidence={"run_id": ctx.latest_backtest.run_id, "status": ctx.latest_backtest.status},
                key="last_failed",
            )
        )

    best = ctx.best_backtest
    if best:
        ret = _f(best.total_return_percent)
        dd = _f(best.max_drawdown_percent)
        wr = _f(best.win_rate_percent)
        trades = best.trades_total or 0
        sharpe = _f(best.sharpe_ratio)

        if ret is not None and ret < 0:
            items.append(
                _item(
                    "bt",
                    RecommendationCategory.STRATEGY,
                    RecommendationSeverity.WARNING,
                    "Лучший бэктест с отрицательной доходностью",
                    f"Прогон #{best.run_id}: доходность {ret:.2f}%. Рассмотрите смену стратегии, "
                    "сужение universe или пересмотр параметров входа.",
                    evidence={"run_id": best.run_id, "total_return_percent": ret},
                    key="neg_return",
                )
            )
        if dd is not None and dd > 15:
            items.append(
                _item(
                    "bt",
                    RecommendationCategory.RISK,
                    RecommendationSeverity.WARNING if dd <= 25 else RecommendationSeverity.CRITICAL,
                    "Высокая просадка в бэктесте",
                    f"Прогон #{best.run_id}: max drawdown {dd:.1f}%. Уменьшите risk_per_trade, "
                    "max_position_size или ужесточите стопы в risk/pipeline.",
                    evidence={"run_id": best.run_id, "max_drawdown_percent": dd},
                    key="high_dd",
                )
            )
        if trades >= 30 and sharpe is not None and sharpe < 0.5:
            items.append(
                _item(
                    "bt",
                    RecommendationCategory.PARAMS,
                    RecommendationSeverity.INFO,
                    "Низкий Sharpe при активной торговле",
                    f"Sharpe {sharpe:.2f} при {trades} сделках — возможен переторг. "
                    "Увеличьте фильтры входа или интервал свечей.",
                    evidence={"sharpe_ratio": sharpe, "trades_total": trades},
                    key="low_sharpe",
                )
            )
        if wr is not None and wr < 40 and trades >= 10:
            items.append(
                _item(
                    "bt",
                    RecommendationCategory.PARAMS,
                    RecommendationSeverity.INFO,
                    "Низкий win rate в бэктесте",
                    f"Win rate {wr:.1f}% (прогон #{best.run_id}). Подстройте пороги стратегии "
                    f"({ctx.strategy}).",
                    evidence={"win_rate_percent": wr},
                    key="low_wr_bt",
                )
            )

        # Сравнение текущего конфига с лучшим прогоном
        best_cfg = ctx.best_config_snapshot or {}
        best_sp = best_cfg.get("strategy_params") if isinstance(best_cfg, dict) else {}
        best_sp = best_sp or {}
        if best_sp:
            diffs = _nested_diff(sp, best_sp)
            important = [
                d for d in diffs
                if d[0] in (
                    "interval",
                    "candle_days",
                    "lookback_days",
                    "ma_period",
                    "deviation_pct",
                    "risk_per_trade_pct",
                    "max_position_size_pct",
                ) or d[0].startswith("risk.")
            ]
            if important[:5]:
                changes = [
                    SuggestedChange(
                        path=f"strategy_params.{p}" if not p.startswith("risk.") else p,
                        current_value=cur,
                        suggested_value=sug,
                        reason=f"В лучшем бэктесте #{best.run_id}",
                    )
                    for p, cur, sug in important[:5]
                ]
                ret_s = f"{ret:.2f}%" if ret is not None else "—"
                dd_s = f"{dd:.1f}%" if dd is not None else "—"
                items.append(
                    _item(
                        "cfg",
                        RecommendationCategory.PARAMS,
                        RecommendationSeverity.INFO,
                        "Текущие параметры отличаются от лучшего бэктеста",
                        f"Найдено {len(important)} отличий от прогона #{best.run_id} "
                        f"(доходность {ret_s}, DD {dd_s}).",
                        suggested_changes=changes,
                        evidence={"best_run_id": best.run_id, "diff_count": len(important)},
                        key="config_drift",
                    )
                )

    # --- Стратегия-специфичные подсказки ---
    if ctx.strategy == "momentum_breakout":
        lookback = int(sp.get("lookback_days") or 5)
        candle_days = int(sp.get("candle_days") or 14)
        if candle_days < lookback + 3:
            items.append(
                _item(
                    "strat",
                    RecommendationCategory.PARAMS,
                    RecommendationSeverity.WARNING,
                    "Мало истории свечей для momentum_breakout",
                    f"candle_days={candle_days}, lookback_days={lookback}. "
                    f"Рекомендуется candle_days ≥ {lookback + 5}.",
                    suggested_changes=[
                        SuggestedChange(
                            path="strategy_params.candle_days",
                            current_value=candle_days,
                            suggested_value=lookback + 5,
                            reason="Достаточно баров для уровня пробоя",
                        )
                    ],
                    key="mb_candle_days",
                )
            )
    elif ctx.strategy == "reversion_to_ma":
        dev = _f(sp.get("deviation_pct"))
        if dev is not None and dev < 1.0:
            items.append(
                _item(
                    "strat",
                    RecommendationCategory.PARAMS,
                    RecommendationSeverity.INFO,
                    "Узкое отклонение от MA",
                    f"deviation_pct={dev}% — мало сигналов. Для mean-reversion часто используют 1.5–3%.",
                    suggested_changes=[
                        SuggestedChange(
                            path="strategy_params.deviation_pct",
                            current_value=dev,
                            suggested_value=2.0,
                        )
                    ],
                    key="rtm_dev",
                )
            )

    interval = sp.get("interval")
    if interval == "CANDLE_INTERVAL_1_MIN":
        items.append(
            _item(
                "strat",
                RecommendationCategory.OPERATIONAL,
                RecommendationSeverity.WARNING,
                "Интервал 1 минуту",
                "1m даёт много шума и нагрузку на WS/очередь. Для MOEX акций чаще используют 5m или 10m.",
                suggested_changes=[
                    SuggestedChange(
                        path="strategy_params.interval",
                        current_value=interval,
                        suggested_value="CANDLE_INTERVAL_5_MIN",
                    )
                ],
                key="interval_1m",
            )
        )

    # --- Лайв vs бэктест ---
    lm = ctx.live_metrics or {}
    live_wr = _f(lm.get("win_rate"))
    live_pnl = _f(lm.get("total_pnl"))
    live_dd = _f(lm.get("max_drawdown"))
    closed = int(lm.get("closed_trades") or 0)

    if best and closed >= 5:
        bt_wr = _f(best.win_rate_percent)
        if bt_wr is not None and live_wr is not None and live_wr < bt_wr - 15:
            items.append(
                _item(
                    "live",
                    RecommendationCategory.LIVE,
                    RecommendationSeverity.WARNING,
                    "Лайв хуже бэктеста по win rate",
                    f"Лайв win rate {live_wr:.1f}% vs бэктест {bt_wr:.1f}% (прогон #{best.run_id}). "
                    "Проверьте проскальзывание, комиссии, задержки исполнения и universe.",
                    evidence={"live_win_rate": live_wr, "backtest_win_rate": bt_wr},
                    key="live_wr_gap",
                )
            )
        bt_dd = _f(best.max_drawdown_percent)
        if bt_dd is not None and live_dd is not None and live_dd > bt_dd * 1.4:
            items.append(
                _item(
                    "live",
                    RecommendationCategory.LIVE,
                    RecommendationSeverity.WARNING,
                    "Просадка в лайве выше бэктеста",
                    f"Лайв max drawdown {live_dd:.0f} vs бэктест {bt_dd:.1f}%. "
                    "Ужесточите лимиты риска или снизьте размер позиции.",
                    key="live_dd_gap",
                )
            )

    if live_pnl is not None and live_pnl < 0 and closed >= 3:
        items.append(
            _item(
                "live",
                RecommendationCategory.LIVE,
                RecommendationSeverity.WARNING,
                "Отрицательный PnL в лайве",
                f"Суммарный PnL {live_pnl:.2f} по {closed} закрытым сделкам. "
                "Остановите робота при превышении дневного лимита убытков.",
                evidence={"total_pnl": live_pnl, "closed_trades": closed},
                key="live_neg_pnl",
            )
        )

    fill_rate = _f(lm.get("fill_rate"))
    if fill_rate is not None and fill_rate < 60:
        items.append(
            _item(
                "live",
                RecommendationCategory.OPERATIONAL,
                RecommendationSeverity.WARNING,
                "Низкий fill rate",
                f"Fill rate {fill_rate:.1f}% — много отклонённых/отменённых ордеров. "
                "Проверьте лимиты риска, ликвидность и лимитные цены.",
                key="low_fill",
            )
        )

    if ctx.signal_execution_rate_pct is not None and ctx.signal_execution_rate_pct < 50:
        items.append(
            _item(
                "live",
                RecommendationCategory.OPERATIONAL,
                RecommendationSeverity.INFO,
                "Мало исполненных сигналов",
                f"За последние сигналы исполнено {ctx.signal_execution_rate_pct:.0f}%. "
                "Возможны блокировки pipeline/риска или отсутствие позиции для SELL.",
                evidence={"execution_rate_pct": ctx.signal_execution_rate_pct},
                key="low_signal_exec",
            )
        )

    if ctx.risk_events_7d >= 10:
        items.append(
            _item(
                "live",
                RecommendationCategory.RISK,
                RecommendationSeverity.WARNING,
                "Частые срабатывания риска",
                f"За 7 дней зафиксировано {ctx.risk_events_7d} risk events. "
                "Просмотрите robot_risk_events и ослабьте агрессию или расширьте лимиты осознанно.",
                evidence={"risk_events_7d": ctx.risk_events_7d},
                key="risk_events",
            )
        )

    # Робот запущен, но нет активности
    stream = ctx.live_snapshot.get("stream_health") or {}
    if ctx.robot_status == 1:
        last_ev = stream.get("last_event_at")
        if closed == 0 and ctx.signal_execution_rate_pct is None:
            items.append(
                _item(
                    "live",
                    RecommendationCategory.OPERATIONAL,
                    RecommendationSeverity.INFO,
                    "Робот активен, сделок пока нет",
                    "Дождитесь сигналов или проверьте allowed_figis, торговые часы и подписку WS.",
                    key="no_trades_yet",
                )
            )
        if not stream.get("connected_hint") and last_ev is None:
            items.append(
                _item(
                    "live",
                    RecommendationCategory.OPERATIONAL,
                    RecommendationSeverity.CRITICAL,
                    "Нет признаков активности сессии",
                    "В логах нет robot_execution_logs. Проверьте запуск торговой сессии и WebSocket.",
                    key="no_stream",
                )
            )

    max_pos = _f(risk.get("max_position_size_pct") or sp.get("max_position_size_pct"))
    if max_pos is not None and max_pos > 25:
        items.append(
            _item(
                "risk",
                RecommendationCategory.RISK,
                RecommendationSeverity.INFO,
                "Крупный размер позиции",
                f"max_position_size_pct={max_pos}% — для диверсификации по MOEX часто ≤ 15–20%.",
                suggested_changes=[
                    SuggestedChange(
                        path="risk.max_position_size_pct",
                        current_value=max_pos,
                        suggested_value=min(20.0, max_pos),
                    )
                ],
                key="large_pos",
            )
        )

    # Rule-engine расширение: декларативные правила поверх текущих эвристик.
    items.extend(generate_rule_engine_recommendations(ctx))

    # Дедупликация по id (приоритет раннего эвристического item).
    dedup: Dict[str, RecommendationItem] = {}
    for it in items:
        if it.id not in dedup:
            dedup[it.id] = it

    items = list(dedup.values())

    items = _dedupe_conflicting_field_changes(items)

    # Сортировка: critical > warning > info
    order = {
        RecommendationSeverity.CRITICAL: 0,
        RecommendationSeverity.WARNING: 1,
        RecommendationSeverity.INFO: 2,
    }
    items.sort(key=lambda x: (order.get(x.severity, 9), x.category.value))
    return _cap_recommendations(items)


def _cap_recommendations(items: List[RecommendationItem]) -> List[RecommendationItem]:
    critical: List[RecommendationItem] = []
    warning: List[RecommendationItem] = []
    info: List[RecommendationItem] = []
    for it in items:
        if it.severity == RecommendationSeverity.CRITICAL:
            critical.append(it)
        elif it.severity == RecommendationSeverity.WARNING:
            if len(warning) < MAX_WARNING_RECOMMENDATIONS:
                warning.append(it)
        else:
            if len(info) < MAX_INFO_RECOMMENDATIONS:
                info.append(it)
    return [*critical, *warning, *info]


_SEVERITY_ORDER = {
    RecommendationSeverity.CRITICAL: 0,
    RecommendationSeverity.WARNING: 1,
    RecommendationSeverity.INFO: 2,
}


def _change_priority(item: RecommendationItem) -> Tuple[int, int]:
    """Lower is better: severity first, then rule-engine over heuristics."""
    sev = _SEVERITY_ORDER.get(item.severity, 9)
    rule_bonus = 0 if str(item.id).startswith("rule-") else 1
    return sev, rule_bonus


def dedupe_conflicting_field_changes(items: List[RecommendationItem]) -> List[RecommendationItem]:
    """Оставить одно suggested change на field path — с наивысшим приоритетом."""
    return _dedupe_conflicting_field_changes(items)


def _dedupe_conflicting_field_changes(items: List[RecommendationItem]) -> List[RecommendationItem]:
    winners: Dict[str, Tuple[Tuple[int, int], str]] = {}

    for item in items:
        prio = _change_priority(item)
        for ch in item.suggested_changes:
            path = ch.path
            if not path:
                continue
            cur = winners.get(path)
            if cur is None or prio < cur[0]:
                winners[path] = (prio, item.id)
            elif prio == cur[0] and str(item.id).startswith("rule-") and not str(cur[1]).startswith("rule-"):
                winners[path] = (prio, item.id)

    out: List[RecommendationItem] = []
    for item in items:
        kept = [ch for ch in item.suggested_changes if winners.get(ch.path, (None, item.id))[1] == item.id]
        if len(kept) != len(item.suggested_changes):
            item = item.model_copy(update={"suggested_changes": kept})
        out.append(item)
    return out


def strategy_static_tips(strategy: str, params_schema: Dict[str, Any]) -> List[RecommendationItem]:
    """Общие подсказки по стратегии без привязки к роботу."""
    tips: List[RecommendationItem] = []
    if strategy == "grain_seed":
        tips.append(
            _item(
                "tip",
                RecommendationCategory.STRATEGY,
                RecommendationSeverity.INFO,
                "Grain Seed — консервативный режим",
                "Используйте gap_filter и ADX для отсечения флэта; для лайва проверьте force_close_time_msk.",
                key="gs_intro",
            )
        )
    elif strategy == "momentum_breakout":
        tips.append(
            _item(
                "tip",
                RecommendationCategory.STRATEGY,
                RecommendationSeverity.INFO,
                "Momentum Breakout",
                "Согласуйте entry_minutes_from_open с интервалом свечей; при allow_entry_all_day "
                "растёт число ложных пробоев.",
                key="mb_intro",
            )
        )
    elif strategy == "reversion_to_ma":
        tips.append(
            _item(
                "tip",
                RecommendationCategory.STRATEGY,
                RecommendationSeverity.INFO,
                "Reversion to MA",
                "В трендовых рынках mean-reversion просаживается — смотрите ADX/макро или переключайте стратегию.",
                key="rtm_intro",
            )
        )
    if "candle_days" in params_schema:
        tips.append(
            _item(
                "tip",
                RecommendationCategory.PARAMS,
                RecommendationSeverity.INFO,
                "История свечей",
                "candle_days должен покрывать lookback/MA/RSI периоды с запасом; REST bootstrap всегда 10m.",
                key="candle_days",
            )
        )
    return tips
