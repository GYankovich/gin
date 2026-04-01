# app/modules/robots/portfolio_updater/queries.py
"""
Специфичные SQL запросы для портфельного робота
"""

def build_get_active_portfolio_robots_query() -> str:
    """
    Получение активных портфельных роботов для шедулера
    Возвращает: robot_id, user_id, token_id, token
    """
    return """
           SELECT
               r.id as robot_id,
               r.user_id,
               r.token_id,
               at.token as token_value
           FROM {schema}.robots r
        INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
           WHERE r.type = :robot_type
             AND r.status = :status_active
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