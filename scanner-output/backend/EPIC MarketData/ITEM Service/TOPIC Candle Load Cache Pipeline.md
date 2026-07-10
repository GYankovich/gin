---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC MarketData"
  item: "ITEM Service"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-marketdata
  - gin-item/item-service
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC MarketData — ITEM Service]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC MarketData]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC MarketData — ITEM Service]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Сервис market data: загрузка свечей из внешних источников, нормализация формата,
 сохранение в локальный репозиторий и выдача данных для аналитики/бэктеста.

