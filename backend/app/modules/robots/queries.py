# app/modules/robots/queries.py
from typing import Optional, List, Dict, Any
from datetime import datetime


def build_get_user_robots_query(
        include_inactive: bool = False,
        robot_type: Optional[str] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения всех роботов пользователя
    """
    base_query = """
                 SELECT
                     id, user_id, token_id, name, display_name, description, robot_type,
                     strategy_params, max_daily_loss, max_position_size, allowed_instruments,
                     status, is_active,
                     total_trades, successful_trades, total_profit, total_profit_percent,
                     created_at, updated_at, started_at, stopped_at, last_error, last_error_at,
                     last_heartbeat_at
                 FROM ganaly.trading_robots
                 WHERE user_id = :user_id \
                 """

    params = {"user_id": ":user_id"}
    conditions = []

    if not include_inactive:
        conditions.append("is_active = 1")

    if robot_type:
        conditions.append("robot_type = :robot_type")
        params["robot_type"] = robot_type

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " ORDER BY created_at DESC"

    return base_query, params


def build_get_robot_by_id_query() -> str:
    """Получение робота по ID с проверкой владельца"""
    return """
           SELECT
               id, user_id, token_id, name, display_name, description, robot_type,
               strategy_params, max_daily_loss, max_position_size, allowed_instruments,
               status, is_active,
               total_trades, successful_trades, total_profit, total_profit_percent,
               created_at, updated_at, started_at, stopped_at, last_error, last_error_at,
               last_heartbeat_at
           FROM ganaly.trading_robots
           WHERE id = :robot_id AND user_id = :user_id \
           """


def build_check_robot_ownership_query() -> str:
    """Проверка принадлежности робота пользователю"""
    return """
           SELECT id FROM ganaly.trading_robots
           WHERE id = :robot_id AND user_id = :user_id \
           """


def build_check_robot_name_exists_query() -> str:
    """Проверка уникальности имени робота для пользователя"""
    return """
           SELECT id FROM ganaly.trading_robots
           WHERE user_id = :user_id AND name = :name \
           """


def build_create_robot_query() -> str:
    """Создание нового робота"""
    return """
           INSERT INTO ganaly.trading_robots
           (user_id, token_id, name, display_name, description, robot_type, strategy_params,
            max_daily_loss, max_position_size, allowed_instruments,
            status, is_active, created_at)
           VALUES
               (:user_id, :token_id, :name, :display_name, :description, :robot_type, :strategy_params,
                :max_daily_loss, :max_position_size, :allowed_instruments,
                :status, :is_active, :created_at)
               RETURNING
            id, user_id, token_id, name, display_name, description, robot_type,
            strategy_params, max_daily_loss, max_position_size, allowed_instruments,
            status, is_active,
            total_trades, successful_trades, total_profit, total_profit_percent,
            created_at, updated_at, started_at, stopped_at, last_error, last_error_at,
            last_heartbeat_at \
           """


def build_update_robot_query(fields: List[str]) -> tuple[str, Dict[str, Any]]:
    """
    Динамически строит запрос обновления робота
    """
    base_query = """
                 UPDATE ganaly.trading_robots
                 SET {updates}, updated_at = :now
                 WHERE id = :robot_id AND user_id = :user_id
                     RETURNING
                     id, user_id, token_id, name, display_name, description, robot_type,
                     strategy_params, max_daily_loss, max_position_size, allowed_instruments,
                     status, is_active,
                     total_trades, successful_trades, total_profit, total_profit_percent,
                     created_at, updated_at, started_at, stopped_at, last_error, last_error_at,
                     last_heartbeat_at \
                 """

    field_mapping = {
        "name": "name = :name",
        "display_name": "display_name = :display_name",
        "description": "description = :description",
        "token_id": "token_id = :token_id",
        "strategy_params": "strategy_params = :strategy_params",
        "max_daily_loss": "max_daily_loss = :max_daily_loss",
        "max_position_size": "max_position_size = :max_position_size",
        "allowed_instruments": "allowed_instruments = :allowed_instruments",
        "status": "status = :status",
        "is_active": "is_active = :is_active"
    }

    updates = [field_mapping[f] for f in fields if f in field_mapping]

    if not updates:
        return "", {}

    query = base_query.format(updates=", ".join(updates))

    params = {
        "robot_id": ":robot_id",
        "user_id": ":user_id",
        "now": ":now"
    }

    for field in fields:
        if field in field_mapping:
            params[field] = f":{field}"

    return query, params


def build_update_robot_heartbeat_query() -> str:
    """Обновление времени heartbeat робота"""
    return """
           UPDATE ganaly.trading_robots
           SET last_heartbeat_at = :now
           WHERE id = :robot_id \
           """


def build_delete_robot_query() -> str:
    """Удаление робота"""
    return """
           DELETE FROM ganaly.trading_robots
           WHERE id = :robot_id AND user_id = :user_id
               RETURNING id \
           """


def build_get_active_robots_for_scheduler_query() -> str:
    """Получение активных роботов для планировщика"""
    return """
           SELECT
               id, user_id, token_id, name, display_name, robot_type,
               strategy_params, status, last_heartbeat_at
           FROM ganaly.trading_robots
           WHERE is_active = 1 AND status = 'active' \
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
    """Обновление статистики робота после сделки"""
    return """
           UPDATE ganaly.trading_robots
           SET total_trades = total_trades + 1,
               successful_trades = successful_trades + :success_increment,
               total_profit = total_profit + :profit,
               total_profit_percent = total_profit_percent + :profit_percent
           WHERE id = :robot_id \
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
                     robot_display_name,
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


# === ЗАПРОСЫ ДЛЯ ТОКЕНОВ ===

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
    Учитывает refresh_interval_minutes и время последнего использования
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


def build_update_token_refresh_interval_query() -> str:
    """
    Обновление интервала обновления токена
    """
    return """
           UPDATE ganaly.api_tokens
           SET refresh_interval_minutes = :interval,
               updated_at = :now
           WHERE id = :token_id AND user_id = :user_id
               RETURNING id \
           """


# === ЗАПРОСЫ ДЛЯ ПОРТФЕЛЕЙ ===

def build_get_account_by_id_query() -> str:
    """Получение счета по ID"""
    return """
           SELECT id FROM ganaly.portfolio_accounts
           WHERE user_id = :user_id AND account_id = :account_id \
           """


def build_get_accounts_by_user_query() -> str:
    """
    Получение всех счетов пользователя
    """
    return """
           SELECT
               id,
               account_id,
               account_type,
               account_name,
               account_status,
               opened_date,
               last_sync_at,
               created_at
           FROM ganaly.portfolio_accounts
           WHERE user_id = :user_id AND is_active = 1
           ORDER BY created_at DESC \
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


def build_update_account_sync_time_query() -> str:
    """
    Обновление времени синхронизации счета
    """
    return """
           UPDATE ganaly.portfolio_accounts
           SET last_sync_at = :now
           WHERE id = :account_id \
           """


def build_get_last_snapshot_query() -> str:
    """
    Получение последнего снимка портфеля
    """
    return """
           SELECT
               id,
               snapshot_date,
               total_amount_portfolio,
               currency
           FROM ganaly.portfolio_snapshots
           WHERE account_id = :account_id
           ORDER BY snapshot_date DESC
               LIMIT 1 \
           """


def build_get_snapshots_by_account_query(
        account_id: int,
        limit: int = 10,
        from_date: Optional[datetime] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Получение снимков портфеля по счету
    """
    base_query = """
                 SELECT
                     id,
                     snapshot_date,
                     total_amount_portfolio,
                     daily_yield,
                     expected_yield,
                     currency
                 FROM ganaly.portfolio_snapshots
                 WHERE account_id = :account_id \
                 """

    params = {"account_id": account_id, "limit": limit}

    if from_date:
        base_query += " AND snapshot_date >= :from_date"
        params["from_date"] = from_date

    base_query += " ORDER BY snapshot_date DESC LIMIT :limit"

    return base_query, params


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


def build_get_positions_by_snapshot_query(snapshot_id: int) -> tuple[str, Dict[str, Any]]:
    """
    Получение всех позиций снимка
    """
    query = """
            SELECT
                id,
                figi,
                ticker,
                instrument_type,
                quantity,
                current_price,
                (current_price * quantity) as total_value,
                expected_yield,
                daily_yield,
                average_position_price,
                blocked
            FROM ganaly.portfolio_positions
            WHERE snapshot_id = :snapshot_id
            ORDER BY total_value DESC \
            """

    params = {"snapshot_id": snapshot_id}
    return query, params


# === ЗАПРОСЫ ДЛЯ СИГНАЛОВ ===

def build_create_signal_query() -> str:
    """Создание записи о сигнале"""
    return """
           INSERT INTO ganaly.robot_signals
           (robot_id, figi, ticker, signal_type, signal_strength,
            indicators, price_at_signal, created_at)
           VALUES
               (:robot_id, :figi, :ticker, :signal_type, :signal_strength,
                :indicators, :price_at_signal, :created_at)
               RETURNING id \
           """


def build_get_signals_by_robot_query(
        robot_id: int,
        limit: int = 50,
        executed_only: bool = False
) -> tuple[str, Dict[str, Any]]:
    """
    Получение сигналов робота
    """
    query = """
            SELECT
                id,
                figi,
                ticker,
                signal_type,
                signal_strength,
                indicators,
                price_at_signal,
                was_executed,
                executed_trade_id,
                created_at
            FROM ganaly.robot_signals
            WHERE robot_id = :robot_id \
            """

    params = {"robot_id": robot_id, "limit": limit}

    if executed_only:
        query += " AND was_executed = 1"

    query += " ORDER BY created_at DESC LIMIT :limit"

    return query, params


def build_mark_signal_executed_query() -> str:
    """Отметка сигнала как исполненного"""
    return """
           UPDATE ganaly.robot_signals
           SET was_executed = 1, executed_trade_id = :trade_id
           WHERE id = :signal_id \
           """


# === ЗАПРОСЫ ДЛЯ СТАТИСТИКИ ===

def build_get_robot_stats_query(robot_id: int) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения статистики робота
    """
    query = """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as successful_trades,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as failed_trades,
                COALESCE(AVG(profit), 0) as avg_profit,
                MAX(profit) as max_profit,
                MIN(profit) as min_profit,
                SUM(profit) as total_profit,
                MAX(closed_at) as last_trade_at
            FROM ganaly.robot_trades
            WHERE robot_id = :robot_id AND status = 'closed' \
            """

    params = {"robot_id": robot_id}
    return query, params


def build_get_trades_by_day_query(robot_id: int, days: int = 30) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для группировки сделок по дням
    """
    query = """
            SELECT
                DATE(created_at) as day,
                COUNT(*) as trade_count,
                SUM(profit) as daily_profit
            FROM ganaly.robot_trades
            WHERE robot_id = :robot_id
              AND status = 'closed'
              AND created_at >= CURRENT_DATE - INTERVAL ':days days'
            GROUP BY DATE(created_at)
            ORDER BY day DESC \
            """

    params = {"robot_id": robot_id, "days": days}
    return query, params


def build_get_robot_health_query(robot_id: int) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для проверки здоровья робота
    """
    query = """
            SELECT
                status,
                is_active,
                last_error,
                last_error_at,
                started_at,
                stopped_at,
                last_heartbeat_at,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_heartbeat_at)) as seconds_since_heartbeat
            FROM ganaly.trading_robots
            WHERE id = :robot_id \
            """

    params = {"robot_id": robot_id}
    return query, params


def build_get_all_robots_health_query() -> str:
    """
    Получение здоровья всех активных роботов
    """
    return """
           SELECT
               id,
               name,
               display_name,
               robot_type,
               status,
               is_active,
               last_heartbeat_at,
               EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_heartbeat_at)) as seconds_since_heartbeat
           FROM ganaly.trading_robots
           WHERE is_active = 1
           ORDER BY
               CASE WHEN last_heartbeat_at IS NULL THEN 0 ELSE 1 END,
               last_heartbeat_at ASC \
           """