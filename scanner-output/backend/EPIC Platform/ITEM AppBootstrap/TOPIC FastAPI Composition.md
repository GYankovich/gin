---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Platform"
  item: "ITEM AppBootstrap"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-platform
  - gin-item/item-appbootstrap
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Platform — ITEM AppBootstrap]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Platform]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Platform — ITEM AppBootstrap]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Точка сборки приложения: lifespan старта/остановки планировщиков, middleware,
 подключение API-роутеров и системные health/force-run endpoints.

