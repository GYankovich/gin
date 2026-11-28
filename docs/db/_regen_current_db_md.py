"""Regenerate docs/db/Текущая база данных.md from the live gin database."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.core.database import engine

OUT = Path(__file__).with_name("Текущая база данных.md")
TODAY = date.today().isoformat()

# Domain buckets for TOC / cards. Every public relation must land in exactly one.
DOMAINS: list[tuple[str, str, list[str]]] = [
    (
        "Пользователи, пакеты и токены",
        "users",
        [
            "api_tokens",
            "app_config",
            "email_confirmation",
            "package",
            "package_feature",
            "user",
            "user_email",
            "user_phone",
            "user_token",
        ],
    ),
    (
        "Портфель и заявки",
        "portfolio",
        [
            "portfolio_account_stats",
            "portfolio_accounts",
            "portfolio_operations",
            "portfolio_orders",
            "portfolio_positions",
            "portfolio_snapshot_daily",
            "portfolio_snapshots",
            "token_portfolio_accounts",
        ],
    ),
    (
        "Роботы",
        "robots",
        [
            "robot_config_history",
            "robot_cycles",
            "robot_day_stats",
            "robot_decisions",
            "robot_fills",
            "robot_orders",
            "robot_sessions",
            "robot_signals",
            "robots",
        ],
    ),
    (
        "Бэктест",
        "backtest",
        [
            "backtest_comparisons",
            "backtest_daily_universe",
            "backtest_decisions",
            "backtest_equity_curve",
            "backtest_execution_events",
            "backtest_metrics",
            "backtest_orders",
            "backtest_portfolio_snapshots",
            "backtest_positions",
            "backtest_risk_events",
            "backtest_runs",
            "backtest_signals",
            "backtest_trades",
            "backtest_universe_membership",
            "market_backtests",
            "optimization_batch_items",
            "optimization_batches",
        ],
    ),
    (
        "Рынок и справочники",
        "market",
        [
            "candle_load_jobs",
            "candles_cache",
            "dictionary",
            "equity_dividend_events",
            "instrument_cache",
            "market_cache_leases",
            "market_candles",
            "market_depth_latest",
            "market_instruments",
            "market_snapshot",
            "market_snapshot_data",
            "market_snapshot_data_history",
            "market_snapshot_history",
            "market_ticks",
            "moex_index_cache",
            "securities_static",
            "shared_market_candles",
            "tqbr_securities",
        ],
    ),
    (
        "Bybit",
        "bybit",
        [
            "bybit_funding_history",
            "bybit_lsr_history",
            "bybit_open_interest_history",
        ],
    ),
    (
        "Служебные",
        "ops",
        [
            "alembic_version",
            "background_jobs",
            "background_worker_leases",
            "cron_table",
            "external_api_logs",
            "osengine_ingest_heartbeat",
            "outbound_message",
        ],
    ),
]

# Кратко: зачем таблица и кто её трогает в runtime.
BLURBS: dict[str, tuple[str, str]] = {
    "user": (
        "Tenant приложения: логин, пароль, тариф, status.",
        "Auth и все FK «чей это объект»; UI настроек.",
    ),
    "package": (
        "Тарифный план.",
        "FK с user.package_code; админка пакетов.",
    ),
    "package_feature": (
        "Флаги возможностей тарифа (вкладки/лимиты).",
        "Проверка доступа к фичам UI/API.",
    ),
    "user_email": (
        "Почты пользователя (текущая + история через status).",
        "Регистрация, сброс пароля, outbound_message.",
    ),
    "user_phone": (
        "Телефоны пользователя (текущий + история через status).",
        "Профиль / будущие SMS; outbound_message.",
    ),
    "user_token": (
        "Сессии входа (JWT/refresh, устройство, last_seen).",
        "Логин, logout, список сессий в настройках.",
    ),
    "email_confirmation": (
        "Одноразовые коды до/вместо сессии (register, reset).",
        "POST /api/auth и смежные confirm-flow.",
    ),
    "app_config": (
        "Глобальные key→value настройки приложения.",
        "TTL сессий и прочие runtime-флаги без релиза.",
    ),
    "api_tokens": (
        "Брокерский ключ пользователя (T-Invest / Bybit), секрет шифруется.",
        "Settings UI; роботы берут token_id для live.",
    ),
    "token_portfolio_accounts": (
        "Какие брокерские счета видны под данным api_token.",
        "Синк портфеля и выбор счёта роботом (не is_trading).",
    ),
    "portfolio_accounts": (
        "Справочник брокерских счетов пользователя.",
        "Дашборд, связка с токеном, корень snapshots/orders/ops.",
    ),
    "portfolio_snapshots": (
        "Снимки equity/PnL счёта во времени.",
        "Пишет portfolio_updater; читает дашборд/аналитика.",
    ),
    "portfolio_positions": (
        "Позиции внутри одного snapshot.",
        "Дашборд позиций; источник ticker для ops.",
    ),
    "portfolio_operations": (
        "Операции брокера по счёту (сделки, вводы, комиссии).",
        "Синк T-Invest/Bybit operations; аналитика / KPI.",
    ),
    "portfolio_orders": (
        "Журнал заявок по счёту (active + history), не audit робота.",
        "Пишет portfolio_updater + live trading_core; Bybit history есть, у T-Invest — в основном open/GetOrders.",
    ),
    "portfolio_snapshot_daily": (
        "Дневной mart по счёту (EOD equity, day_delta).",
        "Пишется при синке; дашборд/графики без тяжёлого DISTINCT ON.",
    ),
    "portfolio_account_stats": (
        "Сводные KPI счёта (own_funds, win-rate, avg monthly ROI).",
        "Mart при синке; dashboard и analytics вместо тяжёлых агрегатов.",
    ),
    "robots": (
        "Торговый робот paper/live: конфиг JSON, status, type, token_id.",
        "CRUD роботов, старт/стоп сессии; торговый счёт в config.core.accountId.",
    ),
    "robot_config_history": (
        "Неизменяемые версии конфига.",
        "Аудит изменений настроек робота.",
    ),
    "robot_sessions": (
        "Один Start→Stop запуска.",
        "Корень audit trail; mode/account_id/virtual_capital.",
    ),
    "robot_cycles": (
        "Торговый цикл (poll/bar/tick) внутри сессии.",
        "Пишет engine; к нему вяжутся signals/decisions/orders.",
    ),
    "robot_signals": (
        "Сырой сигнал стратегии в цикле.",
        "Монитор робота / glass-box.",
    ),
    "robot_decisions": (
        "Решение risk/sizing по сигналу.",
        "Монитор; почему ордер выставлен или нет.",
    ),
    "robot_orders": (
        "Ордера audit робота (не portfolio_orders).",
        "Live/paper execution trail.",
    ),
    "robot_fills": (
        "Исполнения ордеров робота.",
        "PnL цикла и reconcile.",
    ),
    "robot_day_stats": (
        "Дневной rollup W/L по роботу.",
        "Пишет audit после цикла; быстрые KPI без скана fills.",
    ),
    "backtest_runs": (
        "Прогон бэктеста (параметры, статус, robot_id опционально).",
        "UI бэктеста + background_jobs heavy lane.",
    ),
    "backtest_comparisons": (
        "Сравнение нескольких прогонов.",
        "UI сравнения результатов.",
    ),
    "market_backtests": (
        "Очередь/мета market-level бэктестов.",
        "Пакетные прогоны по рынку.",
    ),
    "backtest_daily_universe": (
        "Вселенная инструментов на день прогона.",
        "Симулятор фильтрует тикеры по дню.",
    ),
    "backtest_universe_membership": (
        "Состав universe конкретного run.",
        "Фиксация, на чём считали прогон.",
    ),
    "backtest_signals": (
        "Сигналы прогона.",
        "Glass-box / отладка стратегии.",
    ),
    "backtest_decisions": (
        "Решения прогона.",
        "Glass-box risk path.",
    ),
    "backtest_orders": (
        "Ордера симуляции.",
        "Отчёт и метрики исполнения.",
    ),
    "backtest_trades": (
        "Сделки симуляции.",
        "PnL и trade list в UI.",
    ),
    "backtest_positions": (
        "Позиции по ходу прогона.",
        "Отчёты / equity path.",
    ),
    "backtest_portfolio_snapshots": (
        "Снимки портфеля прогона.",
        "Кривая и аналитика run.",
    ),
    "backtest_equity_curve": (
        "Точки equity curve.",
        "График капитала в UI.",
    ),
    "backtest_metrics": (
        "Итоговые метрики (Sharpe, DD, …).",
        "Карточка результата / сравнение.",
    ),
    "backtest_execution_events": (
        "События исполнения (glass-box).",
        "Отладка fill/slippage модели.",
    ),
    "backtest_risk_events": (
        "Срабатывания risk-правил в прогоне.",
        "Почему сделка отклонена.",
    ),
    "optimization_batches": (
        "Батч перебора параметров.",
        "Оптимизатор → много backtest_runs.",
    ),
    "optimization_batch_items": (
        "Один набор параметров в батче.",
        "Статус/связь item → run.",
    ),
    "candles_cache": (
        "Кэш OHLCV для роботов и бэктеста.",
        "Чтение стратегиями; наполнение load jobs / брокером.",
    ),
    "shared_market_candles": (
        "Общие свечи между контурами.",
        "Дедуп загрузки рынка.",
    ),
    "market_candles": (
        "Свечи market-контура.",
        "Снапшоты/исследования рынка.",
    ),
    "market_ticks": (
        "Тиковые данные.",
        "Тонкий поток цен (если включён ingest).",
    ),
    "market_depth_latest": (
        "Последний стакан.",
        "UI/стратегии, которым нужен depth.",
    ),
    "candle_load_jobs": (
        "Задачи догрузки истории свечей.",
        "Воркеры заполняют candles_cache.",
    ),
    "market_instruments": (
        "Справочник инструментов (ticker↔figi).",
        "Резолв символов в ордерах и синке.",
    ),
    "instrument_cache": (
        "Кэш карточек инструментов.",
        "Быстрый lookup без похода в брокера.",
    ),
    "securities_static": (
        "Статика бумаг.",
        "Справочник/фильтры вселенной.",
    ),
    "tqbr_securities": (
        "TQBR-листинг MOEX.",
        "Universe и справочники акций.",
    ),
    "market_snapshot": (
        "Заголовок снимка рынка.",
        "Корень market_snapshot_data*.",
    ),
    "market_snapshot_data": (
        "Строки текущего снимка (тяжелые).",
        "Скрининг / universe на «сейчас».",
    ),
    "market_snapshot_history": (
        "Заголовки исторических снимков.",
        "Архив market_snapshot.",
    ),
    "market_snapshot_data_history": (
        "Строки истории снимков (самая тяжёлая).",
        "Ретро-скрининг и исследования.",
    ),
    "market_cache_leases": (
        "Лизы на куски рыночного кэша.",
        "Чтобы воркеры не дублировали загрузку.",
    ),
    "equity_dividend_events": (
        "Дивидендные события.",
        "Корректировки/календарь в аналитике.",
    ),
    "moex_index_cache": (
        "Кэш индексов MOEX.",
        "Бенчмарки и фильтры.",
    ),
    "dictionary": (
        "Справочник UI-значений (status и др.).",
        "Подписи enum в фронте/API.",
    ),
    "bybit_funding_history": (
        "История funding Bybit.",
        "Крипто-стратегии и бэктест.",
    ),
    "bybit_lsr_history": (
        "Long/short ratio Bybit.",
        "Сигналы/фильтры крипто.",
    ),
    "bybit_open_interest_history": (
        "Open interest Bybit.",
        "Сигналы/фильтры крипто.",
    ),
    "background_jobs": (
        "Очередь фоновых compute-задач.",
        "Бэктест/оптимизация на heavy/portfolio workers.",
    ),
    "background_worker_leases": (
        "Лизы lane-воркеров (кто держит heavy/portfolio).",
        "Антидубль воркеров на одной БД.",
    ),
    "cron_table": (
        "Расписание периодических задач.",
        "Хостовый/app cron.",
    ),
    "external_api_logs": (
        "Логи вызовов внешних API (брокер и др.).",
        "Отладка rate-limit/ошибок; очень объёмная.",
    ),
    "outbound_message": (
        "Очередь писем (SMTP).",
        "Коды логина/регистрации, уведомления.",
    ),
    "osengine_ingest_heartbeat": (
        "Heartbeat OSEngine ingest.",
        "Мониторинг внешнего загрузчика рынка.",
    ),
    "alembic_version": (
        "Текущая ревизия схемы.",
        "Alembic upgrade/downgrade.",
    ),
}


def fmt_rows(n: int) -> str:
    if n <= 0:
        return "0"
    return f"{n:,}".replace(",", "\u00a0")


def fmt_size(nbytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(nbytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{nbytes} B"


def fetch_meta(conn):
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    tables = conn.execute(
        text(
            """
            SELECT n.nspname AS schema,
                   c.relname AS name,
                   c.relkind AS kind,
                   GREATEST(c.reltuples::bigint, 0) AS est_rows,
                   pg_total_relation_size(c.oid) AS bytes,
                   obj_description(c.oid, 'pg_class') AS comment
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
               AND c.relkind IN ('r', 'v')
             ORDER BY c.relname
            """
        )
    ).mappings().all()

    cols = conn.execute(
        text(
            """
            SELECT c.table_name,
                   c.column_name,
                   c.data_type,
                   c.udt_name,
                   c.character_maximum_length,
                   c.numeric_precision,
                   c.numeric_scale,
                   c.is_nullable,
                   c.column_default,
                   c.ordinal_position,
                   pgd.description AS comment
              FROM information_schema.columns c
              LEFT JOIN pg_catalog.pg_statio_all_tables st
                ON st.schemaname = c.table_schema AND st.relname = c.table_name
              LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
             WHERE c.table_schema = 'public'
             ORDER BY c.table_name, c.ordinal_position
            """
        )
    ).mappings().all()

    pks = conn.execute(
        text(
            """
            SELECT tc.table_name,
                   string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS cols
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
             WHERE tc.table_schema = 'public'
               AND tc.constraint_type = 'PRIMARY KEY'
             GROUP BY tc.table_name
            """
        )
    ).mappings().all()

    uniques = conn.execute(
        text(
            """
            SELECT tc.table_name,
                   tc.constraint_name,
                   string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS cols
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
             WHERE tc.table_schema = 'public'
               AND tc.constraint_type = 'UNIQUE'
             GROUP BY tc.table_name, tc.constraint_name
             ORDER BY tc.table_name, tc.constraint_name
            """
        )
    ).mappings().all()

    fks = conn.execute(
        text(
            """
            SELECT tc.table_name AS src_table,
                   kcu.column_name AS src_column,
                   ccu.table_name AS dst_table,
                   ccu.column_name AS dst_column,
                   rc.delete_rule,
                   tc.constraint_name
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
              JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
               AND ccu.table_schema = tc.table_schema
              JOIN information_schema.referential_constraints rc
                ON rc.constraint_name = tc.constraint_name
               AND rc.constraint_schema = tc.table_schema
             WHERE tc.table_schema = 'public'
               AND tc.constraint_type = 'FOREIGN KEY'
             ORDER BY tc.table_name, kcu.ordinal_position, tc.constraint_name
            """
        )
    ).mappings().all()

    indexes = conn.execute(
        text(
            """
            SELECT tablename AS table_name,
                   indexname AS index_name,
                   indexdef
              FROM pg_indexes
             WHERE schemaname = 'public'
             ORDER BY tablename, indexname
            """
        )
    ).mappings().all()

    view_defs = conn.execute(
        text(
            """
            SELECT table_name, view_definition
              FROM information_schema.views
             WHERE table_schema = 'public'
             ORDER BY table_name
            """
        )
    ).mappings().all()

    return {
        "rev": rev,
        "tables": tables,
        "cols": cols,
        "pks": {r["table_name"]: r["cols"] for r in pks},
        "uniques": uniques,
        "fks": fks,
        "indexes": indexes,
        "views": view_defs,
    }


def type_label(row) -> str:
    dt = row["data_type"]
    udt = row["udt_name"]
    if dt == "USER-DEFINED":
        return udt
    if dt == "character varying":
        n = row["character_maximum_length"]
        return f"character varying({n})" if n else "character varying"
    if dt == "character":
        n = row["character_maximum_length"]
        return f"character({n})" if n else "character"
    if dt == "numeric":
        p, s = row["numeric_precision"], row["numeric_scale"]
        if p is not None and s is not None:
            return f"numeric({p},{s})"
        if p is not None:
            return f"numeric({p})"
        return "numeric"
    if dt == "ARRAY":
        return f"{udt}[]" if udt else "ARRAY"
    if dt == "timestamp with time zone":
        return "timestamp with time zone"
    if dt == "timestamp without time zone":
        return "timestamp without time zone"
    return dt


def default_label(val) -> str:
    if val is None:
        return ""
    s = str(val)
    if len(s) > 80:
        return s[:77] + "..."
    return s


def index_label(indexdef: str) -> str:
    # CREATE [UNIQUE] INDEX name ON table USING btree (cols) [WHERE ...]
    s = indexdef
    unique = (
        "UNIQUE "
        if " UNIQUE " in s.upper() or s.upper().startswith("CREATE UNIQUE")
        else ""
    )
    method = "btree"
    rest = s
    if " USING " in s.upper():
        after = s[s.upper().find(" USING ") + len(" USING ") :]
        method = after.split("(", 1)[0].strip() or "btree"
        rest = after
    cols = ""
    if "(" in rest:
        depth = 0
        start = rest.find("(")
        for i, ch in enumerate(rest[start:], start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    cols = rest[start : i + 1]
                    break
    where = ""
    upper = s.upper()
    if " WHERE " in upper:
        where = " WHERE " + s[upper.rfind(" WHERE ") + len(" WHERE ") :].strip()
    return f"{unique}{method} {cols}{where}".strip()


def build_doc(meta) -> str:
    tables = {r["name"]: r for r in meta["tables"]}
    table_names = sorted(n for n, r in tables.items() if r["kind"] == "r")
    view_names = sorted(n for n, r in tables.items() if r["kind"] == "v")
    ncols_by = defaultdict(int)
    cols_by = defaultdict(list)
    for c in meta["cols"]:
        cols_by[c["table_name"]].append(c)
        ncols_by[c["table_name"]] += 1

    uniques_by = defaultdict(list)
    for u in meta["uniques"]:
        uniques_by[u["table_name"]].append(u)

    fks_by = defaultdict(list)
    for fk in meta["fks"]:
        fks_by[fk["src_table"]].append(fk)

    idx_by = defaultdict(list)
    pk_names = set()
    for name, cols in meta["pks"].items():
        pk_names.add(f"{name}_pkey")
    for ix in meta["indexes"]:
        # skip primary key indexes (usually table_pkey)
        if ix["index_name"].endswith("_pkey"):
            continue
        idx_by[ix["table_name"]].append(ix)

    assigned = set()
    for _, _, names in DOMAINS:
        for n in names:
            assigned.add(n)
    leftover = [n for n in table_names if n not in assigned]
    if leftover:
        raise SystemExit(f"Tables not assigned to a domain: {leftover}")
    missing = [n for n in assigned if n not in tables]
    if missing:
        raise SystemExit(f"Domain lists unknown tables: {missing}")

    total_tables = len(table_names)
    total_cols = sum(ncols_by[n] for n in table_names)
    total_bytes = sum(int(tables[n]["bytes"] or 0) for n in table_names)
    total_fks = len(meta["fks"])
    rev = meta["rev"]

    lines: list[str] = []
    a = lines.append

    a("---")
    a("title: Текущая база данных")
    a("tags:")
    a("  - database")
    a("  - schema")
    a("  - postgres")
    a(f"alembic: {rev}")
    a("db: gin")
    a(f"updated: {TODAY}")
    a("---")
    a("")
    a("# Текущая база данных")
    a("")
    a(f"Снимок **живой** локальной PostgreSQL `gin` на {TODAY}. Это структура, а не выгрузка строк.")
    a("")
    a(f"- Ревизия Alembic: `{rev}`")
    a(f"- Таблиц: **{total_tables}** (`public`)")
    a(f"- Колонок: **{total_cols}**")
    a(f"- Представлений: **{len(view_names)}**")
    a(f"- Суммарный размер таблиц: **{fmt_size(total_bytes)}**")
    a("")
    a("Число строк — оценка планировщика (`pg_class.reltuples`), не `COUNT(*)`. Размер — `pg_total_relation_size` (таблица и индексы).")
    a("")
    a("Канон приложения — таблицы `public`. Legacy `robots` v1, `ganaly__*`, `backtest__*` и схема `backtest` сняты (миграции `0091`–`0095`). Audit роботов подробнее в [[func/trades_tables]].")
    a("")
    a("## Общая карта базы")
    a("")
    a("Ниже — **карта доменов**, не полный ER. В Reading Mode Obsidian отрисует Mermaid. Цель: понять, *где что лежит и зачем*, а детали колонок — в разделах ниже.")
    a("")
    a("### Зачем нам эти контуры")
    a("")
    a("| Контур | Зачем нужен | Главные таблицы |")
    a("|---|---|---|")
    a("| Пользователи и доступ | Аккаунты, пакеты, сессии входа, подтверждение почты | `user`, `package`, `user_token`, `email_confirmation` |")
    a("| Брокерские токены | Подключение T-Invest / Bybit без хранения ключей в коде | `api_tokens`, `token_portfolio_accounts` |")
    a("| Портфель | Дашборд: счета, снимки, операции, заявки + KPI marts | `portfolio_*`, `token_portfolio_accounts` |")
    a("| Роботы | Paper/live + audit сессия→цикл→ордер + дневные KPI | `robots`, `robot_*` |")
    a("| Бэктест | Прогоны стратегий, метрики, glass-box события | `backtest_runs`, `backtest_*`, `optimization_*` |")
    a("| Рынок и справочники | Свечи, снимки MOEX, кэши — топливо роботов и бэктеста | `candles_cache`, `shared_market_candles`, `market_*`, `dictionary` |")
    a("| Bybit-история | Funding / OI / LSR для крипто-стратегий | `bybit_*_history` |")
    a("| Служебные | Очередь воркеров, почта, cron, лизы | `background_jobs`, `outbound_message`, `cron_table` |")
    a("")
    a("### Поток данных (с высоты)")
    a("")
    a("Каждый контур ниже называет **все** свои таблицы. Стрелки — кто от кого зависит. Колонки — в карточках дальше по заметке.")
    a("")
    a("```mermaid")
    a("flowchart TB")
    a('  subgraph Access["Пользователи и доступ"]')
    a("    ACC[\"user<br/>package<br/>package_feature<br/>user_email<br/>user_phone<br/>user_token<br/>email_confirmation<br/>app_config<br/>api_tokens\"]")
    a("  end")
    a("")
    a('  subgraph Portfolio["Портфель — дашборд"]')
    a("    PA[\"portfolio_accounts<br/>token_portfolio_accounts<br/>portfolio_snapshots<br/>portfolio_positions<br/>portfolio_operations<br/>portfolio_orders<br/>portfolio_snapshot_daily<br/>portfolio_account_stats\"]")
    a("  end")
    a("")
    a('  subgraph Market["Рынок — топливо"]')
    a("    MKT[\"candles_cache<br/>shared_market_candles<br/>market_candles<br/>market_ticks<br/>market_depth_latest<br/>candle_load_jobs<br/>market_instruments<br/>instrument_cache<br/>securities_static<br/>tqbr_securities<br/>market_snapshot<br/>market_snapshot_data<br/>market_snapshot_history<br/>market_snapshot_data_history<br/>market_cache_leases<br/>equity_dividend_events<br/>moex_index_cache<br/>dictionary\"]")
    a("  end")
    a("")
    a('  subgraph Bybit["Bybit-история"]')
    a("    BYB[\"bybit_funding_history<br/>bybit_lsr_history<br/>bybit_open_interest_history\"]")
    a("  end")
    a("")
    a('  subgraph Robots["Роботы"]')
    a("    R[\"robots<br/>robot_config_history<br/>robot_sessions<br/>robot_cycles<br/>robot_signals<br/>robot_decisions<br/>robot_orders<br/>robot_fills<br/>robot_day_stats\"]")
    a("  end")
    a("")
    a('  subgraph Backtest["Бэктест"]')
    a("    BT[\"backtest_runs<br/>backtest_comparisons<br/>market_backtests<br/>backtest_daily_universe<br/>backtest_universe_membership<br/>backtest_signals<br/>backtest_decisions<br/>backtest_orders<br/>backtest_trades<br/>backtest_positions<br/>backtest_portfolio_snapshots<br/>backtest_equity_curve<br/>backtest_metrics<br/>backtest_execution_events<br/>backtest_risk_events<br/>optimization_batches<br/>optimization_batch_items\"]")
    a("  end")
    a("")
    a('  subgraph Ops["Служебные"]')
    a("    OPS[\"background_jobs<br/>background_worker_leases<br/>outbound_message<br/>external_api_logs<br/>cron_table<br/>osengine_ingest_heartbeat<br/>alembic_version\"]")
    a("  end")
    a("")
    a("  Access --> Portfolio")
    a("  Access --> Robots")
    a("  Access --> Backtest")
    a("  Bybit --> Market")
    a("  Market --> Robots")
    a("  Market --> Backtest")
    a("  Portfolio -.-> Robots")
    a("  Ops --> Backtest")
    a("  Access --> Ops")
    a("```")
    a("")
    a("### Ядро связей (канон)")
    a("")
    a("Упрощённый ER: только сущности, через которые сшиты остальные таблицы. Полные FK — в разделе ниже и в карточках таблиц.")
    a("")
    a("```mermaid")
    a("erDiagram")
    a("  user ||--o{ api_tokens : owns")
    a("  user ||--o{ portfolio_accounts : owns")
    a("  user ||--o{ robots : owns")
    a("  user ||--o{ backtest_runs : owns")
    a("")
    a("  package ||--o{ user : plans")
    a("  package ||--o{ package_feature : enables")
    a("")
    a("  api_tokens ||--o{ robots : credentials")
    a("  api_tokens ||--o{ token_portfolio_accounts : links")
    a("  portfolio_accounts ||--o{ token_portfolio_accounts : links")
    a("  portfolio_accounts ||--o{ portfolio_snapshots : has")
    a("  portfolio_accounts ||--o{ portfolio_operations : has")
    a("  portfolio_accounts ||--o{ portfolio_orders : has")
    a("  portfolio_snapshots ||--o{ portfolio_positions : has")
    a("")
    a("  robots ||--o{ robot_config_history : versions")
    a("  robots ||--o{ robot_sessions : runs")
    a("  robot_sessions ||--o{ robot_cycles : contains")
    a("  robot_cycles ||--o{ robot_signals : emits")
    a("  robot_cycles ||--o{ robot_decisions : decides")
    a("  robot_cycles ||--o{ robot_orders : places")
    a("  robot_orders ||--o{ robot_fills : fills")
    a("")
    a("  backtest_runs ||--o{ backtest_signals : has")
    a("  backtest_runs ||--o{ backtest_orders : has")
    a("  backtest_runs ||--o{ backtest_metrics : has")
    a("  backtest_runs ||--o{ backtest_execution_events : has")
    a("  optimization_batches ||--o{ optimization_batch_items : has")
    a("")
    a("  market_snapshot ||--o{ market_snapshot_data : rows")
    a("```")
    a("")
    a("### Как читать «где что»")
    a("")
    a("1. **Вход пользователя** — `user` + `package` + `user_token` / `email_confirmation`. Без этого нет мультитенантности.")
    a("2. **Доступ к брокеру** — `api_tokens` (секрет) и `token_portfolio_accounts` (какой счёт виден под токеном).")
    a("3. **Деньги на экране** — `portfolio_accounts` → snapshots / positions / operations / orders; KPI в `portfolio_account_stats` / `portfolio_snapshot_daily`. Это UI портфеля, не audit робота.")
    a("4. **Торговля** — `robots` и audit `sessions → cycles → orders/fills` (+ `robot_day_stats`). Торговый счёт — `config.core.accountId`, не флаг на связи токена.")
    a("5. **Идеи до live** — `backtest_runs` и дети; тяжёлые прогоны идут через `background_jobs`.")
    a("6. **Данные рынка** — самые тяжёлые таблицы (`market_snapshot_data_history`, `candles_cache`). Без них робот и бэктест слепы.")
    a("")
    a("### Оглавление деталей")
    a("")
    for title, _key, names in DOMAINS:
        a(f"- [[#{title}]] — {len(names)} табл.")
    if view_names:
        a(f"- [[#Представления]] — {', '.join('`public.' + v + '`' for v in view_names)}")
    a("")
    a("## Крупнейшие таблицы")
    a("")
    a("| Таблица | Оценка строк | Размер |")
    a("|---|---:|---:|")
    biggest = sorted(table_names, key=lambda n: int(tables[n]["bytes"] or 0), reverse=True)[:12]
    for n in biggest:
        r = tables[n]
        a(f"| `public.{n}` | {fmt_rows(int(r['est_rows']))} | {fmt_size(int(r['bytes']))} |")
    a("")
    a("## Внешние ключи (канон)")
    a("")
    a("| Таблица | Ограничение |")
    a("|---|---|")
    # Collapse multi-column FKs into one constraint line when same constraint
    seen_fk = set()
    for fk in meta["fks"]:
        key = (fk["src_table"], fk["constraint_name"])
        if key in seen_fk:
            continue
        seen_fk.add(key)
        group = [x for x in meta["fks"] if x["src_table"] == fk["src_table"] and x["constraint_name"] == fk["constraint_name"]]
        src_cols = ", ".join(x["src_column"] for x in group)
        dst_cols = ", ".join(x["dst_column"] for x in group)
        dst = group[0]["dst_table"]
        on_del = group[0]["delete_rule"]
        action = ""
        if on_del and on_del.upper() not in ("NO ACTION", "RESTRICT"):
            action = f" ON DELETE {on_del}"
        dst_ref = f'"{dst}"' if dst == "user" else dst
        a(f"| `{fk['src_table']}` | `FOREIGN KEY ({src_cols}) REFERENCES {dst_ref}({dst_cols}){action}` |")
    a("")
    a(f"Всего FK в `public`: **{len(seen_fk)}**.")
    a("")

    for title, _key, names in DOMAINS:
        a(f"## {title}")
        a("")
        a("| Таблица | Колонок | Оценка строк | Размер |")
        a("|---|---:|---:|---:|")
        for n in names:
            r = tables[n]
            a(f"| `public.{n}` | {ncols_by[n]} | {fmt_rows(int(r['est_rows']))} | {fmt_size(int(r['bytes']))} |")
        a("")
        for n in names:
            r = tables[n]
            a(f"### public.{n}")
            a("")
            purpose = BLURBS.get(n)
            if purpose:
                why, how = purpose
                a(f"**Зачем:** {why}")
                a("")
                a(f"**Как используется:** {how}")
                a("")
            a(f"Оценка строк {fmt_rows(int(r['est_rows']))}, размер {fmt_size(int(r['bytes']))}.")
            a("")
            a("| Колонка | Тип | NULL | По умолчанию |")
            a("|---|---|---|---|")
            for c in cols_by[n]:
                null = "да" if c["is_nullable"] == "YES" else "нет"
                a(f"| `{c['column_name']}` | `{type_label(c)}` | {null} | {default_label(c['column_default'])} |")
            a("")
            pk = meta["pks"].get(n)
            if pk:
                a(f"**Первичный ключ:** `PRIMARY KEY ({pk})`")
                a("")
            uqs = uniques_by.get(n) or []
            if uqs:
                bits = ", ".join(f"`UNIQUE ({u['cols']})`" for u in uqs)
                a(f"**Уникальность:** {bits}.")
                a("")
            fks = fks_by.get(n) or []
            if fks:
                a("**Внешние ключи:**")
                a("")
                seen = set()
                for fk in fks:
                    if fk["constraint_name"] in seen:
                        continue
                    seen.add(fk["constraint_name"])
                    group = [x for x in fks if x["constraint_name"] == fk["constraint_name"]]
                    src_cols = ", ".join(x["src_column"] for x in group)
                    dst_cols = ", ".join(x["dst_column"] for x in group)
                    dst = group[0]["dst_table"]
                    on_del = group[0]["delete_rule"]
                    action = ""
                    if on_del and on_del.upper() not in ("NO ACTION", "RESTRICT"):
                        action = f" ON DELETE {on_del}"
                    dst_ref = f'"{dst}"' if dst == "user" else dst
                    a(f"- `FOREIGN KEY ({src_cols}) REFERENCES {dst_ref}({dst_cols}){action}`")
                a("")
            ixs = idx_by.get(n) or []
            # also include unique indexes that are not table constraints? already covered via uniques mostly
            if ixs:
                a("**Индексы:**")
                a("")
                for ix in ixs:
                    a(f"- `{ix['index_name']}` — `{index_label(ix['indexdef'])}`")
                a("")

    if view_names:
        a("## Представления")
        a("")
        for v in view_names:
            a(f"### public.{v}")
            a("")
            purpose = BLURBS.get(v)
            if purpose:
                why, how = purpose
                a(f"**Зачем:** {why}")
                a("")
                a(f"**Как используется:** {how}")
                a("")
            defn = next((x["view_definition"] for x in meta["views"] if x["table_name"] == v), None)
            if defn:
                a("```sql")
                a(defn.strip().rstrip(";") + ";")
                a("```")
                a("")

    a("## Как снять заново")
    a("")
    a("```bash")
    a("PYTHONPATH=backend .venv/Scripts/python.exe docs/db/_regen_current_db_md.py")
    a("```")
    a("")
    a("Заметка собрана запросами к `pg_class` / `information_schema` / `pg_indexes` локальной БД из `.env` (`DB_NAME=gin`). Данные строк, токены и пароли в заметку не входят.")
    a("")
    return "\n".join(lines)


def main() -> None:
    with engine.connect() as conn:
        meta = fetch_meta(conn)
    doc = build_doc(meta)
    OUT.write_text(doc, encoding="utf-8")
    print(f"Wrote {OUT} ({len(doc)} bytes), alembic={meta['rev']}")


if __name__ == "__main__":
    main()
