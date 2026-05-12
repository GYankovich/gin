---
gin_graph:
  version: 1
  root: "frontend-ts"
  epic: "EPIC Frontend"
  item: "ITEM APIClient"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/frontend-ts
  - gin-epic/epic-frontend
  - gin-item/item-apiclient
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — frontend-ts — EPIC Frontend — ITEM APIClient]]
  - EPIC: [[Graph/MOC EPIC — frontend-ts — EPIC Frontend]]
  - Корень: [[Graph/MOC Root — frontend-ts]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — frontend-ts — EPIC Frontend — ITEM APIClient]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Клиентский фасад для /robots и связанных endpoints: CRUD, backtest, live snapshot,
 DMS preview и вспомогательные методы для экранов настройки/тестирования.

