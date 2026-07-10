---
gin_graph:
  version: 1
  root: "frontend-tsx"
  epic: "EPIC Backtesting"
  item: "ITEM TestingPage"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/frontend-tsx
  - gin-epic/epic-backtesting
  - gin-item/item-testingpage
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — frontend-tsx — EPIC Backtesting — ITEM TestingPage]]
  - EPIC: [[Graph/MOC EPIC — frontend-tsx — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — frontend-tsx]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — frontend-tsx — EPIC Backtesting — ITEM TestingPage]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Форма тестирования повторяет параметры робота, позволяет выбрать интервал свечей,
 собирает payload для /api/robots/history-backtest и отображает результат прогона:
 status stages, метрики, кривая капитала, сделки, сигналы, ордера и история запусков.

