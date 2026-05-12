"""
Общие SQL запросы для базовых операций с роботами
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsBaseQueries [1]
#/// Исходный модуль `backend/app/modules/robots/base/queries.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Optional, List, Dict, Any

# ============================================================
# robot_execution_logs (логи выполнения/запусков роботов)
# ============================================================

def build_create_execution_log_query() -> str:
    """
    Создание записи о запуске робота
    """
    return """
           INSERT INTO {schema}.robot_execution_logs
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
           UPDATE {schema}.robot_execution_logs
           SET status = :status,
               message = :message,
               execution_time_ms = :execution_time_ms,
               error_stack = :error_stack
           WHERE id = :log_id
               RETURNING id \
           """


# ============================================================
# robot_logs (логи HTTP запросов к внешним API)
# ============================================================

def build_create_api_log_query() -> str:
    """
    Создание записи о HTTP запросе робота
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
    Обновление записи об успешном HTTP запросе
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
    Обновление записи о неудачном HTTP запросе
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


# ============================================================
# Расписание и статусы роботов
# ============================================================

def build_get_robot_schedule_query() -> str:
    """
    Получение активного расписания робота
    Возвращает: schedule_type, interval_seconds, start_time, end_time, weekdays, is_active
    """
    return """
           SELECT schedule_type, interval_seconds, start_time, end_time, weekdays, is_active
           FROM {schema}.robot_schedules
           WHERE robot_id = :robot_id AND is_active = 1
           ORDER BY priority DESC, id ASC
               LIMIT 1 \
           """


def build_update_robot_last_run_query() -> str:
    """
    Обновление времени последнего запуска робота
    """
    return """
           UPDATE {schema}.robots
           SET last_started = :now
           WHERE id = :robot_id
               RETURNING id \
           """


def build_get_robot_info_query() -> str:
    """
    Получение базовой информации о роботе (для проверки существования и статуса)
    Возвращает: id, user_id, token_id, name, type, status, last_started
    """
    return """
           SELECT id, user_id, token_id, name, type, status, last_started
           FROM {schema}.robots
           WHERE id = :robot_id \
           """


def build_check_robot_active_query() -> str:
    """
    Проверка, активен ли робот (статус = 1)
    """
    return """
           SELECT id
           FROM {schema}.robots
           WHERE id = :robot_id AND status = 1 \
           """


# ============================================================
# Токены
# ============================================================

def build_get_token_query() -> str:
    """
    Получение токена по ID с проверкой активности
    """
    return """
           SELECT id, token, user_id
           FROM {schema}.api_tokens
           WHERE id = :token_id AND is_active = 1 \
           """