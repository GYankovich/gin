#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsQueries [1]
#/// Исходный модуль `backend/app/modules/robots/queries.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/queries.py
from typing import Optional, List, Dict, Any
from datetime import datetime


# === ЗАПРОСЫ ДЛЯ РОБОТОВ ===
def build_get_user_robots_query(
        robot_status: Optional[List[int]] = None,
        robot_type: Optional[List[int]] = None,
        robot_name: Optional[str] = None,
        token_type: Optional[List[int]] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        schema: str = "ganaly"
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения всех роботов пользователя
    Возвращает: id, name, token_type, type, status_name, last_started, last_error
    """
    base_query = """
                 SELECT
                     r.id,
                     r.user_id,
                     t.id,
                     t.name,
                     t.is_active,
                     t.token_type,
                     da.name,
                     r.name,
                     r.type as type_id,
                     dt.name as type_name,
                     r.status as status_id,
                     ds.name as status_name,
                     r.config,
                     r.last_started,
                     r.last_error,
                     r.last_error_at,
                     r.last_stopped,
                     r.usercre,
                     r.date_creation,
                     r.usermod,
                     r.date_modification
                 FROM {schema}.robots r
                          JOIN {schema}.api_tokens t ON r.token_id = t.id
                          join {schema}.dictionary da ON t.token_type = da.num_value AND da.table_name = 'TOKEN' AND da.column_name = 'TYPE'
                          JOIN {schema}.dictionary dt ON r.type = dt.num_value AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                          JOIN {schema}.dictionary ds ON r.status = ds.num_value AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
                 WHERE r.user_id = :user_id
                     AND R.STATUS != 0
                 """.format(schema=schema)

    params = {}
    conditions = []

    # Фильтр по статусу
    if robot_status:
        placeholders = ','.join([f':status_{i}' for i in range(len(robot_status))])
        conditions.append(f"r.status IN ({placeholders})")
        for i, status in enumerate(robot_status):
            params[f'status_{i}'] = status

    # Фильтр по типу робота
    if robot_type:
        placeholders = ','.join([f':type_{i}' for i in range(len(robot_type))])
        conditions.append(f"r.type IN ({placeholders})")
        for i, rt in enumerate(robot_type):
            params[f'type_{i}'] = rt

    # Фильтр по названию робота (поиск)
    if robot_name:
        conditions.append("r.name ILIKE :robot_name")
        params["robot_name"] = f"%{robot_name}%"

    # Фильтр по типу токена
    if token_type:
        placeholders = ','.join([f':token_type_{i}' for i in range(len(token_type))])
        conditions.append(f"t.token_type IN ({placeholders})")
        for i, tt in enumerate(token_type):
            params[f'token_type_{i}'] = tt

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    # Сортировка
    sort_mapping = {
        "status": "r.status",
        "name": "r.name",
        "token_type": "t.token_type"
    }

    if sort_by and sort_by in sort_mapping:
        order = "ASC" if sort_order.lower() == "asc" else "DESC"
        base_query += f" ORDER BY {sort_mapping[sort_by]} {order}, r.date_creation DESC"
    else:
        base_query += " ORDER BY r.date_creation DESC"

    # Пагинация
    base_query += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    return base_query, params


def build_count_user_robots_query(
        robot_status: Optional[List[int]] = None,
        robot_type: Optional[List[int]] = None,
        robot_name: Optional[str] = None,
        token_type: Optional[List[int]] = None,
        schema: str = "ganaly"
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для подсчета количества роботов пользователя
    """
    base_query = """
                 SELECT COUNT(*)
                 FROM {schema}.robots r
                          JOIN {schema}.api_tokens t ON r.token_id = t.id
                 WHERE r.user_id = :user_id
                     AND R.STATUS != 0
                 """.format(schema=schema)

    params = {}
    conditions = []

    if robot_status:
        placeholders = ','.join([f':status_{i}' for i in range(len(robot_status))])
        conditions.append(f"r.status IN ({placeholders})")
        for i, status in enumerate(robot_status):
            params[f'status_{i}'] = status

    if robot_type:
        placeholders = ','.join([f':type_{i}' for i in range(len(robot_type))])
        conditions.append(f"r.type IN ({placeholders})")
        for i, rt in enumerate(robot_type):
            params[f'type_{i}'] = rt

    if robot_name:
        conditions.append("r.name ILIKE :robot_name")
        params["robot_name"] = f"%{robot_name}%"

    if token_type:
        placeholders = ','.join([f':token_type_{i}' for i in range(len(token_type))])
        conditions.append(f"t.token_type IN ({placeholders})")
        for i, tt in enumerate(token_type):
            params[f'token_type_{i}'] = tt

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    return base_query, params


def build_get_robot_by_id_query(schema: str = "ganaly") -> str:
    """Получение робота по ID с проверкой владельца"""
    return """
           SELECT
               r.id,
               r.user_id,
               t.id,
               t.name,
               t.is_active,
               t.token_type,
               da.name,
               r.name,
               r.type as type_id,
               dt.name as type_name,
               r.status as status_id,
               ds.name as status_name,
               r.config,
               r.last_started,
               r.last_error,
               r.last_error_at,
               r.last_stopped,
               r.usercre,
               r.date_creation,
               r.usermod,
               r.date_modification
           FROM {schema}.robots r
                    JOIN {schema}.api_tokens t ON r.token_id = t.id 
                    join {schema}.dictionary da ON t.token_type = da.num_value AND da.table_name = 'TOKEN' AND da.column_name = 'TYPE'
                    JOIN {schema}.dictionary dt ON r.type = dt.num_value AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                    JOIN {schema}.dictionary ds ON r.status = ds.num_value AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
           WHERE r.id = :robot_id AND r.user_id = :user_id and status != 0
           """.format(schema=schema)


def build_check_robot_name_exists_query(schema: str = "ganaly") -> str:
    """Проверка уникальности имени робота для пользователя"""
    return """
           SELECT id FROM {schema}.robots
           WHERE user_id = :user_id AND name = :name and status != 0\
           """.format(schema=schema)


def build_create_robot_query(schema: str = "ganaly") -> str:
    """Создание нового робота"""
    return """
           INSERT INTO {schema}.robots
               (user_id, token_id, name, type, status, usercre, date_creation)
           VALUES
               (:user_id, :token_id, :name, :type, :status, :usercre, :created_at)
               RETURNING
               id, user_id, token_id, name, type, status,
               last_started, last_error, last_error_at,
               usercre, date_creation, usermod, date_modification
           """.format(schema=schema)


#
# def build_update_robot_last_started_query() -> str:
#     """Обновление времени последнего запуска робота"""
#     return """
#            UPDATE ganaly.robots
#            SET last_started = :now,
#                usermod = :usermod,
#                date_modification = :now
#            WHERE id = :robot_id \
#            """

#
# def build_update_robot_error_query() -> str:
#     """Обновление информации об ошибке робота"""
#     return """
#            UPDATE ganaly.robots
#            SET last_error = :error,
#                last_error_at = :now,
#                usermod = :usermod,
#                date_modification = :now
#            WHERE id = :robot_id \
#            """
#
#
def build_soft_delete_robot_query(schema: str = "ganaly") -> str:
    """Мягкое удаление робота (status=0)"""
    return """
           UPDATE {schema}.robots
           SET status = 0,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id AND user_id = :user_id AND status != 0
               RETURNING id
           """.format(schema=schema)

# app/modules/robots/queries.py

def build_change_robot_status_query(schema: str = "ganaly") -> str:
    """
    Изменение статуса робота
    status: 1 - активен, 2 - остановлен
    """
    return """
           UPDATE {schema}.robots
           SET status = :status,
               last_started = CASE WHEN :status = 1 THEN :now ELSE last_started END,
               last_stopped = CASE WHEN :status = 2 THEN :now ELSE last_stopped END,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id AND user_id = :user_id
               RETURNING
               id, user_id, token_id, name, type, status, config,
               last_started, last_error, last_error_at,
               usercre, date_creation, usermod, date_modification
           """.format(schema=schema)


def build_update_robot_config_query(schema: str = "ganaly") -> str:
    """
    Обновление конфигурации робота.
    """
    return """
           UPDATE {schema}.robots
           SET config = :config,
               usermod = :usermod,
               date_modification = :now
           WHERE id = :robot_id AND user_id = :user_id AND status != 0
               RETURNING id \
           """.format(schema=schema)


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

def build_check_token_query(schema: str = "ganaly") -> str:
    """Проверка существования и активности токена"""
    return """
           SELECT id
           FROM {schema}.api_tokens
           WHERE id = :token_id AND user_id = :user_id AND is_active = 1
           """.format(schema=schema)



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

