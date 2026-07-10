---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Backtesting"
  item: "ITEM StrategySignals"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-backtesting
  - gin-item/item-strategysignals
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM StrategySignals]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM StrategySignals]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Стратегия приводится к устойчивой numeric-модели: свечи нормализуются в float,
 inf/NaN чистятся перед индикаторами, ADX считается через EWM с защитой деления на 0.
 Это устраняет падения pandas на object/NAType в rolling/ewm во время history-backtest.

