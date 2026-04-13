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
                     (SELECT COUNT(*) FROM ganaly.portfolio_positions WHERE snapshot_id = ps.id) as positions_count,
                     pa.last_token_id,
                     ps.daily_yield,
                     ps.expected_yield
                 FROM ganaly.portfolio_accounts pa
                          LEFT JOIN LATERAL (
                     SELECT id, snapshot_date, total_amount_portfolio, currency, daily_yield, expected_yield
                     FROM ganaly.portfolio_snapshots
                     WHERE account_id = pa.id
                     ORDER BY snapshot_date DESC
                         LIMIT 1
        ) ps ON true
                 WHERE pa.user_id = :user_id \
                 """

    params = {"user_id": user_id}
    conditions = []

    if not include_inactive:
        conditions.append("pa.account_status != 'closed'")

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
        interval: Optional[str] = None  # 'day', 'week', 'month'
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

    Returns:
        tuple: (SQL запрос, параметры)
    """
    params = {"account_id": account_id}
    conditions = ["account_id = :account_id"]

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
        order_by = "date ASC"
    elif interval == 'week':
        select_fields = """
            DATE_TRUNC('week', snapshot_date) as date,
            MAX(total_amount_portfolio) as total_value,
            SUM(daily_yield) as daily_yield,
            AVG(expected_yield) as expected_yield
        """
        group_by = "DATE_TRUNC('week', snapshot_date)"
        order_by = "date ASC"
    else:
        select_fields = """
            id as snapshot_id,
            snapshot_date as date,
            total_amount_portfolio as total_value,
            daily_yield,
            expected_yield
        """
        group_by = None
        order_by = "snapshot_date ASC"

    # Собираем запрос
    if group_by:
        query = f"""
            SELECT {select_fields}
            FROM ganaly.portfolio_snapshots
            WHERE {' AND '.join(conditions)}
            GROUP BY {group_by}
            ORDER BY {order_by}
        """
    else:
        query = f"""
            SELECT {select_fields}
            FROM ganaly.portfolio_snapshots
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
                            SELECT id FROM ganaly.portfolio_snapshots
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
        FROM ganaly.portfolio_positions
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


def build_account_ownership_check_query() -> str:
    """Возвращает запрос для проверки принадлежности счета пользователю"""
    return """
           SELECT id, account_id, account_name, account_type, account_status
           FROM ganaly.portfolio_accounts
           WHERE id = :account_id AND user_id = :user_id \
           """


def build_robot_ownership_query(schema: str = "ganaly") -> str:
    """Проверка: робот принадлежит пользователю."""
    return f"""
        SELECT 1 FROM {schema}.robots
        WHERE id = :robot_id AND user_id = :user_id
        LIMIT 1
    """


def build_robot_trades_summary_query(schema: str = "ganaly") -> str:
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
        FROM {schema}.robot_trades
        WHERE robot_id = :robot_id
    """


def build_robot_closed_pnl_series_query(schema: str = "ganaly") -> str:
    """Кумулятивный PnL по закрытым сделкам (для расчёта drawdown)."""
    return f"""
        SELECT profit
        FROM {schema}.robot_trades
        WHERE robot_id = :robot_id AND status = 'closed'
        ORDER BY closed_at ASC
    """


def build_user_robots_trades_aggregate_query(schema: str = "ganaly") -> str:
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
        FROM {schema}.robot_trades t
        INNER JOIN {schema}.robots r ON r.id = t.robot_id AND r.user_id = :user_id
    """


def build_user_robots_closed_pnl_series_query(schema: str = "ganaly") -> str:
    """Закрытые сделки всех роботов пользователя по времени (drawdown / risk)."""
    return f"""
        SELECT t.profit
        FROM {schema}.robot_trades t
        INNER JOIN {schema}.robots r ON r.id = t.robot_id AND r.user_id = :user_id
        WHERE t.status = 'closed'
        ORDER BY t.closed_at ASC NULLS LAST, t.id ASC
    """


def build_robot_recent_trades_query(schema: str = "ganaly") -> str:
    """Последние сделки робота."""
    return f"""
        SELECT id, figi, side, quantity, entry_price, exit_price,
               profit, profit_percent, status, created_at, closed_at
        FROM {schema}.robot_trades
        WHERE robot_id = :robot_id
        ORDER BY created_at DESC
        LIMIT :limit
    """


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
        FROM ganaly.portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        LIMIT 1
    """

    return query, {"account_id": account_id}