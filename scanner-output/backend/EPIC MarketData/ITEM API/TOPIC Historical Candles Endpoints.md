---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC MarketData"
  item: "ITEM API"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-marketdata
  - gin-item/item-api
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC MarketData — ITEM API]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC MarketData]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC MarketData — ITEM API]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Роутер исторических данных: нормализация диапазонов дат, получение свечей,
 проксирование/кеширование и lightweight backtest утилиты поверх market data.

