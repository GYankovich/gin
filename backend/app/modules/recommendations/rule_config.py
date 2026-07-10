from __future__ import annotations

from typing import Any, Dict, List

# Ограничения выдачи после ранжирования.
# critical — без лимита; warning/info — кап для компактного ответа.
MAX_WARNING_RECOMMENDATIONS = 4
MAX_INFO_RECOMMENDATIONS = 2
RULES_VERSION = "v1.6.0"
RULE_ENGINE_ENABLED = True


RULE_DEFINITIONS: List[Dict[str, Any]] = [
    # --- Risk ---
    {
        "id": "risk-high-dd",
        "category": "risk",
        "priority": "high",
        "description": "Высокая просадка бэктеста",
        "when": {"metric": "backtest.maxDrawdownPct", "op": ">", "value": 25},
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.35,
                "reasoning": "Просадка выше 25% — снизить долю позиции на 35%",
                "expected_impact": "Снижение max drawdown при умеренном снижении доходности",
            }
        ],
    },
    {
        "id": "risk-critical-dd",
        "category": "risk",
        "priority": "critical",
        "description": "Критическая просадка бэктеста",
        "when": {"metric": "backtest.maxDrawdownPct", "op": ">", "value": 30},
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "set",
                "value": 5,
                "reasoning": "Критическая DD — жёсткий лимит доли позиции",
                "expected_impact": "Сильное ограничение хвостового риска",
            }
        ],
    },
    {
        "id": "risk-low-profit-factor",
        "category": "risk",
        "priority": "high",
        "description": "Низкий profit factor",
        "when": {"metric": "backtest.profitFactor", "op": "<", "value": 1.5},
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.25,
                "reasoning": "Profit factor < 1.5 — средняя прибыль не компенсирует убытки",
                "expected_impact": "Рост средней прибыли на сделку",
            }
        ],
    },
    {
        "id": "risk-profit-loss-imbalance",
        "category": "risk",
        "priority": "high",
        "description": "Дисбаланс прибыли и убытка на сделку",
        "when": {"metric": "backtest.profitLossRatio", "op": "<", "value": 1.2},
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.3,
                "reasoning": "Средняя прибыль слишком мала относительно среднего убытка",
                "expected_impact": "Улучшение соотношения risk/reward",
            },
            {
                "field": "risk.stop_loss_percent",
                "operation": "decrease",
                "value": 0.2,
                "reasoning": "Дополнительно: ужесточить стоп для снижения среднего убытка",
                "expected_impact": "Снижение avg loss per trade",
            },
        ],
    },
    {
        "id": "risk-large-position-dd",
        "category": "risk",
        "priority": "high",
        "description": "Крупная позиция при высокой просадке",
        "when": {
            "metric": "risk.maxPositionSizePct",
            "op": ">",
            "value": 20,
            "and": [{"metric": "backtest.maxDrawdownPct", "op": ">", "value": 20}],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.25,
                "reasoning": "Большая доля позиции усиливает просадку",
                "expected_impact": "Снижение волатильности equity curve",
            }
        ],
    },
    {
        "id": "risk-frequent-events",
        "category": "risk",
        "priority": "high",
        "description": "Частые срабатывания риска в лайве",
        "when": {"metric": "live.riskEvents7d", "op": ">=", "value": 10},
        "recommendations": [
            {
                "field": "risk.max_daily_loss",
                "operation": "decrease",
                "value": 0.25,
                "reasoning": "Много risk events за 7 дней — ужесточить дневной лимит",
                "expected_impact": "Меньше агрессивных входов в убыточные дни",
            }
        ],
    },
    # --- Performance ---
    {
        "id": "perf-negative-return",
        "category": "performance",
        "priority": "high",
        "description": "Отрицательная доходность бэктеста",
        "when": {"metric": "backtest.totalReturnPct", "op": "<", "value": 0},
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "review_strategy_and_universe",
                "reasoning": "Лучший прогон убыточен — пересмотрите стратегию или universe",
                "expected_impact": "Поиск более устойчивой конфигурации",
            }
        ],
    },
    {
        "id": "perf-low-return",
        "category": "performance",
        "priority": "medium",
        "description": "Низкая доходность при достаточном числе сделок",
        "when": {
            "metric": "backtest.totalReturnPct",
            "op": "<",
            "value": 10,
            "and": [{"metric": "backtest.tradesTotal", "op": ">=", "value": 10}],
        },
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "soften_liquidity_and_spread_thresholds",
                "reasoning": "Доходность < 10% при активной торговле",
                "expected_impact": "Рост числа качественных входов",
            }
        ],
    },
    {
        "id": "perf-low-winrate",
        "category": "performance",
        "priority": "medium",
        "description": "Низкий win rate",
        "when": {
            "metric": "backtest.winRatePct",
            "op": "<",
            "value": 40,
            "and": [{"metric": "backtest.tradesTotal", "op": ">=", "value": 10}],
        },
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "tighten_entry_thresholds",
                "reasoning": "Низкий win rate на достаточном числе сделок",
                "expected_impact": "Снижение числа ложных входов",
            }
        ],
    },
    {
        "id": "perf-low-winrate-dd",
        "category": "performance",
        "priority": "high",
        "description": "Низкий win rate и высокая просадка",
        "when": {
            "metric": "backtest.winRatePct",
            "op": "<",
            "value": 40,
            "and": [
                {"metric": "backtest.maxDrawdownPct", "op": ">", "value": 20},
                {"metric": "backtest.tradesTotal", "op": ">=", "value": 10},
            ],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.3,
                "reasoning": "Низкий WR + высокая DD — снизить экспозицию",
                "expected_impact": "Снижение риска при слабом качестве сигналов",
            }
        ],
    },
    {
        "id": "perf-low-sharpe-high-activity",
        "category": "performance",
        "priority": "medium",
        "description": "Низкий Sharpe при высокой активности",
        "when": {
            "metric": "backtest.sharpe",
            "op": "<",
            "value": 1.0,
            "and": [{"metric": "backtest.tradesTotal", "op": ">", "value": 100}],
        },
        "recommendations": [
            {
                "field": "strategy_params.interval",
                "operation": "suggest",
                "value": "increase_timeframe",
                "reasoning": "Слишком много сделок при слабом Sharpe",
                "expected_impact": "Меньше шума и переторговки",
            }
        ],
    },
    {
        "id": "perf-low-sharpe-dd",
        "category": "performance",
        "priority": "high",
        "description": "Низкий Sharpe и высокая просадка",
        "when": {
            "metric": "backtest.sharpe",
            "op": "<",
            "value": 1.0,
            "and": [{"metric": "backtest.maxDrawdownPct", "op": ">", "value": 20}],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.25,
                "reasoning": "Sharpe < 1 и DD > 20% — снизить размер позиции",
                "expected_impact": "Снижение волатильности и просадки",
            }
        ],
    },
    {
        "id": "perf-too-few-trades",
        "category": "performance",
        "priority": "medium",
        "description": "Слишком мало сделок",
        "when": {"metric": "backtest.tradesTotal", "op": "<", "value": 10},
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "soften_liquidity_and_spread_thresholds",
                "reasoning": "Статистика нестабильна из-за малого числа сделок",
                "expected_impact": "Рост количества сделок и надёжности оценки",
            }
        ],
    },
    {
        "id": "perf-too-many-trades",
        "category": "performance",
        "priority": "medium",
        "description": "Слишком много сделок",
        "when": {"metric": "backtest.tradesTotal", "op": ">", "value": 200},
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "tighten_entry_thresholds",
                "reasoning": "Переторговка — >200 сделок за период",
                "expected_impact": "Снижение числа сделок и комиссионной нагрузки",
            }
        ],
    },
    # --- Execution ---
    {
        "id": "exec-low-fill-rate",
        "category": "execution",
        "priority": "high",
        "description": "Низкий fill rate в лайве",
        "when": {"metric": "live.fillRatePct", "op": "<", "value": 60},
        "recommendations": [
            {
                "field": "execution_model",
                "operation": "suggest",
                "value": "review_limits_and_liquidity",
                "reasoning": "Слишком много отмен/неисполнений",
                "expected_impact": "Рост доли исполненных сигналов",
            }
        ],
    },
    {
        "id": "exec-commission-pressure",
        "category": "execution",
        "priority": "high",
        "description": "Комиссия съедает значительную долю прибыли",
        "when": {"metric": "backtest.commissionToReturnRatio", "op": ">", "value": 0.2},
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.3,
                "reasoning": "Комиссии > 20% от валовой доходности прогона",
                "expected_impact": "Компенсация издержек более широким TP",
            },
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "reduce_trade_frequency",
                "reasoning": "Снизить частоту сделок для уменьшения комиссий",
                "expected_impact": "Снижение commission drag",
            },
        ],
    },
    {
        "id": "exec-commission-critical",
        "category": "execution",
        "priority": "critical",
        "description": "Критическое давление комиссий",
        "when": {"metric": "backtest.commissionToReturnRatio", "op": ">", "value": 0.3},
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.5,
                "reasoning": "Комиссии > 30% от валовой доходности",
                "expected_impact": "Жёсткая компенсация издержек",
            }
        ],
    },
    {
        "id": "exec-low-signal-rate",
        "category": "execution",
        "priority": "medium",
        "description": "Низкая доля исполненных сигналов",
        "when": {"metric": "live.signalExecutionRatePct", "op": "<", "value": 50},
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "review_risk_gates_and_universe",
                "reasoning": "Менее половины сигналов доходит до исполнения",
                "expected_impact": "Выявление блокировок pipeline/риска",
            }
        ],
    },
    # --- Live ---
    {
        "id": "live-negative-pnl",
        "category": "risk",
        "priority": "high",
        "description": "Отрицательный PnL в лайве",
        "when": {
            "metric": "live.totalPnl",
            "op": "<",
            "value": 0,
            "and": [{"metric": "live.closedTrades", "op": ">=", "value": 3}],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.2,
                "reasoning": "Лайв PnL отрицательный при достаточном числе сделок",
                "expected_impact": "Снижение агрессии до стабилизации",
            }
        ],
    },
    {
        "id": "risk-frequent-stop-loss",
        "category": "risk",
        "priority": "high",
        "description": "Частое срабатывание стоп-лосса",
        "when": {
            "metric": "backtest.stopLossHitRate",
            "op": ">",
            "value": 40,
            "and": [{"metric": "backtest.winRatePct", "op": "<", "value": 50}],
        },
        "recommendations": [
            {
                "field": "risk.stop_loss_percent",
                "operation": "increase",
                "value": 0.35,
                "reasoning": "Стопы срабатывают слишком часто при низком win rate — расширить стоп",
                "expected_impact": "Снижение доли выходов по стопу на 25–35%",
            },
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.2,
                "reasoning": "Дополнительно снизить размер позиции при частых стопах",
                "expected_impact": "Меньший ущерб при каждом стопе",
            },
        ],
    },
    {
        "id": "risk-stop-loss-imbalance",
        "category": "risk",
        "priority": "high",
        "description": "Частые стопы при крупном среднем убытке",
        "when": {
            "metric": "backtest.stopLossHitRate",
            "op": ">",
            "value": 40,
            "and": [{"metric": "backtest.profitLossRatio", "op": "<", "value": 1.43}],
        },
        "recommendations": [
            {
                "field": "risk.stop_loss_percent",
                "operation": "increase",
                "value": 0.2,
                "reasoning": "Стопы частые и средний убыток высок — смягчить стоп и экспозицию",
                "expected_impact": "Комплексное снижение stop-out давления",
            },
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.2,
                "reasoning": "Снизить долю позиции при крупных убытках на стопе",
                "expected_impact": "Снижение avg loss per trade",
            },
        ],
    },
    {
        "id": "perf-early-take-profit",
        "category": "performance",
        "priority": "medium",
        "description": "Ранний тейк-профит ограничивает прибыль",
        "when": {
            "metric": "backtest.takeProfitHitRate",
            "op": ">",
            "value": 60,
            "and": [{"metric": "backtest.profitFactor", "op": "<", "value": 1.8}],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.4,
                "reasoning": "TP срабатывает слишком часто при слабом profit factor",
                "expected_impact": "Рост средней прибыли на сделку и profit factor",
            }
        ],
    },
    {
        "id": "perf-early-tp-low-avg-profit",
        "category": "performance",
        "priority": "medium",
        "description": "Ранний TP при низкой средней прибыли",
        "when": {
            "metric": "backtest.takeProfitHitRate",
            "op": ">",
            "value": 60,
            "and": [{"metric": "backtest.avgProfitPerTradePct", "op": "<", "value": 2}],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.35,
                "reasoning": "Средняя прибыль на сделку < 2% капитала при частых TP",
                "expected_impact": "Увеличение avg profit per trade",
            }
        ],
    },
    {
        "id": "perf-profit-factor-winrate",
        "category": "performance",
        "priority": "medium",
        "description": "Слабый profit factor при умеренном win rate",
        "when": {
            "metric": "backtest.profitFactor",
            "op": "<",
            "value": 1.5,
            "and": [
                {"metric": "backtest.winRatePct", "op": ">=", "value": 45},
                {"metric": "backtest.tradesTotal", "op": ">=", "value": 10},
            ],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.35,
                "reasoning": "Win rate приемлемый, но profit factor низкий — прибыли мало на сделку",
                "expected_impact": "Рост profit factor без сильного снижения win rate",
            }
        ],
    },
    # --- Universe ---
    {
        "id": "universe-narrow",
        "category": "universe",
        "priority": "medium",
        "description": "Слишком узкий universe",
        "when": {"metric": "universe.avgUniverseSize", "op": "<", "value": 5},
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "soften_volume_spread_atr_filters",
                "reasoning": "Средний размер universe < 5 инструментов в день",
                "expected_impact": "Рост universe на 30–50%",
            }
        ],
    },
    {
        "id": "universe-narrow-low-traded",
        "category": "universe",
        "priority": "high",
        "description": "Узкий universe и мало торгуемых инструментов",
        "when": {
            "metric": "universe.avgUniverseSize",
            "op": "<",
            "value": 5,
            "and": [{"metric": "universe.instrumentsTraded", "op": "<", "value": 3}],
        },
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "soften_liquidity_and_spread_thresholds",
                "reasoning": "Мало кандидатов и < 3 инструментов в сделках",
                "expected_impact": "Увеличение universe и диверсификации",
            }
        ],
    },
    {
        "id": "universe-wide-low-traded",
        "category": "universe",
        "priority": "medium",
        "description": "Широкий universe, но мало реально торгуемых",
        "when": {
            "metric": "universe.avgUniverseSize",
            "op": ">",
            "value": 30,
            "and": [{"metric": "universe.instrumentsTraded", "op": "<", "value": 5}],
        },
        "recommendations": [
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "tighten_volume_spread_atr_filters",
                "reasoning": "Universe широкий, но торгуется < 5 инструментов — отбор неэффективен",
                "expected_impact": "Сужение universe на 20–40%",
            }
        ],
    },
    {
        "id": "universe-low-utilization",
        "category": "universe",
        "priority": "medium",
        "description": "Низкая утилизация universe",
        "when": {"metric": "universe.universeUtilizationRatio", "op": "<", "value": 0.3},
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "soften_entry_thresholds",
                "reasoning": "Торгуется менее 30% доступного universe",
                "expected_impact": "Рост числа сигналов на 30–50%",
            }
        ],
    },
    {
        "id": "universe-concentration",
        "category": "universe",
        "priority": "high",
        "description": "Высокая концентрация на 1–2 инструментах",
        "when": {
            "metric": "universe.instrumentsTraded",
            "op": "<",
            "value": 3,
            "and": [
                {"metric": "backtest.tradesTotal", "op": ">", "value": 50},
                {"metric": "backtest.maxDrawdownPct", "op": ">", "value": 20},
            ],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.35,
                "reasoning": "Много сделок на < 3 инструментах при высокой DD",
                "expected_impact": "Снижение концентрационного риска",
            },
            {
                "field": "pipeline.filters",
                "operation": "suggest",
                "value": "soften_selection_filters_for_diversification",
                "reasoning": "Расширить отбор для диверсификации",
                "expected_impact": "Больше инструментов в ротации",
            },
        ],
    },
    # --- Market-specific ---
    {
        "id": "market-crypto-funding-pressure",
        "category": "market_specific",
        "priority": "high",
        "description": "Funding съедает значительную долю доходности (perp)",
        "when": {
            "metric": "backtest.fundingToReturnRatio",
            "op": ">",
            "value": 0.1,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "bybit"}],
        },
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "reduce_hold_time_or_spot_mode",
                "reasoning": "Funding > 10% от валовой доходности на Bybit perp",
                "expected_impact": "Снижение funding drag на 30–50%",
            },
            {
                "field": "costs.funding_mode",
                "operation": "set",
                "value": "average",
                "reasoning": "Переключить симуляцию funding на режим average",
                "expected_impact": "Усреднение funding-издержек",
            },
        ],
    },
    {
        "id": "bybit-funding-critical-spot",
        "category": "market_specific",
        "priority": "critical",
        "description": "Критическое давление funding на perp",
        "when": {
            "metric": "backtest.fundingToReturnRatio",
            "op": ">",
            "value": 0.2,
            "and": [
                {"metric": "market.brokerType", "op": "==", "value": "bybit"},
                {"metric": "bybit.instrumentIsPerp", "op": "==", "value": 1},
            ],
        },
        "recommendations": [
            {
                "field": "bybit.instrument_category",
                "operation": "set",
                "value": "spot",
                "reasoning": "Funding > 20% доходности — рассмотреть spot вместо perp",
                "expected_impact": "Исключение funding из PnL",
            }
        ],
    },
    {
        "id": "bybit-universe-narrow-volume",
        "category": "universe",
        "priority": "medium",
        "description": "Узкий crypto-universe (Bybit)",
        "when": {
            "metric": "universe.avgUniverseSize",
            "op": "<",
            "value": 5,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "bybit"}],
        },
        "recommendations": [
            {
                "field": "crypto_universe.min_volume_24h_usd",
                "operation": "decrease",
                "value": 0.35,
                "reasoning": "Средний universe < 5 — смягчить порог объёма 24h",
                "expected_impact": "Рост universe на 30–50%",
            }
        ],
    },
    {
        "id": "bybit-universe-narrow-spread",
        "category": "universe",
        "priority": "medium",
        "description": "Узкий crypto-universe — спред (Bybit)",
        "when": {
            "metric": "universe.avgUniverseSize",
            "op": "<",
            "value": 5,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "bybit"}],
        },
        "recommendations": [
            {
                "field": "crypto_universe.max_spread_bps",
                "operation": "increase",
                "value": 0.35,
                "reasoning": "Расширить допустимый спред для отбора пар",
                "expected_impact": "Рост universe на 20–30%",
            }
        ],
    },
    {
        "id": "bybit-universe-narrow-funding",
        "category": "universe",
        "priority": "medium",
        "description": "Узкий crypto-universe — funding-фильтр (Bybit)",
        "when": {
            "metric": "universe.avgUniverseSize",
            "op": "<",
            "value": 5,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "bybit"}],
        },
        "recommendations": [
            {
                "field": "crypto_universe.min_funding_rate",
                "operation": "decrease",
                "value": 0.35,
                "reasoning": "Расширить нижнюю границу funding rate",
                "expected_impact": "Рост universe на 20–30%",
            },
            {
                "field": "crypto_universe.max_funding_rate",
                "operation": "increase",
                "value": 0.35,
                "reasoning": "Расширить верхнюю границу funding rate",
                "expected_impact": "Больше пар проходят funding-фильтр",
            },
        ],
    },
    {
        "id": "bybit-slippage-pressure",
        "category": "execution",
        "priority": "high",
        "description": "Проскальзывание съедает доходность (Bybit)",
        "when": {
            "metric": "bybit.slippageToReturnRatio",
            "op": ">",
            "value": 0.15,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "bybit"}],
        },
        "recommendations": [
            {
                "field": "costs.backtest_execution",
                "operation": "set",
                "value": "market_taker",
                "reasoning": "Slippage > 15% от валовой доходности — перейти на market_taker в бэктесте",
                "expected_impact": "Более реалистичное исполнение",
            },
            {
                "field": "execution_model.slippage_pct",
                "operation": "decrease",
                "value": 0.35,
                "reasoning": "Дополнительно снизить slippage_pct в модели",
                "expected_impact": "Снижение издержек проскальзывания",
            },
        ],
    },
    {
        "id": "bybit-commission-fee-model",
        "category": "execution",
        "priority": "high",
        "description": "Комиссия Bybit не соответствует maker/taker модели",
        "when": {
            "metric": "backtest.commissionToReturnRatio",
            "op": ">",
            "value": 0.2,
            "and": [
                {"metric": "market.brokerType", "op": "==", "value": "bybit"},
                {"metric": "bybit.backtestFeeModelIsMakerTaker", "op": "==", "value": 0},
            ],
        },
        "recommendations": [
            {
                "field": "costs.backtest_fee_model",
                "operation": "set",
                "value": "maker_taker",
                "reasoning": "Комиссии > 20% доходности — включить maker_taker fee model",
                "expected_impact": "Реалистичные комиссии в симуляции",
            }
        ],
    },
    {
        "id": "bybit-leverage-underuse-return",
        "category": "risk",
        "priority": "medium",
        "description": "Плечо недоиспользуется при слабой доходности",
        "when": {
            "metric": "bybit.leverageUsed",
            "op": "<",
            "value": 1.0,
            "and": [
                {"metric": "backtest.totalReturnPct", "op": "<", "value": 20},
                {"metric": "bybit.instrumentIsPerp", "op": "==", "value": 1},
                {"metric": "market.brokerType", "op": "==", "value": "bybit"},
            ],
        },
        "recommendations": [
            {
                "field": "bybit.leverage",
                "operation": "set",
                "value": 2,
                "reasoning": "Эффективное плечо < 1x при доходности < 20%",
                "expected_impact": "Потенциальный рост доходности на perp",
            }
        ],
    },
    {
        "id": "bybit-leverage-underuse-safe",
        "category": "risk",
        "priority": "low",
        "description": "Плечо недоиспользуется при низкой просадке",
        "when": {
            "metric": "bybit.leverageUsed",
            "op": "<",
            "value": 1.0,
            "and": [
                {"metric": "backtest.maxDrawdownPct", "op": "<", "value": 10},
                {"metric": "bybit.instrumentIsPerp", "op": "==", "value": 1},
                {"metric": "market.brokerType", "op": "==", "value": "bybit"},
            ],
        },
        "recommendations": [
            {
                "field": "bybit.leverage",
                "operation": "set",
                "value": 2,
                "reasoning": "Низкая DD и слабое использование плеча",
                "expected_impact": "Умеренный рост доходности при контролируемом риске",
            }
        ],
    },
    {
        "id": "bybit-leverage-overuse",
        "category": "risk",
        "priority": "high",
        "description": "Избыточное плечо при высокой просадке",
        "when": {
            "metric": "bybit.leverageUsed",
            "op": ">",
            "value": 3,
            "and": [
                {"metric": "backtest.maxDrawdownPct", "op": ">", "value": 30},
                {"metric": "market.brokerType", "op": "==", "value": "bybit"},
            ],
        },
        "recommendations": [
            {
                "field": "bybit.leverage",
                "operation": "set",
                "value": 1,
                "reasoning": "Плечо > 3x при DD > 30%",
                "expected_impact": "Снижение риска ликвидации и хвостовых потерь",
            }
        ],
    },
    # --- MOEX ---
    {
        "id": "moex-gap-moderate",
        "category": "market_specific",
        "priority": "medium",
        "description": "Гэпы часто влияют на отбор (MOEX)",
        "when": {
            "metric": "moex.avgGapImpactPct",
            "op": ">",
            "value": 0.5,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "strategy_params.gap_filter_pct",
                "operation": "increase",
                "value": 0.4,
                "reasoning": "Средний гэп > 0.5% — расширить gap_filter",
                "expected_impact": "Снижение влияния гэпов на входы",
            }
        ],
    },
    {
        "id": "moex-gap-severe",
        "category": "market_specific",
        "priority": "high",
        "description": "Крупные гэпы мешают стратегии (MOEX)",
        "when": {
            "metric": "moex.avgGapImpactPct",
            "op": ">",
            "value": 1.0,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "strategy_params.gap_filter_pct",
                "operation": "increase",
                "value": 0.75,
                "reasoning": "Средний гэп > 1% — жёстче фильтровать гэпы",
                "expected_impact": "Жёсткая фильтрация гэпов",
            }
        ],
    },
    {
        "id": "moex-commission-pressure",
        "category": "market_specific",
        "priority": "high",
        "description": "Комиссия MOEX съедает доходность",
        "when": {
            "metric": "backtest.commissionToReturnRatio",
            "op": ">",
            "value": 0.2,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.4,
                "reasoning": "Комиссии > 20% от валовой доходности на MOEX",
                "expected_impact": "Компенсация комиссии более широким TP",
            },
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.25,
                "reasoning": "Меньше оборота — меньше комиссионной нагрузки",
                "expected_impact": "Снижение commission drag",
            },
        ],
    },
    {
        "id": "moex-ndfl-pressure",
        "category": "market_specific",
        "priority": "medium",
        "description": "НДФЛ заметно снижает чистую доходность",
        "when": {
            "metric": "moex.ndflToReturnRatio",
            "op": ">",
            "value": 0.1,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.25,
                "reasoning": "НДФЛ > 10% от валовой доходности прогона",
                "expected_impact": "Компенсация налога",
            }
        ],
    },
    {
        "id": "moex-ndfl-critical",
        "category": "market_specific",
        "priority": "high",
        "description": "НДФЛ критически высок относительно доходности",
        "when": {
            "metric": "moex.ndflToReturnRatio",
            "op": ">",
            "value": 0.15,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "risk.take_profit_percent",
                "operation": "increase",
                "value": 0.4,
                "reasoning": "НДФЛ > 15% от валовой доходности",
                "expected_impact": "Жёсткая компенсация налога",
            }
        ],
    },
    {
        "id": "moex-narrow-session",
        "category": "market_specific",
        "priority": "medium",
        "description": "Торговое окно уже половины MOEX-сессии",
        "when": {
            "metric": "moex.tradingHoursUsedRatio",
            "op": "<",
            "value": 0.5,
            "and": [{"metric": "market.brokerType", "op": "==", "value": "tinvest"}],
        },
        "recommendations": [
            {
                "field": "risk.trading_hours_start",
                "operation": "suggest",
                "value": "expand_session_window",
                "reasoning": "Используется < 50% стандартной сессии 10:00–18:45 MSK",
                "expected_impact": "Больше возможностей для входа",
            },
            {
                "field": "risk.trading_hours_end",
                "operation": "suggest",
                "value": "expand_session_window",
                "reasoning": "Расширить конец торгового окна",
                "expected_impact": "Рост числа сигналов",
            },
        ],
    },
    {
        "id": "moex-very-narrow-session",
        "category": "market_specific",
        "priority": "high",
        "description": "Очень узкая сессия и мало сделок",
        "when": {
            "metric": "moex.tradingHoursUsedRatio",
            "op": "<",
            "value": 0.3,
            "and": [
                {"metric": "backtest.tradesTotal", "op": "<", "value": 10},
                {"metric": "market.brokerType", "op": "==", "value": "tinvest"},
            ],
        },
        "recommendations": [
            {
                "field": "risk.trading_hours_start",
                "operation": "suggest",
                "value": "expand_session_by_1_2_hours",
                "reasoning": "Окно < 30% сессии при < 10 сделках",
                "expected_impact": "Увеличение сделок на 30–50%",
            }
        ],
    },
    {
        "id": "moex-negative-weekday",
        "category": "market_specific",
        "priority": "medium",
        "description": "Есть убыточный день недели",
        "when": {
            "metric": "moex.negativeWeekdaysCount",
            "op": ">=",
            "value": 1,
            "and": [
                {"metric": "backtest.tradesTotal", "op": ">=", "value": 10},
                {"metric": "market.brokerType", "op": "==", "value": "tinvest"},
            ],
        },
        "recommendations": [
            {
                "field": "risk.allowed_weekdays",
                "operation": "clear_weekday_bit",
                "value": None,
                "reasoning": "Исключить наихудший день недели по средней дневной доходности",
                "expected_impact": "Снижение убыточных торговых дней",
            }
        ],
    },
    {
        "id": "moex-expand-weekdays",
        "category": "market_specific",
        "priority": "low",
        "description": "Не все дни недели включены при малой активности",
        "when": {
            "metric": "moex.allWeekdaysEnabled",
            "op": "==",
            "value": 0,
            "and": [
                {"metric": "backtest.tradesTotal", "op": "<", "value": 15},
                {"metric": "moex.negativeWeekdaysCount", "op": "==", "value": 0},
                {"metric": "market.brokerType", "op": "==", "value": "tinvest"},
            ],
        },
        "recommendations": [
            {
                "field": "risk.allowed_weekdays",
                "operation": "set",
                "value": 31,
                "reasoning": "Нет явно убыточных дней — можно включить все будни",
                "expected_impact": "Рост числа торговых возможностей",
            }
        ],
    },
    # --- General (both markets) ---
    {
        "id": "gen-long-bias-weak-profit",
        "category": "performance",
        "priority": "medium",
        "description": "Перекос в long при слабой прибыли long vs short",
        "when": {
            "metric": "general.longBiasWithWeakProfit",
            "op": "==",
            "value": 1,
            "and": [{"metric": "backtest.tradesTotal", "op": ">=", "value": 6}],
        },
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "reduce_long_signal_share",
                "reasoning": "Long-сделок > 2× short, но avg profit long < avg profit short",
                "expected_impact": "Улучшение баланса long/short",
            }
        ],
    },
    {
        "id": "gen-short-bias-weak-profit",
        "category": "performance",
        "priority": "medium",
        "description": "Перекос в short при слабой прибыли short vs long",
        "when": {
            "metric": "general.shortBiasWithWeakProfit",
            "op": "==",
            "value": 1,
            "and": [{"metric": "backtest.tradesTotal", "op": ">=", "value": 6}],
        },
        "recommendations": [
            {
                "field": "strategy_params",
                "operation": "suggest",
                "value": "reduce_short_signal_share",
                "reasoning": "Short-сделок > 2× long, но avg profit short < avg profit long",
                "expected_impact": "Улучшение баланса long/short",
            }
        ],
    },
    {
        "id": "gen-negative-trading-hour",
        "category": "performance",
        "priority": "medium",
        "description": "Есть убыточный час торговли",
        "when": {
            "metric": "general.negativeHoursCount",
            "op": ">=",
            "value": 1,
            "and": [{"metric": "backtest.tradesTotal", "op": ">=", "value": 10}],
        },
        "recommendations": [
            {
                "field": "risk.trading_hours_start",
                "operation": "narrow_trading_hour",
                "value": "exclude_worst_hour",
                "reasoning": "Исключить наихудший час по среднему PnL закрытых сделок",
                "expected_impact": "Снижение убыточных часов",
            },
            {
                "field": "risk.trading_hours_end",
                "operation": "narrow_trading_hour",
                "value": "exclude_worst_hour",
                "reasoning": "Сузить торговое окно вокруг убыточного часа",
                "expected_impact": "Меньше входов в слабые часы",
            },
        ],
    },
    {
        "id": "gen-positive-hour-exposure",
        "category": "performance",
        "priority": "low",
        "description": "Выраженный прибыльный час торговли",
        "when": {
            "metric": "general.bestHourReturn",
            "op": ">",
            "value": 0,
            "and": [
                {"metric": "general.worstHourReturn", "op": "<", "value": 0},
                {"metric": "backtest.tradesTotal", "op": ">=", "value": 10},
            ],
        },
        "recommendations": [
            {
                "field": "risk.trading_hours_start",
                "operation": "expand_trading_hour",
                "value": "focus_best_hour",
                "reasoning": "Есть стабильно прибыльный час — сфокусировать экспозицию",
                "expected_impact": "Рост доходности за счёт лучших часов",
            }
        ],
    },
    {
        "id": "gen-high-beta-drawdown",
        "category": "risk",
        "priority": "high",
        "description": "Высокая рыночная чувствительность и просадка",
        "when": {
            "metric": "general.betaEstimate",
            "op": ">",
            "value": 1.2,
            "and": [{"metric": "backtest.maxDrawdownPct", "op": ">", "value": 25}],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "decrease",
                "value": 0.25,
                "reasoning": "Оценка beta > 1.2 при DD > 25% — снизить рыночную экспозицию",
                "expected_impact": "Снижение рыночного риска",
            }
        ],
    },
    {
        "id": "gen-low-beta-low-return",
        "category": "performance",
        "priority": "medium",
        "description": "Низкая beta и слабая доходность",
        "when": {
            "metric": "general.betaEstimate",
            "op": "<",
            "value": 0.5,
            "and": [{"metric": "backtest.totalReturnPct", "op": "<", "value": 10}],
        },
        "recommendations": [
            {
                "field": "risk.max_position_percent",
                "operation": "increase",
                "value": 0.25,
                "reasoning": "Низкая волатильность относительно рынка (beta < 0.5) при return < 10%",
                "expected_impact": "Увеличение экспозиции при умеренном риске",
            }
        ],
    },
]
