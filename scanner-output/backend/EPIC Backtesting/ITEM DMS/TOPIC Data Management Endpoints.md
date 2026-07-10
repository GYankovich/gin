---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Backtesting"
  item: "ITEM DMS"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-backtesting
  - gin-item/item-dms
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM DMS]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM DMS]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Роутер DMS: подписки, снапшоты, preview pipeline, инициализация дня и логи
 фильтрации; используется как фундамент отбора бумаг для торговли/бэктеста.

