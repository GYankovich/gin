#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesAuthQueries [1]
#/// Исходный модуль `backend/app/modules/auth/queries.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/auth/queries.py
from typing import Optional, Dict, Any
from datetime import datetime


def build_get_user_by_login_query() -> str:
    """Возвращает запрос для получения пользователя по логину"""
    return """
           SELECT
               id,
               login,
               password_hash,
               created_at
           FROM "user"
           WHERE login = :login \
           """


def build_get_user_by_email_query() -> str:
    """Пользователь по действующей почте. Регистр не важен."""
    return """
           SELECT
               u.id,
               u.login,
               u.password_hash,
               u.created_at
           FROM "user" u
           JOIN user_email e ON e.user_id = u.id
           WHERE lower(e.email) = :email
             AND (e.valid_to IS NULL OR e.valid_to > CURRENT_TIMESTAMP)
           ORDER BY e.is_primary DESC, e.valid_from DESC
           LIMIT 1 \
           """


def build_check_email_exists_query() -> str:
    """Есть ли действующая запись с этой почтой."""
    return """
           SELECT e.user_id
           FROM user_email e
           WHERE lower(e.email) = :email
             AND (e.valid_to IS NULL OR e.valid_to > CURRENT_TIMESTAMP)
           LIMIT 1 \
           """


def build_check_login_exists_query() -> str:
    """Возвращает запрос для проверки существования логина"""
    return """
           SELECT id FROM "user" WHERE login = :login \
           """


def build_check_login_taken_by_other_query() -> str:
    """Проверяет, занят ли логин другим пользователем"""
    return """
           SELECT id FROM "user"
           WHERE login = :login AND id <> :user_id \
           """


def build_update_login_query() -> str:
    """Обновляет логин пользователя"""
    return """
           UPDATE "user"
           SET login = :login
           WHERE id = :user_id \
           """


def build_create_user_query() -> str:
    """Возвращает запрос для создания пользователя"""
    return """
           INSERT INTO "user" (login, password_hash, created_at)
           VALUES (:login, :password_hash, :created_at)
               RETURNING id, login, created_at \
           """


def build_create_email_query() -> str:
    """Возвращает запрос для добавления email пользователя"""
    return """
           INSERT INTO user_email (user_id, email, is_primary, valid_from)
           VALUES (:user_id, :email, :is_primary, :valid_from) \
           """


def build_create_phone_query() -> str:
    """Возвращает запрос для добавления телефона пользователя"""
    return """
           INSERT INTO user_phone (user_id, phone, is_primary, valid_from)
           VALUES (:user_id, :phone, :is_primary, :valid_from) \
           """


def build_create_token_query() -> str:
    """Возвращает запрос для сохранения токена"""
    return """
           INSERT INTO user_token (
               user_id, token, status, created_at, expires_at,
               ip, user_agent, device_label, geo_label, last_seen_at
           )
           VALUES (
               :user_id, :token, :status, :created_at, :expires_at,
               :ip, :user_agent, :device_label, :geo_label, :last_seen_at
           ) \
           """


def build_list_active_sessions_query() -> str:
    """Активные (не просроченные) сессии пользователя. Текущая — первой."""
    return """
           SELECT
               id,
               ip,
               device_label,
               geo_label,
               created_at,
               expires_at,
               last_seen_at,
               token
           FROM user_token
           WHERE user_id = :user_id
             AND status = 1
             AND expires_at > CURRENT_TIMESTAMP
           ORDER BY (token = :current_token) DESC, created_at DESC \
           """


def build_invalidate_token_by_id_query() -> str:
    """Инвалидация конкретной сессии пользователя по id."""
    return """
           UPDATE user_token
           SET status = 3, invalidated_at = :now
           WHERE id = :token_id
             AND user_id = :user_id
             AND status = 1 \
           """


def build_invalidate_all_user_tokens_query() -> str:
    """Инвалидация всех активных сессий пользователя."""
    return """
           UPDATE user_token
           SET status = 3, invalidated_at = :now
           WHERE user_id = :user_id AND status = 1 \
           """


