---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Platform"
  item: "ITEM Auth"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-platform
  - gin-item/item-auth
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Platform — ITEM Auth]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Platform]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Platform — ITEM Auth]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Сервис авторизации: валидация пользователя, выпуск JWT, управление профилем
 и проверка прав доступа через SQL-слой и security helpers.

