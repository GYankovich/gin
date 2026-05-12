# Obsidian Source Scanner: настройка для проекта `gin`

Документ фиксирует рабочую конфигурацию Source Scanner (v2) для этого репозитория.

## 1) Что уже подготовлено в проекте

- В проекте есть базовая гигиена для сканирования: исключены `venv`, `.venv`, `node_modules`, `dist`, IDE и кеши через `.gitignore`.
- Рекомендованный формат документирующих маркеров описан ниже и готов к использованию в коде.

## 2) Рекомендуемые профили сканирования

Source Scanner v2 сканирует **один корень + одно расширение** за прогон.  
Для этого проекта лучше использовать два отдельных прогона.

### Профиль A: Backend (Python)

- **Folder**: `<repo>/backend/app`
- **Working Folder**: `scanner/backend`
- **Start**: `#///`
- **The markdown file path**: `EPIC.ITEM.TOPIC`
- **Extension**: `.py`
- **Destination file extension**: `md`

### Профиль B: Frontend (React/TS)

- **Folder**: `<repo>/frontend/src`
- **Working Folder**: `scanner/frontend`
- **Start**: `///@`
- **The markdown file path**: `EPIC.ITEM.TOPIC`
- **Extension**: `.tsx`
- **Destination file extension**: `md`

При необходимости добавь отдельный профиль для `.ts`.

## 3) Единый формат маркеров для команды

Чтобы документация собиралась предсказуемо, используем общий стиль:

- Python:
  - `#///EPIC Backtesting.ITEM HistoryBacktest.TOPIC API Contract [1]`
  - `#/// текст блока...`
- TS/TSX:
  - `///@EPIC Backtesting.ITEM TestingPage.TOPIC Candle Interval [1]`
  - `///@ текст блока...`

Правила:

- Первый маркер блока содержит путь + имя файла назначения.
- Нумерация блоков в одном целевом файле: `[1]`, `[2]`, ...
- Блок заканчивается, когда пропадает префикс `#///` или `///@`.

## 4) Что документировать в первую очередь

- `backend/app/modules/robots/service.py`:
  - жизненный цикл `/api/robots/history-backtest`
  - приоритет источников данных
  - логика fallback по свечам/истории
- `backend/app/modules/robots/trading/backtest/engine.py`:
  - цикл симуляции
  - правила исполнения и risk checks
- `frontend/src/pages/TestingPage.tsx`:
  - контракт формы backtest
  - маппинг интервалов свечей

## 5) Быстрый чек перед запуском сканера

- Включен Source Scanner v2.
- Для прогона выбран правильный профиль (backend или frontend).
- Маркеры в коде используют ровно тот префикс, который задан в `Start`.
- В целевом vault уже есть `Working Folder` или есть права на его создание.

## 6) Массовая разметка новых файлов

Скрипт `scripts/apply_obsidian_scanner_markers.py` проходит по:

- `backend/app/**/*.py`
- `alembic/**/*.py`
- `frontend/src/**/*.{ts,tsx,js,jsx}`

и вставляет стандартный блок маркеров только в файлы, где ещё нет `#///EPIC` / `///@EPIC`.  
Запуск из корня репозитория:

```bash
python scripts/apply_obsidian_scanner_markers.py
```

После добавления новых модулей достаточно снова выполнить команду.