def build_get_user_by_id_query(include_email: bool = True, include_phone: bool = True) -> str:
    """
    Возвращает запрос для получения пользователя по ID с опциональным получением контактов
    """
    base_query = """
        SELECT
            u.id,
            u.login,
            u.created_at
    """

    if include_email:
        base_query += """,
            (SELECT email FROM user_email 
             WHERE user_id = u.id AND (valid_to IS NULL OR valid_to > CURRENT_TIMESTAMP)
             ORDER BY is_primary DESC, valid_from DESC LIMIT 1) as email
        """
    else:
        base_query += ", NULL as email"

    if include_phone:
        base_query += """,
            (SELECT phone FROM user_phone 
             WHERE user_id = u.id AND (valid_to IS NULL OR valid_to > CURRENT_TIMESTAMP)
             ORDER BY is_primary DESC, valid_from DESC LIMIT 1) as phone
        """
    else:
        base_query += ", NULL as phone"

    base_query += """
        FROM "user" u
        WHERE u.id = :user_id
    """

    return base_query


def build_get_user_by_id_simple_query() -> str:
    """Упрощенный запрос только для проверки существования пользователя"""
    return """
           SELECT id, login FROM "user" WHERE id = :user_id \
           """


def build_get_user_contacts_query() -> tuple[str, Dict[str, Any]]:
    """
    Возвращает запрос для получения всех контактов пользователя
    """
    query = """
            SELECT
                'email' as contact_type,
                email as contact_value,
                is_primary,
                valid_from,
                valid_to
            FROM user_email
            WHERE user_id = :user_id
            UNION ALL
            SELECT
                'phone' as contact_type,
                phone as contact_value,
                is_primary,
                valid_from,
                valid_to
            FROM user_phone
            WHERE user_id = :user_id
            ORDER BY is_primary DESC, valid_from DESC \
            """
    return query, {"user_id": ":user_id"}


def build_invalidate_token_query() -> str:
    """Возвращает запрос для инвалидации токена"""
    return """
           UPDATE user_token
           SET status = 3, invalidated_at = :now
           WHERE token = :token AND status = 1 \
           """


def build_check_token_valid_query() -> str:
    """Возвращает запрос для проверки валидности токена"""
    return """
           SELECT
               id,
               user_id,
               expires_at > CURRENT_TIMESTAMP as is_active
           FROM user_token
           WHERE token = :token AND status = 1 \
           """


def build_clean_expired_tokens_query() -> str:
    """Возвращает запрос для очистки просроченных токенов"""
    return """
           UPDATE user_token
           SET status = 3, invalidated_at = CURRENT_TIMESTAMP
           WHERE expires_at < CURRENT_TIMESTAMP AND status = 1 \
           """


def build_get_user_password_hash_query() -> str:
    """Возвращает password_hash пользователя по id"""
    return """
           SELECT id, login, password_hash
           FROM "user"
           WHERE id = :user_id \
           """


def build_update_password_query() -> str:
    """Обновляет password_hash пользователя"""
    return """
           UPDATE "user"
           SET password_hash = :password_hash
           WHERE id = :user_id \
           """


def build_update_user_email_query() -> str:
    """Обновляет актуальную email-запись пользователя (без INSERT)."""
    return """
           UPDATE user_email
           SET email = :email,
               is_primary = TRUE,
               valid_to = NULL
           WHERE id = (
               SELECT id FROM (
                   SELECT id FROM user_email
                   WHERE user_id = :user_id
                   ORDER BY CASE WHEN valid_to IS NULL THEN 0 ELSE 1 END,
                            is_primary DESC,
                            valid_from DESC
                   LIMIT 1
               ) AS pick
           )
           """


def build_update_user_phone_query() -> str:
    """Обновляет актуальную phone-запись пользователя (без INSERT)."""
    return """
           UPDATE user_phone
           SET phone = :phone,
               is_primary = TRUE,
               valid_to = NULL
           WHERE id = (
               SELECT id FROM (
                   SELECT id FROM user_phone
                   WHERE user_id = :user_id
                   ORDER BY CASE WHEN valid_to IS NULL THEN 0 ELSE 1 END,
                            is_primary DESC,
                            valid_from DESC
                   LIMIT 1
               ) AS pick
           )
           """


