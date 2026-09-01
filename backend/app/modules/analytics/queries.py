#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesAnalyticsQueries [1]
#/// Исходный модуль `backend/app/modules/analytics/queries.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/analytics/queries.py
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import text


def build_accounts_summary_query(
        user_id: int,
        include_inactive: bool = False,
        min_total_value: Optional[float] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения сводки по всем портфелям пользователя.
    """
    base_query = """
                 SELECT
                     pa.id,
                     pa.account_id::text,                    -- Явно приводим к тексту
                     pa.account_name,
                     COALESCE(pa.account_type, 'unknown') as account_type,  -- Заменяем NULL
                     COALESCE(pa.account_status, 'active') as account_status, -- Заменяем NULL
                     ps.snapshot_date as last_snapshot_date,
                     ps.total_amount_portfolio as total_value,
                     COALESCE(ps.currency, 'RUB') as currency,  -- Значение по умолчанию
                     (SELECT COUNT(*) FROM portfolio_positions WHERE snapshot_id = ps.id) as positions_count,
                     pa.last_token_id,
                     ps.daily_yield,
                     ps.expected_yield
                 FROM portfolio_accounts pa
                          LEFT JOIN LATERAL (
                     SELECT id, snapshot_date, total_amount_portfolio, currency, daily_yield, expected_yield
                     FROM portfolio_snapshots
                     WHERE account_id = pa.id
                     ORDER BY snapshot_date DESC
                         LIMIT 1
        ) ps ON true
                 WHERE pa.user_id = :user_id \
                 """

    params = {"user_id": user_id}
    conditions = []

    if not include_inactive:
        conditions.append("UPPER(pa.account_status) = 'OPEN'")

    if min_total_value is not None:
        conditions.append("ps.total_amount_portfolio >= :min_total_value")
        params["min_total_value"] = min_total_value

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " ORDER BY ps.total_amount_portfolio DESC NULLS LAST"

    return base_query, params

def build_account_history_query(
        account_id: int,
        days: int = 30,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        include_empty: bool = False,
        interval: Optional[str] = None,  # 'day', 'week', 'month'
        order: str = "asc",
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для истории снимков портфеля.

    Args:
        account_id: ID счета
        days: количество дней (если не указан from_date)
        from_date: начальная дата
        to_date: конечная дата
        include_empty: включать ли дни без снимков
        interval: интервал агрегации
        order: направление сортировки неагрегированной истории

    Returns:
        tuple: (SQL запрос, параметры)
    """
    params = {"account_id": account_id}
    conditions = ["account_id = :account_id"]
    order_direction = "DESC" if order.lower() == "desc" else "ASC"

    # Обработка дат
    if from_date:
        conditions.append("snapshot_date >= :from_date")
        params["from_date"] = from_date
    elif days:
        conditions.append("snapshot_date >= :from_date")
        params["from_date"] = datetime.utcnow() - timedelta(days=days)

    if to_date:
        conditions.append("snapshot_date <= :to_date")
        params["to_date"] = to_date

    # Выбор полей в зависимости от интервала
    if interval == 'day':
        select_fields = """
            DATE(snapshot_date) as date,
            MAX(total_amount_portfolio) as total_value,
            SUM(daily_yield) as daily_yield,
            AVG(expected_yield) as expected_yield
        """
        group_by = "DATE(snapshot_date)"
        order_by = f"date {order_direction}"
    elif interval == 'week':
        select_fields = """
            DATE_TRUNC('week', snapshot_date) as date,
            MAX(total_amount_portfolio) as total_value,
            SUM(daily_yield) as daily_yield,
            AVG(expected_yield) as expected_yield
        """
        group_by = "DATE_TRUNC('week', snapshot_date)"
        order_by = f"date {order_direction}"
    else:
        select_fields = """
            id as snapshot_id,
            snapshot_date as date,
            total_amount_portfolio as total_value,
            daily_yield,
            expected_yield
        """
        group_by = None
        order_by = f"snapshot_date {order_direction}"

    # Собираем запрос
    if group_by:
        query = f"""
            SELECT {select_fields}
            FROM portfolio_snapshots
            WHERE {' AND '.join(conditions)}
            GROUP BY {group_by}
            ORDER BY {order_by}
        """
    else:
        query = f"""
            SELECT {select_fields}
            FROM portfolio_snapshots
            WHERE {' AND '.join(conditions)}
            ORDER BY {order_by}
        """

    return query, params


def build_distribution_query(
        account_id: int,
        snapshot_id: Optional[int] = None,
        instrument_types: Optional[List[str]] = None,
        min_value: Optional[float] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для распределения активов.

    Args:
        account_id: ID счета
        snapshot_id: конкретный снимок (если None - последний)
        instrument_types: фильтр по типам инструментов
        min_value: минимальная стоимость позиции

    Returns:
        tuple: (SQL запрос, параметры)
    """
    params = {}

    # Если не указан snapshot_id, берем последний
    if snapshot_id is None:
        snapshot_subquery = """
                            SELECT id FROM portfolio_snapshots
                            WHERE account_id = :account_id
                            ORDER BY snapshot_date DESC
                                LIMIT 1 \
                            """
        params["account_id"] = account_id
        snapshot_id_placeholder = f"({snapshot_subquery})"
    else:
        snapshot_id_placeholder = ":snapshot_id"
        params["snapshot_id"] = snapshot_id

    base_query = f"""
        SELECT
            instrument_type,
            SUM(current_price * quantity) as total_value,
            COUNT(*) as count,
            AVG(current_price) as avg_price,
            MIN(current_price) as min_price,
            MAX(current_price) as max_price
        FROM portfolio_positions
        WHERE snapshot_id = {snapshot_id_placeholder}
    """

    conditions = []

    if instrument_types:
        conditions.append("instrument_type = ANY(:instrument_types)")
        params["instrument_types"] = instrument_types

    if min_value:
        conditions.append("(current_price * quantity) >= :min_value")
        params["min_value"] = min_value

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " GROUP BY instrument_type ORDER BY total_value DESC"

    return base_query, params


def build_account_ownership_check_query(
        account_id: int,
        user_id: int,
) -> tuple[str, Dict[str, Any]]:
    """Возвращает запрос для проверки принадлежности счета пользователю"""
    return """
           SELECT id, account_id, account_name, account_type, account_status
           FROM portfolio_accounts
           WHERE id = :account_id AND user_id = :user_id \
           """, {"account_id": account_id, "user_id": user_id}


def build_robot_ownership_query(
        robot_id: int,
        user_id: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Проверка: робот принадлежит пользователю."""
    return f"""
        SELECT 1 FROM robots
        WHERE id = :robot_id AND user_id = :user_id
        LIMIT 1
    """, {"robot_id": robot_id, "user_id": user_id}


def build_robot_trades_summary_query(
        robot_id: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Агрегированные метрики по сделкам робота."""
    return f"""
        SELECT
            COUNT(*) as total_trades,
            COUNT(*) FILTER (WHERE status IN ('open', 'partial')) as open_trades,
            COUNT(*) FILTER (WHERE status = 'closed') as closed_trades,
            COUNT(*) FILTER (WHERE status = 'closed' AND profit > 0) as winning_trades,
            COUNT(*) FILTER (WHERE status = 'closed' AND profit <= 0) as losing_trades,
            COALESCE(SUM(profit) FILTER (WHERE status = 'closed'), 0) as total_pnl,
            AVG(profit) FILTER (WHERE status = 'closed' AND profit > 0) as avg_profit,
            AVG(profit) FILTER (WHERE status = 'closed' AND profit <= 0) as avg_loss,
            MAX(profit) FILTER (WHERE status = 'closed') as best_trade,
            MIN(profit) FILTER (WHERE status = 'closed') as worst_trade,
            AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600)
                FILTER (WHERE status = 'closed' AND closed_at IS NOT NULL) as avg_duration_hours,
            COALESCE(SUM(commission) FILTER (WHERE status = 'closed'), 0) as total_commission
        FROM robot_trades
        WHERE robot_id = :robot_id
    """, {"robot_id": robot_id}


def build_robot_closed_pnl_series_query(
        robot_id: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Кумулятивный PnL по закрытым сделкам (для расчёта drawdown)."""
    return f"""
        SELECT profit
        FROM robot_trades
        WHERE robot_id = :robot_id AND status = 'closed'
        ORDER BY closed_at ASC
    """, {"robot_id": robot_id}


def build_user_robots_trades_aggregate_query(
        user_id: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Сводка по сделкам всех роботов пользователя (для дашборда)."""
    return f"""
        SELECT
            COUNT(*)::int as total_trades,
            COUNT(*) FILTER (WHERE t.status IN ('open', 'partial'))::int as open_trades,
            COUNT(*) FILTER (WHERE t.status = 'closed')::int as closed_trades,
            COUNT(*) FILTER (WHERE t.status = 'closed' AND t.profit > 0)::int as winning_trades,
            COUNT(*) FILTER (WHERE t.status = 'closed' AND t.profit <= 0)::int as losing_trades,
            COALESCE(SUM(t.profit) FILTER (WHERE t.status = 'closed'), 0) as total_pnl,
            COALESCE(SUM(t.commission) FILTER (WHERE t.status = 'closed'), 0) as total_commission,
            COUNT(DISTINCT t.robot_id) FILTER (WHERE t.status = 'closed')::int as robots_with_closed_trades,
            COALESCE(SUM(t.profit) FILTER (WHERE t.status = 'closed' AND t.profit > 0), 0) as sum_winning_profit,
            COALESCE(SUM(ABS(t.profit)) FILTER (WHERE t.status = 'closed' AND t.profit < 0), 0) as sum_losing_loss
        FROM robot_trades t
        INNER JOIN robots r ON r.id = t.robot_id AND r.user_id = :user_id
    """, {"user_id": user_id}


def build_user_robots_closed_pnl_series_query(
        user_id: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Закрытые сделки всех роботов пользователя по времени (drawdown / risk)."""
    return f"""
        SELECT t.profit
        FROM robot_trades t
        INNER JOIN robots r ON r.id = t.robot_id AND r.user_id = :user_id
        WHERE t.status = 'closed'
        ORDER BY t.closed_at ASC NULLS LAST, t.id ASC
    """, {"user_id": user_id}


def build_robot_recent_trades_query(
        robot_id: int,
        limit: int,
        schema: str = "public",
) -> tuple[str, Dict[str, Any]]:
    """Последние сделки робота."""
    return f"""
        SELECT id, figi, side, quantity, entry_price, exit_price,
               profit, profit_percent, status, created_at, closed_at
        FROM robot_trades
        WHERE robot_id = :robot_id
        ORDER BY created_at DESC
        LIMIT :limit
    """, {"robot_id": robot_id, "limit": limit}


def build_last_snapshot_query(
        account_id: int,
        fields: List[str] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения последнего снимка портфеля.

    Args:
        account_id: ID счета
        fields: список полей (если None - все основные)

    Returns:
        tuple: (SQL запрос, параметры)
    """
    if fields is None:
        fields = [
            'id', 'snapshot_date', 'total_amount_portfolio',
            'total_amount_shares', 'total_amount_bonds', 'total_amount_etf',
            'total_amount_currencies', 'expected_yield', 'daily_yield',
            'daily_yield_relative'
        ]

    select_fields = ', '.join(fields)

    query = f"""
        SELECT {select_fields}
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        LIMIT 1
    """

    return query, {"account_id": account_id}


def build_account_positions_query(
        snapshot_id: int,
        instrument_types: Optional[List[str]] = None,
) -> tuple[str, Dict[str, Any]]:
    """Строит запрос позиций для снимка портфеля."""
    query = """
        SELECT
            ps.id,
            ps.figi,
            ts.name AS ticker_name,
            NULLIF(TRIM(ts.shortname), '') AS short_name,
            ps.ticker,
            ps.instrument_type,
            COALESCE(d.name, ps.instrument_type) AS type_name,
            ps.quantity,
            ps.current_price,
            (ps.current_price * ps.quantity) AS total_value,
            ps.expected_yield,
            ps.daily_yield,
            ps.average_position_price,
            ps.blocked
        FROM portfolio_positions ps
        LEFT JOIN tqbr_securities ts
            ON UPPER(TRIM(replace(ps.ticker,'@',''))) = UPPER(TRIM(ts.secid))
        LEFT JOIN dictionary d
            ON d.table_name = 'PORTFOLIO_POSITIONS'
           AND d.column_name = 'INSTRUMENT_TYPE'
           AND LOWER(TRIM(d.string_value)) = LOWER(TRIM(ps.instrument_type))
           AND d.hide_from_ui = 0
        WHERE ps.snapshot_id = :snapshot_id
    """
    params: Dict[str, Any] = {"snapshot_id": snapshot_id}
    if instrument_types:
        query += " AND ps.instrument_type = ANY(:instrument_types)"
        params["instrument_types"] = instrument_types
    query += " ORDER BY total_value DESC NULLS LAST"
    return query, params


def build_instrument_type_labels_query() -> tuple[str, Dict[str, Any]]:
    """Строит запрос отображаемых наименований типов инструментов."""
    return """
        SELECT string_value, name
        FROM dictionary
        WHERE table_name = 'PORTFOLIO_POSITIONS'
          AND column_name = 'INSTRUMENT_TYPE'
          AND hide_from_ui = 0
    """, {}


def _optional_date_range_clauses(
        column: str,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        params: Dict[str, Any],
) -> List[str]:
    """Append inclusive date bounds when both ends are provided (all-time if omitted)."""
    clauses: List[str] = []
    if from_date is not None:
        clauses.append(f"{column} >= :from_date")
        params["from_date"] = from_date
    if to_date is not None:
        clauses.append(f"{column} <= :to_date")
        params["to_date"] = to_date
    return clauses


def build_account_snapshots_count_query(
        account_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
) -> tuple[str, Dict[str, Any]]:
    """COUNT snapshots for account with optional inclusive date filter."""
    params: Dict[str, Any] = {"account_id": account_id}
    conditions = ["account_id = :account_id"]
    conditions.extend(
        _optional_date_range_clauses("snapshot_date", from_date, to_date, params)
    )
    query = f"""
        SELECT COUNT(*)::int AS count
        FROM portfolio_snapshots
        WHERE {' AND '.join(conditions)}
    """
    return query, params


def build_account_snapshots_page_query(
        account_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
) -> tuple[str, Dict[str, Any]]:
    """Page of snapshots newest→oldest with optional inclusive date filter."""
    params: Dict[str, Any] = {
        "account_id": account_id,
        "limit": limit,
        "offset": offset,
    }
    conditions = ["account_id = :account_id"]
    conditions.extend(
        _optional_date_range_clauses("snapshot_date", from_date, to_date, params)
    )
    query = f"""
        SELECT
            id AS snapshot_id,
            snapshot_date AS date,
            total_amount_portfolio AS total_value,
            daily_yield,
            expected_yield
        FROM portfolio_snapshots
        WHERE {' AND '.join(conditions)}
        ORDER BY snapshot_date DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_account_operations_count_query(
        account_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        operation_type: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """COUNT operations for account with optional date and type filters."""
    params: Dict[str, Any] = {"account_id": account_id}
    conditions = ["account_id = :account_id"]
    conditions.extend(
        _optional_date_range_clauses("operation_date", from_date, to_date, params)
    )
    if operation_type:
        conditions.append("operation_type = :operation_type")
        params["operation_type"] = operation_type
    query = f"""
        SELECT COUNT(*)::int AS count
        FROM portfolio_operations
        WHERE {' AND '.join(conditions)}
    """
    return query, params


def build_account_operations_query(
        account_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        operation_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
) -> tuple[str, Dict[str, Any]]:
    """Page of account operations with dictionary labels; newest→oldest."""
    params: Dict[str, Any] = {
        "account_id": account_id,
        "limit": limit,
        "offset": offset,
    }
    conditions = ["po.account_id = :account_id"]
    conditions.extend(
        _optional_date_range_clauses("po.operation_date", from_date, to_date, params)
    )
    if operation_type:
        conditions.append("po.operation_type = :operation_type")
        params["operation_type"] = operation_type

    query = f"""
        SELECT
            po.operation_id,
            po.operation_date,
            po.operation_type,
            COALESCE(dt.name, po.operation_type) AS operation_type_name,
            po.figi,
            pt.ticker,
            COALESCE(ts.name, pt.ticker) AS ticker_name,
            NULLIF(TRIM(ts.shortname), '') AS short_name,
            po.instrument_type,
            po.quantity,
            po.price,
            po.payment,
            po.payment_currency,
            po.status,
            COALESCE(ds.name, po.status) AS status_name,
            po.extra_data
        FROM portfolio_operations po
        LEFT JOIN dictionary dt
            ON dt.table_name = 'PORTFOLIO_OPERATIONS'
           AND dt.column_name = 'OPERATION_TYPE'
           AND LOWER(TRIM(dt.string_value)) = LOWER(TRIM(po.operation_type))
           AND dt.hide_from_ui = 0
        LEFT JOIN dictionary ds
            ON ds.table_name = 'PORTFOLIO_OPERATIONS'
           AND ds.column_name = 'STATUS'
           AND LOWER(TRIM(ds.string_value)) = LOWER(TRIM(po.status))
           AND ds.hide_from_ui = 0
        LEFT JOIN LATERAL (
            SELECT pp.ticker
            FROM portfolio_positions pp
            WHERE po.figi IS NOT NULL
              AND pp.figi = po.figi
              AND pp.ticker IS NOT NULL
              AND TRIM(pp.ticker) <> ''
            ORDER BY pp.id DESC
            LIMIT 1
        ) pt ON true
        LEFT JOIN tqbr_securities ts
            ON UPPER(TRIM(replace(ts.secid, '@', ''))) = UPPER(TRIM(COALESCE(pt.ticker, po.figi)))
        WHERE {' AND '.join(conditions)}
        ORDER BY po.operation_date DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_available_instruments_query(account_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос доступных инструментов из последнего снимка."""
    return """
        SELECT DISTINCT pp.figi, pp.ticker
        FROM portfolio_positions pp
        WHERE pp.snapshot_id = (
            SELECT ps.id
            FROM portfolio_snapshots ps
            WHERE ps.account_id = :account_id
            ORDER BY ps.snapshot_date DESC
            LIMIT 1
        )
        ORDER BY pp.figi
    """, {"account_id": account_id}


def build_account_instrument_chart_query(
        account_id: int,
        from_date: datetime,
        to_date: datetime,
        figis: List[str],
        no_filter: int,
) -> tuple[str, Dict[str, Any]]:
    """Строит запрос временных рядов стоимости инструментов."""
    return """
        SELECT
            ps.snapshot_date,
            pp.figi,
            MAX(pp.ticker) AS ticker,
            MAX(COALESCE(ts.name, ts.shortname)) AS name,
            SUM(pp.quantity * pp.current_price) AS value
        FROM portfolio_snapshots ps
        JOIN portfolio_positions pp ON pp.snapshot_id = ps.id
        LEFT JOIN tqbr_securities ts
            ON UPPER(TRIM(replace(pp.ticker, '@', ''))) = UPPER(TRIM(ts.secid))
        WHERE ps.account_id = :account_id
          AND ps.snapshot_date >= :from_date
          AND ps.snapshot_date <= :to_date
          AND (:no_filter = 1 OR pp.figi = ANY(:figis))
        GROUP BY ps.snapshot_date, pp.figi
        HAVING SUM(pp.quantity) > 0
        ORDER BY ps.snapshot_date ASC, pp.figi ASC
    """, {
        "account_id": account_id,
        "from_date": from_date,
        "to_date": to_date,
        "figis": figis,
        "no_filter": no_filter,
    }


def build_robot_status_counts_query(robot_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос количества сделок робота по статусам."""
    return """
        SELECT status, COUNT(*)::int
        FROM robot_trades
        WHERE robot_id = :robot_id
        GROUP BY status
    """, {"robot_id": robot_id}


def build_account_own_funds_query(account_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос собственных средств счета."""
    return """
        SELECT
            COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN ABS(payment) ELSE 0 END), 0)
        FROM portfolio_operations
        WHERE account_id = :account_id
    """, {"account_id": account_id}


def build_account_latest_value_query(account_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос последнего значения портфеля."""
    return """
        SELECT total_amount_portfolio, snapshot_date
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        LIMIT 1
    """, {"account_id": account_id}


def build_account_first_input_date_query(account_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос даты первого пополнения счета."""
    return """
        SELECT MIN(operation_date)
        FROM portfolio_operations
        WHERE account_id = :account_id
          AND operation_type = 'OPERATION_TYPE_INPUT'
    """, {"account_id": account_id}


def build_account_inflow_before_query(
        account_id: int,
        from_date: datetime,
) -> tuple[str, Dict[str, Any]]:
    """Строит запрос чистого притока средств до даты."""
    return """
        SELECT
            COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN ABS(payment) ELSE 0 END), 0)
        FROM portfolio_operations
        WHERE account_id = :account_id
          AND operation_date < :from_date
    """, {"account_id": account_id, "from_date": from_date}


def build_fifo_operations_query(
        account_id: int,
        to_date: datetime,
) -> tuple[str, Dict[str, Any]]:
    """Строит запрос операций для FIFO-расчета."""
    return """
        SELECT operation_date, operation_type, figi, quantity, price, payment
        FROM portfolio_operations
        WHERE account_id = :account_id
          AND operation_date <= :to_date
          AND figi IS NOT NULL
          AND operation_type IN (
              'OPERATION_TYPE_BUY', 'OPERATION_TYPE_BUY_CARD', 'OPERATION_TYPE_BUY_MARGIN',
              'OPERATION_TYPE_SELL', 'OPERATION_TYPE_SELL_CARD', 'OPERATION_TYPE_SELL_MARGIN'
          )
        ORDER BY operation_date ASC, id ASC
    """, {"account_id": account_id, "to_date": to_date}


def build_account_period_operations_query(
        account_id: int,
        from_date: datetime,
        to_date: datetime,
) -> tuple[str, Dict[str, Any]]:
    """Строит запрос операций счета за отчетный период."""
    return """
        SELECT operation_type, payment
        FROM portfolio_operations
        WHERE account_id = :account_id
          AND operation_date >= :from_date
          AND operation_date <= :to_date
    """, {
        "account_id": account_id,
        "from_date": from_date,
        "to_date": to_date,
    }


def build_account_unrealized_pnl_query(account_id: int) -> tuple[str, Dict[str, Any]]:
    """Строит запрос нереализованного PnL последнего снимка."""
    return """
        SELECT COALESCE(SUM(pp.quantity * (pp.current_price - pp.average_position_price)), 0)
        FROM portfolio_positions pp
        WHERE pp.snapshot_id = (
            SELECT ps.id
            FROM portfolio_snapshots ps
            WHERE ps.account_id = :account_id
            ORDER BY ps.snapshot_date DESC
            LIMIT 1
        )
    """, {"account_id": account_id}