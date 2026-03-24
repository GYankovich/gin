# app/modules/apikey/queries.py
from typing import Optional, Dict, Any, List


def build_check_existing_token_query() -> str:
    """Проверка существования активного токена"""
    return """
           SELECT id FROM ganaly.api_tokens
           WHERE token = :token AND is_active = 1
               LIMIT 1 \
           """


def build_check_existing_token_by_user_query() -> str:
    """Проверка существования токена у конкретного пользователя"""
    return """
           SELECT id, name, token_type, is_active, created_at
           FROM ganaly.api_tokens
           WHERE user_id = :user_id
             AND token = :token
             AND is_active = 1 \
           """


def build_check_active_key_by_type_query() -> str:
    """Проверка наличия активного ключа определенного типа"""
    return """
           SELECT id FROM ganaly.api_tokens
           WHERE user_id = :user_id
             AND token_type = :key_type
             AND is_active = 1 \
           """


def build_deactivate_old_key_query() -> str:
    """Деактивация старого ключа"""
    return """
           UPDATE ganaly.api_tokens
           SET is_active = 0, updated_at = :now
           WHERE id = :old_id \
           """


def build_create_api_key_query() -> str:
    """Создание нового API ключа"""
    return """
           INSERT INTO ganaly.api_tokens
           (user_id, token, token_type, name, is_active, created_at, refresh_interval_minutes)
           VALUES
               (:user_id, :token, :key_type, :name, 1, :created_at, :refresh_interval_minutes)
               RETURNING id, name, token_type, is_active, created_at, refresh_interval_minutes, token \
           """

def build_count_user_keys_query(
        key_type: Optional[str] = None,
        include_inactive: bool = False
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для подсчета количества ключей пользователя
    """
    base_query = """
                 SELECT COUNT(*)
                 FROM ganaly.api_tokens
                 WHERE user_id = :user_id\
                 """

    params = {"user_id": ":user_id"}
    conditions = []

    if key_type:
        conditions.append("token_type = :key_type")
        params["key_type"] = key_type

    if not include_inactive:
        conditions.append("is_active = 1")

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    return base_query, params


def build_get_user_keys_query(
        key_type: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0
) -> tuple[str, Dict[str, Any]]:
    """
    Строит запрос для получения списка ключей пользователя
    """
    base_query = """
                 SELECT
                     id,
                     name,
                     token_type,
                     is_active,
                     created_at,
                     token,
                     refresh_interval_minutes
                 FROM ganaly.api_tokens
                 WHERE user_id = :user_id \
                 """

    params = {"user_id": ":user_id", "limit": limit, "offset": offset}
    conditions = []

    if key_type:
        conditions.append("token_type = :key_type")
        params["key_type"] = key_type

    if not include_inactive:
        conditions.append("is_active = 1")

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

    return base_query, params


def build_get_key_by_id_query() -> str:
    """Получение ключа по ID с проверкой принадлежности"""
    return """
           SELECT
               id,
               name,
               token_type,
               token,
               is_active,
               created_at,
               updated_at,
               expires_at,
               last_used_at
           FROM ganaly.api_tokens
           WHERE id = :key_id AND user_id = :user_id \
           """


def build_check_key_ownership_query() -> str:
    """Проверка принадлежности ключа пользователю"""
    return """
           SELECT id FROM ganaly.api_tokens
           WHERE id = :key_id AND user_id = :user_id \
           """


def build_update_key_query(
        fields: List[str]
) -> tuple[str, Dict[str, Any]]:
    """
    Динамически строит запрос обновления ключа
    """
    base_query = """
                 UPDATE ganaly.api_tokens
                 SET {updates}, updated_at = :now
                 WHERE id = :key_id AND user_id = :user_id
                     RETURNING id, name, token_type, is_active, created_at, refresh_interval_minutes, token \
                 """

    field_mapping = {
        "name": "name = :name",
        "is_active": "is_active = :is_active",
        "refresh_interval_minutes": "refresh_interval_minutes = :refresh_interval_minutes"
    }

    updates = [field_mapping[f] for f in fields if f in field_mapping]

    if not updates:
        return "", {}

    query = base_query.format(updates=", ".join(updates))

    params = {
        "key_id": ":key_id",
        "user_id": ":user_id",
        "now": ":now"
    }

    return query, params


def build_deactivate_key_query() -> str:
    """Деактивация ключа"""
    return """
           UPDATE ganaly.api_tokens
           SET is_active = 0, updated_at = :now
           WHERE id = :key_id AND user_id = :user_id AND is_active = 1
               RETURNING id \
           """


def build_update_last_used_query() -> str:
    """Обновление времени последнего использования"""
    return """
           UPDATE ganaly.api_tokens
           SET last_used_at = :now
           WHERE id = :key_id \
           """


def build_get_token_by_value_query() -> str:
    """Получение токена по его значению"""
    return """
           SELECT
               id,
               user_id,
               token_type,
               name,
               is_active,
               refresh_interval_minutes
           FROM ganaly.api_tokens
           WHERE token = :token AND is_active = 1 \
           """


def build_get_tokens_by_type_query() -> str:
    """Получение всех активных токенов определенного типа"""
    return """
           SELECT
               id,
               user_id,
               token,
               name,
               refresh_interval_minutes,
               last_used_at
           FROM ganaly.api_tokens
           WHERE token_type = :token_type AND is_active = 1
           ORDER BY created_at DESC \
           """


def build_get_expiring_tokens_query(days: int = 7) -> tuple[str, Dict[str, Any]]:
    """Получение токенов, срок действия которых истекает"""
    query = """
            SELECT
                id,
                user_id,
                token_type,
                name,
                expires_at
            FROM ganaly.api_tokens
            WHERE expires_at IS NOT NULL
              AND expires_at <= :expiry_threshold
              AND is_active = 1
            ORDER BY expires_at ASC \
            """

    params = {"expiry_threshold": ":expiry_threshold"}
    return query, params


def build_bulk_deactivate_tokens_query() -> str:
    """Массовая деактивация токенов"""
    return """
           UPDATE ganaly.api_tokens
           SET is_active = 0, updated_at = :now
           WHERE user_id = :user_id AND token_type = :token_type \
           """