def build_expire_user_emails_query() -> str:
    """Закрывает активные email-записи пользователя"""
    return """
           UPDATE user_email
           SET valid_to = :now
           WHERE user_id = :user_id
             AND (valid_to IS NULL OR valid_to > :now) \
           """


def build_expire_user_phones_query() -> str:
    """Закрывает активные phone-записи пользователя"""
    return """
           UPDATE user_phone
           SET valid_to = :now
           WHERE user_id = :user_id
             AND (valid_to IS NULL OR valid_to > :now) \
           """


def build_get_email_confirmation_query() -> str:
    return """
           SELECT code_hash, password_hash, attempts, expires_at, last_sent_at, login
           FROM email_confirmation
           WHERE email = :email AND purpose = :purpose \
           """


def build_upsert_email_confirmation_query() -> str:
    return """
           INSERT INTO email_confirmation (
               email, purpose, code_hash, password_hash, attempts,
               expires_at, created_at, last_sent_at, login
           )
           VALUES (
               :email, :purpose, :code_hash, :password_hash, 0,
               :expires_at, :now, :now, :login
           )
           ON CONFLICT (email, purpose) DO UPDATE SET
               code_hash = EXCLUDED.code_hash,
               password_hash = EXCLUDED.password_hash,
               attempts = 0,
               expires_at = EXCLUDED.expires_at,
               last_sent_at = EXCLUDED.last_sent_at,
               login = EXCLUDED.login \
           """


def build_refresh_email_confirmation_query() -> str:
    """Новый код, пароль регистрации не меняется."""
    return """
           UPDATE email_confirmation
           SET code_hash = :code_hash,
               attempts = 0,
               expires_at = :expires_at,
               last_sent_at = :now
           WHERE email = :email AND purpose = :purpose \
           """


def build_increment_email_confirmation_attempts_query() -> str:
    return """
           UPDATE email_confirmation
           SET attempts = attempts + 1
           WHERE email = :email AND purpose = :purpose \
           """


def build_delete_email_confirmation_query() -> str:
    return """
           DELETE FROM email_confirmation
           WHERE email = :email AND purpose = :purpose \
           """


def build_get_active_email_query() -> str:
    """Действующая карточка почты: id записи и пользователь."""
    return """
           SELECT e.id, e.user_id
           FROM user_email e
           WHERE lower(e.email) = :email
             AND (e.valid_to IS NULL OR e.valid_to > CURRENT_TIMESTAMP)
           ORDER BY e.is_primary DESC, e.valid_from DESC
           LIMIT 1 \
           """


def build_insert_outbound_message_query() -> str:
    return """
           INSERT INTO outbound_message (
               user_id, email_id, phone_id, to_email, channel, subject, body, purpose,
               status, attempts, created_at, updated_at,
               created_source, created_by, updated_source, updated_by
           )
           VALUES (
               :user_id, :email_id, NULL, :to_email, 'mail', :subject, :body, :purpose,
               'pending', 0, :now, :now,
               'rest', :actor, 'rest', :actor
           )
           RETURNING id \
           """


def build_finish_outbound_message_query() -> str:
    return """
           UPDATE outbound_message
           SET status = :status,
               attempts = attempts + 1,
               error_code = :error_code,
               error_message = :error_message,
               sent_at = :sent_at,
               updated_at = :now,
               updated_source = 'rest',
               updated_by = :actor
           WHERE id = :id \
           """


def build_get_reset_by_hash_query() -> str:
    return """
           SELECT email, expires_at
           FROM email_confirmation
           WHERE purpose = :purpose AND code_hash = :code_hash \
           """


def build_get_user_with_token_query() -> str:
    """Возвращает запрос для получения пользователя вместе с токеном"""
    return """
           SELECT
               u.id,
               u.login,
               t.id as token_id,
               t.expires_at
           FROM "user" u
                    JOIN user_token t ON u.id = t.user_id
           WHERE t.token = :token AND t.status = 1 AND t.expires_at > CURRENT_TIMESTAMP \
           """