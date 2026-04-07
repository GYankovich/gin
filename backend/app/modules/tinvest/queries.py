# app/modules/tinvest/queries.py
from typing import Optional, Dict, Any, List


def build_get_user_token_query() -> str:
    """Получение активного токена пользователя"""
    return """
           SELECT token, id FROM ganaly.api_tokens
           WHERE user_id = :user_id
             AND token_type = (
                 SELECT num_value FROM ganaly.dictionary
                 WHERE table_name = 'TOKEN' AND column_name = 'TYPE' AND string_value = 'tinvest'
                 LIMIT 1
             )
             AND is_active = 1
           ORDER BY created_at DESC
               LIMIT 1 \
           """


def build_get_user_tokens_query(active_only: bool = True) -> str:
    """
    Запрос списка токенов пользователя (тип tinvest из справочника).
    """
    active_clause = " AND is_active = 1" if active_only else ""
    return f"""
                 SELECT
                     id,
                     user_id,
                     token_type,
                     token,
                     name,
                     is_active,
                     created_at,
                     updated_at,
                     last_used_at,
                     expires_at
                 FROM ganaly.api_tokens
                 WHERE user_id = :user_id
                  AND token_type = (
                      SELECT num_value FROM ganaly.dictionary
                      WHERE table_name = 'TOKEN' AND column_name = 'TYPE' AND string_value = 'tinvest'
                      LIMIT 1
                  )
                  {active_clause}
                 ORDER BY created_at DESC
                 """


def build_get_token_by_id_query() -> str:
    """Получение токена по ID с проверкой принадлежности"""
    return """
           SELECT
               id,
               user_id,
               token_type,
               token,
               name,
               is_active,
               created_at,
               updated_at,
               last_used_at,
               expires_at
           FROM ganaly.api_tokens
           WHERE id = :token_id AND user_id = :user_id \
           """


def build_check_token_exists_query() -> str:
    """Проверка существования токена"""
    return """
           SELECT id FROM ganaly.api_tokens
           WHERE user_id = :user_id AND token = :token AND is_active = 1 \
           """


def build_create_token_query() -> str:
    """Создание нового токена"""
    return """
           INSERT INTO ganaly.api_tokens
               (user_id, token_type, token, name, is_active, created_at)
           VALUES
               (:user_id, :token_type, :token, :token_name, 1, :created_at)
               RETURNING
            id, user_id, token_type, token, token_name, is_active, created_at \
           """


def build_update_token_query(fields: List[str]) -> tuple[str, Dict[str, Any]]:
    """
    Динамически строит запрос обновления токена
    """
    base_query = """
                 UPDATE ganaly.api_tokens
                 SET {updates}, updated_at = :now
                 WHERE id = :token_id AND user_id = :user_id
                     RETURNING
                     id, user_id, token_type, token, token_name, is_active, created_at, updated_at, last_used_at, expires_at \
                 """

    field_mapping = {
        "token_name": "token_name = :token_name",
        "is_active": "is_active = :is_active"
    }

    updates = [field_mapping[f] for f in fields if f in field_mapping]

    if not updates:
        return "", {}

    query = base_query.format(updates=", ".join(updates))

    params = {
        "token_id": ":token_id",
        "user_id": ":user_id",
        "now": ":now"
    }

    return query, params


def build_delete_token_query() -> str:
    """Удаление токена"""
    return """
           DELETE FROM ganaly.api_tokens
           WHERE id = :token_id AND user_id = :user_id
               RETURNING id \
           """


def build_update_last_used_query() -> str:
    """Обновление времени последнего использования токена"""
    return """
           UPDATE ganaly.api_tokens
           SET last_used_at = :now
           WHERE id = :token_id \
           """


def build_get_account_by_id_query() -> str:
    """Получение счета по ID"""
    return """
           SELECT id FROM ganaly.portfolio_accounts
           WHERE user_id = :user_id AND account_id = :account_id \
           """


def build_create_account_query() -> str:
    """Создание нового счета"""
    return """
           INSERT INTO ganaly.portfolio_accounts
           (user_id, account_id, account_type, account_name, account_status, opened_date, is_active)
           VALUES
               (:user_id, :account_id, :account_type, :account_name, :account_status, :opened_date, 1)
               RETURNING id \
           """


def build_update_account_query() -> str:
    """Обновление счета"""
    return """
           UPDATE ganaly.portfolio_accounts
           SET account_name = :account_name,
               account_status = :account_status,
               updated_at = :now
           WHERE id = :db_account_id \
           """


def build_create_snapshot_query() -> str:
    """Создание снимка портфеля"""
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
    """Создание позиции в снимке"""
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


def build_get_last_snapshots_query(
        account_id: int,
        limit: int = 10
) -> tuple[str, Dict[str, Any]]:
    """Получение последних снимков портфеля"""
    query = """
            SELECT
                id,
                snapshot_date,
                total_amount_portfolio,
                daily_yield,
                expected_yield
            FROM ganaly.portfolio_snapshots
            WHERE account_id = :account_id
            ORDER BY snapshot_date DESC
                LIMIT :limit \
            """

    params = {"account_id": account_id, "limit": limit}
    return query, params


def build_get_accounts_list_query() -> str:
    """Получение списка счетов пользователя из БД"""
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


def build_update_account_sync_time_query() -> str:
    """Обновление времени синхронизации счета"""
    return """
           UPDATE ganaly.portfolio_accounts
           SET last_sync_at = :now
           WHERE id = :account_id \
           """


def build_get_token_stats_query() -> str:
    """Получение статистики по токену"""
    return """
           SELECT
               COUNT(*) as total_requests,
               MAX(last_used_at) as last_used,
               COUNT(DISTINCT account_id) as accounts_accessed
           FROM ganaly.api_tokens t
                    LEFT JOIN ganaly.portfolio_snapshots s ON s.account_id IN (
               SELECT id FROM ganaly.portfolio_accounts WHERE user_id = t.user_id
           )
           WHERE t.id = :token_id
           GROUP BY t.id \
           """