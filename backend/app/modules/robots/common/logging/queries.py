"""
Общие SQL запросы для логирования роботов
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLoggingQueries [1]
#/// Исходный модуль `backend/app/modules/robots/common/logging/queries.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Optional

# ============================================================
# robot_execution_logs (логи выполнения/запусков роботов)
# ============================================================

def build_create_execution_log_query() -> str:
    """
    Создание записи о запуске робота
    """
    return """
           INSERT INTO robot_execution_logs
               (robot_id, action_type, status, created_at)
           VALUES
               (:robot_id, :action_type, :status, :now)
               RETURNING id \
           """


def build_update_execution_log_query() -> str:
    """
    Обновление записи выполнения робота (при завершении)
    """
    return """
           UPDATE robot_execution_logs
           SET status = :status,
               message = :message,
               execution_time_ms = :execution_time_ms,
               error_stack = :error_stack
           WHERE id = :log_id
               RETURNING id \
           """


def build_get_execution_log_query() -> str:
    """
    Получение записи выполнения по ID
    """
    return """
           SELECT id, robot_id, action_type, status, message,
                  execution_time_ms, created_at, error_stack
           FROM robot_execution_logs
           WHERE id = :log_id \
           """


def build_get_last_execution_logs_query(limit: int = 10) -> str:
    """
    Получение последних записей выполнения для робота
    """
    return """
           SELECT id, robot_id, action_type, status, message,
                  execution_time_ms, created_at
           FROM robot_execution_logs
           WHERE robot_id = :robot_id
           ORDER BY created_at DESC
               LIMIT :limit \
           """


# ============================================================
# robot_logs (логи HTTP запросов к внешним API)
# ============================================================

def build_create_api_log_query() -> str:
    """
    Создание записи о HTTP запросе робота
    """
    return """
           INSERT INTO robot_logs
           (robot_name, robot_version, token_id, user_id, endpoint,
            request_data, started_at, execution_log_id)
           VALUES
               (:robot_name, :robot_version, :token_id, :user_id, :endpoint,
               :request_data, :started_at, :execution_log_id)
               RETURNING id \
           """


def build_update_api_log_success_query() -> str:
    """
    Обновление записи об успешном HTTP запросе
    """
    return """
           UPDATE robot_logs
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
    Обновление записи о неудачном HTTP запросе
    """
    return """
           UPDATE robot_logs
           SET finished_at = :finished_at,
               duration_ms = :duration_ms,
               error_message = :error_message,
               success = 0
           WHERE id = :log_id
               RETURNING id \
           """


def build_get_api_logs_query(
        robot_name: Optional[str] = None,
        limit: int = 100
) -> tuple[str, dict]:
    """
    Получение логов API запросов с фильтрацией
    """
    params = {"limit": limit}
    where_clauses = []

    if robot_name:
        where_clauses.append("robot_name = :robot_name")
        params["robot_name"] = robot_name

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
        SELECT id, robot_name, endpoint, started_at, finished_at,
               duration_ms, success, response_status, error_message
        FROM robot_logs
        WHERE {where_sql}
        ORDER BY started_at DESC
        LIMIT :limit
    """

    return query, params


# ============================================================
# Статистика по логам
# ============================================================

def build_get_logs_stats_query() -> str:
    """
    Получение статистики по логам для робота
    """
    return """
           SELECT
               COUNT(*) as total_executions,
               SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as success_count,
               SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as error_count,
               AVG(execution_time_ms) as avg_duration_ms,
               MAX(created_at) as last_run
           FROM robot_execution_logs
           WHERE robot_id = :robot_id
             AND created_at >= :since \
           """


def build_get_api_errors_stats_query() -> str:
    """
    Получение статистики по ошибкам API для робота
    """
    return """
           SELECT
               endpoint,
               COUNT(*) as error_count,
               MAX(error_message) as last_error
           FROM robot_logs
           WHERE robot_name = :robot_name
             AND success = 0
             AND created_at >= :since
           GROUP BY endpoint
           ORDER BY error_count DESC \
           """