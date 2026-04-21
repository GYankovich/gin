# app/modules/robots/trading/queries.py
"""
SQL запросы для торгового робота
"""


def build_get_active_trading_robots_query() -> str:
    """
    Получение активных торговых роботов для шедулера
    Возвращает: robot_id, user_id, token_id, token, config
    """
    return """
           SELECT
               r.id as robot_id,
               r.user_id,
               r.token_id,
               r.config,
               at.token as token_value
           FROM {schema}.robots r
        INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
           WHERE r.type = :robot_type
             AND r.status = :status_active
             AND at.is_active = 1 \
           """


def build_collect_scheduled_trading_robots_query() -> str:
    """
    Получение торговых роботов с расписанием для stage1_collect.
    """
    return """
           SELECT
               r.id as robot_id,
               r.user_id,
               r.token_id,
               r.config,
               at.token as token_value,
               rs.schedule_type,
               rs.interval_seconds,
               rs.start_time,
               rs.end_time,
               rs.weekdays
           FROM {schema}.robots r
        INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
         LEFT JOIN {schema}.robot_schedules rs ON r.id = rs.robot_id AND rs.is_active = 1
           WHERE r.type = 2
             AND r.status = 1
             AND at.is_active = 1 \
           """


def build_get_robot_config_query() -> str:
    """
    Получение конфигурации робота из БД
    """
    return """
           SELECT config FROM {schema}.robots
           WHERE id = :robot_id AND status = 1 \
           """


def build_update_robot_status_query() -> str:
    """
    Обновление статуса робота
    """
    return """
           UPDATE {schema}.robots
           SET status = :status, date_modification = :now
           WHERE id = :robot_id
               RETURNING id \
           """


def build_create_execution_log_query() -> str:
    """
    Создание записи о запуске сессии
    """
    return """
           INSERT INTO {schema}.robot_execution_logs
               (robot_id, action_type, status, created_at)
           VALUES (:robot_id, :action_type, :status, :now)
               RETURNING id \
           """


def build_update_execution_log_query() -> str:
    """
    Обновление записи выполнения
    """
    return """
           UPDATE {schema}.robot_execution_logs
           SET status = :status,
               message = :message,
               execution_time_ms = :execution_time_ms,
               error_stack = :error_stack
           WHERE id = :log_id
               RETURNING id \
           """


def build_create_api_log_query() -> str:
    """
    Создание записи об API вызове
    """
    return """
           INSERT INTO {schema}.robot_logs
           (robot_name, robot_version, token_id, user_id, endpoint,
            request_data, started_at, execution_log_id)
           VALUES
               (:robot_name, :robot_version, :token_id, :user_id, :endpoint,
               :request_data, :started_at, :execution_log_id)
               RETURNING id \
           """


def build_update_api_log_success_query() -> str:
    """
    Обновление успешного API вызова
    """
    return """
           UPDATE {schema}.robot_logs
           SET finished_at = :finished_at,
               duration_ms = :duration_ms,
               response_data = :response_data,
               response_status = :response_status,
               success = 1
           WHERE id = :log_id
               RETURNING id \
           """


def build_update_api_log_error_query() -> str:
    """
    Обновление ошибочного API вызова
    """
    return """
           UPDATE {schema}.robot_logs
           SET finished_at = :finished_at,
               duration_ms = :duration_ms,
               error_message = :error_message,
               success = 0
           WHERE id = :log_id
               RETURNING id \
           """


def build_save_signals_query() -> str:
    """
    Сохранение сигналов в БД
    """
    return """
           INSERT INTO {schema}.robot_signals
           (robot_id, figi, signal_type, signal_strength, price_at_signal,
            was_executed, created_at)
           VALUES
               (:robot_id, :figi, :signal_type, :signal_strength, :price,
               0, :now)
               RETURNING id \
           """


def build_save_trades_query() -> str:
    """
    Сохранение сделок в БД
    """
    return """
           INSERT INTO {schema}.robot_trades
           (robot_id, figi, side, quantity, price, total_amount,
            entry_price, commission, status, order_id, created_at)
           VALUES
               (:robot_id, :figi, :side, :quantity, :price, :total_amount,
               :entry_price, :commission, :status, :order_id, :now)
               RETURNING id \
           """


def build_update_trade_status_query() -> str:
    """
    Обновление статуса сделки
    """
    return """
           UPDATE {schema}.robot_trades
           SET status = :status,
               filled_quantity = COALESCE(:filled_quantity, filled_quantity),
               avg_fill_price = COALESCE(:executed_price, avg_fill_price),
               commission = COALESCE(:commission, commission),
               updated_at = :now
           WHERE order_id = :order_id
               RETURNING id \
           """


def build_update_trade_entry_price_query() -> str:
    """
    Обновление цены входа для исполненной заявки
    """
    return """
           UPDATE {schema}.robot_trades
           SET entry_price = :entry_price,
               quantity = :quantity,
               total_amount = :total_amount,
               status = 'open'
           WHERE order_id = :order_id AND status IN ('pending', 'partial')
               RETURNING id \
           """


def build_get_open_positions_query() -> str:
    """
    Получение открытых позиций робота.
    """
    return """
           SELECT id, figi, side, quantity, entry_price, status
           FROM {schema}.robot_trades
           WHERE robot_id = :robot_id AND status IN ('open', 'partial') \
           """


def build_close_trade_query() -> str:
    """
    Закрытие сделки в БД.
    """
    return """
           UPDATE {schema}.robot_trades
           SET status = 'closed',
               exit_price = :exit_price,
               closed_at = :now,
               profit = :profit,
               profit_percent = :profit_percent
           WHERE id = :trade_id \
           """