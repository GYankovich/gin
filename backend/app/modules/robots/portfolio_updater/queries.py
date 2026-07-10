#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsPortfolioUpdaterQueries [1]
#/// Исходный модуль `backend/app/modules/robots/portfolio_updater/queries.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/portfolio_updater/queries.py
"""
Специфичные SQL запросы для портфельного робота
"""

def build_get_active_portfolio_robots_query() -> str:
    """
    Получение активных портфельных роботов для шедулера
    Возвращает: robot_id, user_id, token_id, token, broker_type, token_extra_data, token_type
    """
    return """
           SELECT
               r.id as robot_id,
               r.user_id,
               r.token_id,
               at.token as token_value,
               da.string_value as broker_type,
               at.extra_data as token_extra_data,
               at.token_type
           FROM {schema}.robots r
        INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
        INNER JOIN {schema}.dictionary da
                ON at.token_type = da.num_value
               AND da.table_name = 'TOKEN'
               AND da.column_name = 'TYPE'
           WHERE r.type = :robot_type
             AND r.status = :status_active
             AND at.status = 1 \
           """


def build_get_robot_config_query() -> str:
    """
    Получение конфигурации робота из БД
    """
    return """
           SELECT config FROM {schema}.robots
           WHERE id = :robot_id AND status = 1 \
           """