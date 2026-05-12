---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Backtesting"
  item: "ITEM SimulationEngine"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-backtesting
  - gin-item/item-simulationengine
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM SimulationEngine]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM SimulationEngine]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Ядро симуляции: строит внутридневной цикл по bar_time, запрашивает сигналы стратегии,
 выполняет виртуальные сделки через broker/sim_executor, обновляет equity/drawdown
 и формирует артефакты (signals, trades, equity_curve, daily_positions).

