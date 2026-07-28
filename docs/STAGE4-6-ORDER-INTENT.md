# Stage 4 / 5 / 6 as adapters (OrderIntent pipeline)

См. также [BRD-ARCH-03](BRD-ARCH-03-unified-engine-architecture.md) §7–9.

## Целевой контур live-цикла

```
Risk exits (Stage4 adapter)
  → Strategy signals (Stage5 adapter)
  → Risk sizing/filters (RiskManager helpers)
  → LiveExecutionService.submit_intents (Stage6 place)
```

| Было | Стало |
|------|--------|
| Stage4 сам вызывает `post_order` | Stage4 только `OrderIntent(kind=exit_sl_tp)` |
| Stage5 sizing + strategy | sizing/filters в `RiskManager.size_live_strategy_signal` |
| Два пути place | Только `LiveExecutionService` / Stage6 |
| Дубли in-flight | `SymbolGuard` |

## Контракты

- `OrderIntent` — [`contracts.py`](../backend/app/modules/robots/trading/contracts.py): `entry` | `exit_sl_tp` | `exit_strategy` | `flatten`
- `SymbolGuard` — [`symbol_guard.py`](../backend/app/modules/robots/trading/symbol_guard.py)
- `RiskManager.plan_sl_tp_exit_intents` / `size_live_strategy_signal` — [`risk/manager.py`](../backend/app/modules/robots/trading/risk/manager.py)

## Оркестрация

[`trading_core.run_single_trading_cycle`](../backend/app/modules/robots/trading/core/trading_core.py):

1. `_plan_exit_intents` (Stage4 decision)
2. `_generate_signals` (Stage5)
3. merge intents → `_execute_intents`
4. register pending close + live events с `intent_source`

Имена Stage4/5/6 сохранены как тонкие адаптеры (логи / Live UI). Полный cutover на `LiveTradingEngine` — отдельно (R1 / engine-parity).
