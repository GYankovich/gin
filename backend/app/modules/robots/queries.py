# app/modules/robots/queries.py
from typing import Optional, List, Dict, Any
from datetime import datetime


# === ЗАПРОСЫ ДЛЯ РОБОТОВ ===

def build_get_user_robots_query(
        include_inactive: bool = False,
        robot_type: Optional[int] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения всех роботов пользователя
    """
    base_query = """
                 SELECT
                     r.id,
                     r.user_id,
                     r.token_id,
                     r.name,
                     r.type as type_id,
                     dt.name as type_name,
                     r.status as status_id,
                     ds.name as status_name,
                     r.config,
                     r.last_started,
                     r.last_error,
                     r.last_error_at,
                     r.usercre,
                     r.date_creation,
                     r.usermod,
                     r.date_modification,
                     COUNT(DISTINCT t.id) as total_trades,
                     SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as successful_trades,
                     COALESCE(SUM(t.profit), 0) as total_profit
                 FROM ganaly.robots r
                          LEFT JOIN ganaly.robot_trades t ON r.id = t.robot_id
                          LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                          LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
                 WHERE r.user_id = :user_id \
                 """

    params = {"user_id": ":user_id"}
    conditions = []

    if not include_inactive:
        # Получаем ID статуса "Включен" из dictionary
        conditions.append("r.status = (SELECT id FROM ganaly.dictionary WHERE table_name = 'ROBOT' AND column_name = 'STATUS' AND num_value = 1)")

    if robot_type:
        # Получаем ID типа робота из dictionary
        conditions.append("r.type = (SELECT id FROM ganaly.dictionary WHERE table_name = 'ROBOT' AND column_name = 'TYPE' AND num_value = :robot_type)")
        params["robot_type"] = robot_type

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " GROUP BY r.id, dt.name, ds.name ORDER BY r.date_creation DESC"

    return base_query, params


def build_get_robot_by_id_query() -> str:
    """Получение робота по ID с проверкой владельца"""
    return """
           SELECT
               r.id,
               r.user_id,
               r.token_id,
               r.name,
               r.type as type_id,
               dt.name as type_name,
               dt.num_value as type_value,
               r.status as status_id,
               ds.name as status_name,
               ds.num_value as status_value,
               r.config,
               r.last_started,
               r.last_error,
               r.last_error_at,
               r.usercre,
               r.date_creation,
               r.usermod,
               r.date_modification,
               COUNT(DISTINCT t.id) as total_trades,
               SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as successful_trades,
               COALESCE(SUM(t.profit), 0) as total_profit
           FROM ganaly.robots r
                    LEFT JOIN ganaly.robot_trades t ON r.id = t.robot_id
                    LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                    LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
           WHERE r.id = :robot_id AND r.user_id = :user_id
           GROUP BY r.id, dt.name, dt.num_value, ds.name, ds.num_value \
           """


def build_check_robot_ownership_query() -> str:
    """Проверка принадлежности робота пользователю"""
    return """
           SELECT id FROM ganaly.robots
           WHERE id = :robot_id AND user_id = :user_id \
           """


def build_check_robot_name_exists_query() -> str:
    """Проверка уникальности имени робота для пользователя"""
    return """
           SELECT id FROM ganaly.robots
           WHERE user_id = :user_id AND name = :name \
           """


def build_create_robot_query() -> str:
    """Создание нового робота"""
    return """
           INSERT INTO ganaly.robots
               (user_id, token_id, name, type, status, config, usercre, date_creation)
           VALUES
               (:user_id, :token_id, :name, :type, :status, :config, :usercre, :created_at)
               RETURNING
            id, user_id, token_id, name, type, status, config,
            last_started, last_error, last_error_at,
            usercre, date_creation, usermod, date_modification \
           """


def build_update_robot_query(fields: List[str]) -> tuple[str, Dict[str, Any]]:
    """
    Динамически строит запрос обновления робота
    """
    base_query = """
                 UPDATE ganaly.robots
                 SET {updates}, usermod = :usermod, date_modification = :now
                 WHERE id = :robot_id AND user_id = :user_id
                     RETURNING
                     id, user_id, token_id, name, type, status, config,
                     last_started, last_error, last_error_at,
                     usercre, date_creation, usermod, date_modification \
                 """

    field_mapping = {
        "name": "name = :name",
        "token_id": "token_id = :token_id",
        "type": "type = :type",
        "status": "status = :status",
        "config": "config = :config",
        "last_started": "last_started = :last_started",
        "last_error": "last_error = :last_error",
        "last_error_at": "last_error_at = :last_error_at"
    }

    updates = [field_mapping[f] for f in fields if f in field_mapping]

    if not updates:
        return "", {}

    query = base_query.format(updates=", ".join(updates))

    params = {
        "robot_id": ":robot_id",
        "user_id": ":user_id",
        "usermod": ":usermod",
        "now": ":now"
    }

    for field in fields:
        if field in field_mapping:
            params[field] = f":{field}"

    return query, params


def build_update_robot_last_started_query() -> str:
    """Обновление времени последнего запуска робота"""
    return """
           UPDATE ganaly.robots
           SET last_started = :now,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id \
           """


def build_update_robot_error_query() -> str:
    """Обновление информации об ошибке робота"""
    return """
           UPDATE ganaly.robots
           SET last_error = :error,
               last_error_at = :now,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id \
           """


def build_delete_robot_query() -> str:
    """Удаление робота"""
    return """
           DELETE FROM ganaly.robots
           WHERE id = :robot_id AND user_id = :user_id
               RETURNING id \
           """


# === ЗАПРОСЫ ДЛЯ СПРАВОЧНИКОВ ===

def build_get_dictionary_values_query(
        table_name: str,
        column_name: str,
        include_hidden: bool = False
) -> tuple[str, Dict[str, Any]]:
    """
    Получение значений из справочника
    """
    query = """
            SELECT
                id,
                num_value,
                string_value,
                name,
                description
            FROM ganaly.dictionary
            WHERE table_name = :table_name
              AND column_name = :column_name \
            """

    params = {
        "table_name": table_name,
        "column_name": column_name
    }

    if not include_hidden:
        query += " AND hide_from_ui = 0"

    query += " ORDER BY num_value NULLS LAST, name"

    return query, params


def build_get_dictionary_id_by_value_query() -> str:
    """
    Получение ID записи в справочнике по значению
    """
    return """
           SELECT id FROM ganaly.dictionary
           WHERE table_name = :table_name
             AND column_name = :column_name
             AND num_value = :num_value \
           """


# === ЗАПРОСЫ ДЛЯ СДЕЛОК ===

def build_get_robot_trades_query(
        robot_id: int,
        limit: int = 100,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения сделок робота
    """
    base_query = """
                 SELECT
                     id, robot_id, figi, ticker, instrument_type,
                     side, quantity, price, total_amount,
                     commission, commission_currency, order_id,
                     profit, profit_percent, status,
                     created_at, closed_at
                 FROM ganaly.robot_trades
                 WHERE robot_id = :robot_id \
                 """

    params = {"robot_id": robot_id, "limit": limit}
    conditions = []

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if from_date:
        conditions.append("created_at >= :from_date")
        params["from_date"] = from_date

    if to_date:
        conditions.append("created_at <= :to_date")
        params["to_date"] = to_date

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " ORDER BY created_at DESC LIMIT :limit"

    return base_query, params


def build_create_trade_query() -> str:
    """Создание новой сделки"""
    return """
           INSERT INTO ganaly.robot_trades
           (robot_id, figi, ticker, instrument_type, side,
            quantity, price, total_amount, order_id, status, created_at)
           VALUES
               (:robot_id, :figi, :ticker, :instrument_type, :side,
                :quantity, :price, :total_amount, :order_id, :status, :created_at)
               RETURNING id \
           """


def build_close_trade_query() -> str:
    """Закрытие сделки"""
    return """
           UPDATE ganaly.robot_trades
           SET status = 'closed',
               closed_at = :closed_at,
               profit = :profit,
               profit_percent = :profit_percent
           WHERE id = :trade_id AND status = 'open'
               RETURNING id, robot_id, profit, profit_percent \
           """


def build_update_robot_stats_after_trade_query() -> str:
    """Обновление статистики робота после сделки (теперь через агрегацию, но оставим для совместимости)"""
    return """
        -- Статистика теперь считается на лету через агрегацию
        SELECT 1
    """


def build_get_trade_stats_query(robot_id: int) -> tuple[str, Dict[str, Any]]:
    """Получение статистики по сделкам робота"""
    query = """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as profitable_trades,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as loss_trades,
                COALESCE(AVG(profit), 0) as avg_profit,
                COALESCE(SUM(profit), 0) as total_profit,
                MAX(profit) as max_profit,
                MIN(profit) as min_profit,
                MAX(created_at) as last_trade_at
            FROM ganaly.robot_trades
            WHERE robot_id = :robot_id AND status = 'closed' \
            """

    params = {"robot_id": robot_id}
    return query, params


# === ЗАПРОСЫ ДЛЯ ЛОГОВ ===

def build_create_robot_log_query() -> str:
    """
    Создание записи в логах роботов
    """
    return """
           INSERT INTO ganaly.robot_logs
           (robot_name, robot_version, token_id, user_id,
            started_at, endpoint, request_data)
           VALUES
               (:robot_name, :robot_version, :token_id, :user_id,
                :started_at, :endpoint, :request_data)
               RETURNING id \
           """


def build_update_robot_log_success_query() -> str:
    """
    Обновление записи в логах при успешном выполнении
    """
    return """
           UPDATE ganaly.robot_logs
           SET finished_at = :finished_at,
               duration_ms = :duration_ms,
               response_data = :response_data,
               success = 1
           WHERE id = :log_id \
           """


def build_update_robot_log_error_query() -> str:
    """
    Обновление записи в логах при ошибке
    """
    return """
           UPDATE ganaly.robot_logs
           SET finished_at = :finished_at,
               duration_ms = :duration_ms,
               error_message = :error_message,
               success = 0
           WHERE id = :log_id \
           """


def build_get_robot_logs_query(
        robot_name: Optional[str] = None,
        user_id: Optional[int] = None,
        token_id: Optional[int] = None,
        success: Optional[bool] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
) -> tuple[str, Dict[str, Any]]:
    """
    Получение логов роботов с фильтрацией
    """
    base_query = """
                 SELECT
                     id,
                     robot_name,
                     robot_version,
                     token_id,
                     user_id,
                     endpoint,
                     started_at,
                     finished_at,
                     duration_ms,
                     success,
                     error_message,
                     response_data,
                     created_at
                 FROM ganaly.robot_logs
                 WHERE 1=1 \
                 """

    params = {"limit": limit, "offset": offset}
    conditions = []

    if robot_name:
        conditions.append("robot_name = :robot_name")
        params["robot_name"] = robot_name

    if user_id:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    if token_id:
        conditions.append("token_id = :token_id")
        params["token_id"] = token_id

    if success is not None:
        conditions.append("success = :success")
        params["success"] = 1 if success else 0

    if from_date:
        conditions.append("started_at >= :from_date")
        params["from_date"] = from_date

    if to_date:
        conditions.append("started_at <= :to_date")
        params["to_date"] = to_date

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " ORDER BY started_at DESC LIMIT :limit OFFSET :offset"

    return base_query, params


def build_get_robot_log_stats_query() -> str:
    """
    Получение статистики по логам роботов
    """
    return """
           SELECT
               robot_name,
               COUNT(*) as total_runs,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
               SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
               AVG(duration_ms) as avg_duration_ms,
               MAX(started_at) as last_run
           FROM ganaly.robot_logs
           GROUP BY robot_name
           ORDER BY last_run DESC \
           """


def build_clean_old_logs_query(days: int = 30) -> tuple[str, Dict[str, Any]]:
    """
    Очистка старых логов
    """
    query = """
            DELETE FROM ganaly.robot_logs
            WHERE created_at < CURRENT_TIMESTAMP - INTERVAL ':days days'
                RETURNING id \
            """

    params = {"days": days}
    return query, params


# === ЗАПРОСЫ ДЛЯ ТОКЕНОВ (ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ) ===

def build_get_token_with_refresh_info_query() -> str:
    """
    Получение информации о токене для проверки необходимости обновления
    """
    return """
           SELECT
               id,
               user_id,
               token,
               refresh_interval_minutes,
               last_used_at,
               created_at
           FROM ganaly.api_tokens
           WHERE id = :token_id AND is_active = 1 \
           """


def build_get_tokens_for_update_query() -> str:
    """
    Получение всех активных токенов, которые требуют обновления
    """
    return """
           SELECT
               id,
               user_id,
               token,
               refresh_interval_minutes,
               last_used_at,
               created_at
           FROM ganaly.api_tokens
           WHERE is_active = 1
             AND (
               last_used_at IS NULL
                   OR last_used_at <= CURRENT_TIMESTAMP - (refresh_interval_minutes || ' minutes')::INTERVAL
               )
           ORDER BY
               CASE WHEN last_used_at IS NULL THEN 0 ELSE 1 END,
               last_used_at ASC \
           """


def build_get_user_tokens_query(user_id: int, include_inactive: bool = False) -> tuple[str, Dict[str, Any]]:
    """
    Получение всех токенов пользователя
    """
    query = """
            SELECT
                id,
                user_id,
                token_type,
                token,
                token_name,
                is_active,
                refresh_interval_minutes,
                last_used_at,
                created_at
            FROM ganaly.api_tokens
            WHERE user_id = :user_id \
            """

    params = {"user_id": user_id}

    if not include_inactive:
        query += " AND is_active = 1"

    query += " ORDER BY created_at DESC"

    return query, params


def build_update_token_last_used_query() -> str:
    """
    Обновление времени последнего использования токена
    """
    return """
           UPDATE ganaly.api_tokens
           SET last_used_at = :now
           WHERE id = :token_id
               RETURNING id, refresh_interval_minutes \
           """


# === ЗАПРОСЫ ДЛЯ ПОРТФЕЛЕЙ (ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ) ===

def build_get_account_by_id_query() -> str:
    """Получение счета по ID"""
    return """
           SELECT id FROM ganaly.portfolio_accounts
           WHERE user_id = :user_id AND account_id = :account_id \
           """


def build_create_account_query() -> str:
    """
    Создание нового счета
    """
    return """
           INSERT INTO ganaly.portfolio_accounts
           (user_id, account_id, account_type, account_name, account_status, opened_date, is_active)
           VALUES
               (:user_id, :account_id, :account_type, :account_name, :account_status, :opened_date, 1)
               RETURNING id \
           """


def build_update_account_query() -> str:
    """
    Обновление информации о счете
    """
    return """
           UPDATE ganaly.portfolio_accounts
           SET account_name = :account_name,
               account_status = :account_status,
               last_sync_at = :now,
               updated_at = :now
           WHERE id = :db_account_id \
           """


def build_create_snapshot_query() -> str:
    """
    Создание нового снимка портфеля
    """
    return """
           INSERT INTO ganaly.portfolio_snapshots
           (account_id, snapshot_date, total_amount_portfolio, total_amount_shares,
            total_amount_bonds, total_amount_etf, total_amount_currencies,
            total_amount_futures, total_amount_options, expected_yield,
            daily_yield, daily_yield_relative, currency)
           VALUES
               (:account_id, :snapshot_date, :total_amount_portfolio, :total_amount_shares,
                :total_amount_bonds, :total_amount_etf, :total_amount_currencies,
                :total_amount_futures, :total_amount_options, :expected_yield,
                :daily_yield, :daily_yield_relative, :currency)
               RETURNING id \
           """


def build_create_position_query() -> str:
    """
    Создание позиции в снимке
    """
    return """
           INSERT INTO ganaly.portfolio_positions
           (snapshot_id, figi, instrument_type, quantity,
            average_position_price, current_price, expected_yield,
            daily_yield, blocked, ticker, class_code,
            position_uid, instrument_uid)
           VALUES
               (:snapshot_id, :figi, :instrument_type, :quantity,
                :average_position_price, :current_price, :expected_yield,
                :daily_yield, :blocked, :ticker, :class_code,
                :position_uid, :instrument_uid) \
           """

# === ДОПОЛНИТЕЛЬНЫЕ ЗАПРОСЫ ДЛЯ РОБОТОВ ===

def build_update_robot_heartbeat_query() -> str:
    """
    Обновление времени последнего heartbeat робота
    """
    return """
           UPDATE ganaly.robots
           SET last_heartbeat_at = :now,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id
           """


def build_get_active_robots_for_scheduler_query() -> str:
    """
    Получение активных роботов для планировщика
    Возвращает роботов со статусом "Включен" (num_value = 1)
    """
    return """
           SELECT
               r.id,
               r.user_id,
               r.token_id,
               r.name,
               dt.num_value as type_value,
               dt.name as type_name,
               r.config,
               ds.num_value as status_value,
               r.last_started,
               r.last_heartbeat_at
           FROM ganaly.robots r
                    LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                    LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
           WHERE ds.num_value = 1  -- только активные роботы (статус "Включен")
           ORDER BY r.date_creation DESC \
           """


def build_get_robot_health_query(robot_id: int) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для проверки здоровья робота
    """
    query = """
            SELECT
                r.id,
                r.name,
                dt.name as type_name,
                ds.name as status_name,
                ds.num_value as status_value,
                r.last_error,
                r.last_error_at,
                r.last_started,
                r.last_heartbeat_at,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - r.last_heartbeat_at)) as seconds_since_heartbeat
            FROM ganaly.robots r
                     LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                     LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
            WHERE r.id = :robot_id
            """

    params = {"robot_id": robot_id}
    return query, params


def build_get_all_robots_health_query() -> str:
    """
    Получение здоровья всех активных роботов
    """
    return """
           SELECT
               r.id,
               r.name,
               dt.name as type_name,
               ds.name as status_name,
               ds.num_value as status_value,
               r.last_heartbeat_at,
               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - r.last_heartbeat_at)) as seconds_since_heartbeat
           FROM ganaly.robots r
                    LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                    LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
           WHERE ds.num_value = 1  -- только активные роботы
           ORDER BY
               CASE WHEN r.last_heartbeat_at IS NULL THEN 0 ELSE 1 END,
               r.last_heartbeat_at ASC
           """


def build_get_robot_config_schema_query(robot_type: int) -> tuple[str, Dict[str, Any]]:
    """
    Получение схемы конфигурации для типа робота
    """
    query = """
            SELECT
                config_key,
                config_value,
                description,
                is_required
            FROM ganaly.robot_configs
            WHERE robot_type = :robot_type
            ORDER BY config_key
            """

    params = {"robot_type": robot_type}
    return query, params


def build_get_robot_types_query() -> tuple[str, Dict[str, Any]]:
    """
    Получение всех типов роботов из справочника
    """
    query = """
            SELECT
                id,
                num_value,
                name,
                description
            FROM ganaly.dictionary
            WHERE table_name = 'ROBOT'
              AND column_name = 'TYPE'
              AND hide_from_ui = 0
            ORDER BY num_value
            """

    params = {}
    return query, params


def build_get_robot_statuses_query() -> tuple[str, Dict[str, Any]]:
    """
    Получение всех статусов роботов из справочника
    """
    query = """
            SELECT
                id,
                num_value,
                name,
                description
            FROM ganaly.dictionary
            WHERE table_name = 'ROBOT'
              AND column_name = 'STATUS'
              AND hide_from_ui = 0
            ORDER BY num_value
            """

    params = {}
    return query, params


def build_get_active_robots_by_type_query(robot_type: int) -> tuple[str, Dict[str, Any]]:
    """
    Получение активных роботов определенного типа
    """
    query = """
            SELECT
                r.id,
                r.user_id,
                r.token_id,
                r.name,
                r.config,
                t.token
            FROM ganaly.robots r
                     JOIN ganaly.api_tokens t ON r.token_id = t.id
            WHERE r.type = :robot_type
              AND r.status = (SELECT id FROM ganaly.dictionary WHERE table_name = 'ROBOT' AND column_name = 'STATUS' AND num_value = 1)
              AND t.is_active = 1
            """

    params = {"robot_type": robot_type}
    return query, params


def build_update_robot_config_query() -> str:
    """
    Обновление конфигурации робота
    """
    return """
           UPDATE ganaly.robots
           SET config = config || :config,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id AND user_id = :user_id
               RETURNING id
           """


def build_get_robot_stats_by_date_range_query(
        robot_id: int,
        from_date: datetime,
        to_date: datetime
) -> tuple[str, Dict[str, Any]]:
    """
    Получение статистики робота за период
    """
    query = """
            SELECT
                DATE(created_at) as trade_date,
                COUNT(*) as trades_count,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as profitable_count,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as loss_count,
                COALESCE(SUM(profit), 0) as total_profit,
                AVG(profit) as avg_profit,
                MAX(profit) as max_profit,
                MIN(profit) as min_profit
            FROM ganaly.robot_trades
            WHERE robot_id = :robot_id
              AND status = 'closed'
              AND created_at BETWEEN :from_date AND :to_date
            GROUP BY DATE(created_at)
            ORDER BY trade_date DESC
            """

    params = {
        "robot_id": robot_id,
        "from_date": from_date,
        "to_date": to_date
    }
    return query, params
