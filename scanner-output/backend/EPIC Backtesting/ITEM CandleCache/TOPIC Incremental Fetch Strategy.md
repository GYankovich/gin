---
gin_graph:
  version: 1
  root: "backend"
  epic: "EPIC Backtesting"
  item: "ITEM CandleCache"
tags:
  - gin-graph
  - gin-scanner
  - gin-root/backend
  - gin-epic/epic-backtesting
  - gin-item/item-candlecache
---

## Связи графа

> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]

- Вверх по дереву:
  - ITEM: [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM CandleCache]]
  - EPIC: [[Graph/MOC EPIC — backend — EPIC Backtesting]]
  - Корень: [[Graph/MOC Root — backend]]
  - Индекс: [[Graph/Index|Graph / Index]]

Остальные заметки этого ITEM перечислены в [[Graph/MOC ITEM — backend — EPIC Backtesting — ITEM CandleCache]] (избегаем сотен дублей ссылок в каждом файле).

<!-- gin_graph:end -->
 Гарантирует полноту candles_cache на диапазоне дат без лишних запросов:
 вычисляет min/max покрытие по тикеру, догружает только разрывы,
 при необходимости обновляет последний intraday-день и ведет статистику fetch/cache hits.

