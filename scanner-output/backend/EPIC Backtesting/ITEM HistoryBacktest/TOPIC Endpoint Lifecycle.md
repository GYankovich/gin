---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Backtesting"
  item: "ITEM HistoryBacktest"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-backtesting
  - gin-item/item-historybacktest
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM HistoryBacktest]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM HistoryBacktest]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Оркестрация /api/robots/history-backtest: merge config, подготовка history,
 отбор тикеров через pipeline, загрузка свечей из cache/MOEX, симуляция и persist.
 Источники данных приоритетно локальные таблицы ganaly/backtest, затем внешние API.

