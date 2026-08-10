#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestQueries [1]
#/// Исходный модуль `backend/app/modules/tinvest/queries.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/tinvest/queries.py
from typing import Optional, Dict, Any, List


def build_get_user_token_query() -> str:
    """Получение активного токена пользователя"""
    return """
           SELECT token, id FROM api_tokens
           WHERE user_id = :user_id
             AND token_type = (
                 SELECT num_value FROM dictionary
                 WHERE table_name = 'TOKEN' AND column_name = 'TYPE' AND string_value = 'tinvest'
                 LIMIT 1
             )
             AND status = 1
           ORDER BY created_at DESC
               LIMIT 1 \
           """


def build_get_user_tokens_query(active_only: bool = True) -> str:
    """
    Запрос списка токенов пользователя (тип tinvest из справочника).
    """
    active_clause = " AND status = 1" if active_only else ""
    return f"""
                 SELECT
                     id,
                     user_id,
                     token_type,
                     token,
                     name,
                     status,
                     created_at,
                     updated_at,
                     last_used_at,
                     expires_at
                 FROM api_tokens
                 WHERE user_id = :user_id
                  AND token_type = (
                      SELECT num_value FROM dictionary
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
               status,
               created_at,
               updated_at,
               last_used_at,
               expires_at,
               extra_data
           FROM api_tokens
           WHERE id = :token_id AND user_id = :user_id \
           """


def build_check_token_exists_query() -> str:
    """Проверка существования токена"""
    return """
           SELECT id FROM api_tokens
           WHERE user_id = :user_id AND token = :token AND status = 1 \
           """


def build_create_token_query() -> str:
    """Создание нового токена"""
    return """
           INSERT INTO api_tokens
               (user_id, token_type, token, name, status, created_at)
           VALUES
               (:user_id, :token_type, :token, :token_name, 1, :created_at)
               RETURNING
            id, user_id, token_type, token, token_name, status, created_at \
           """


def build_update_token_query(fields: List[str]) -> tuple[str, Dict[str, Any]]:
    """
    Динамически строит запрос обновления токена
    """
    base_query = """
                 UPDATE api_tokens
                 SET {updates}, updated_at = :now
                 WHERE id = :token_id AND user_id = :user_id
                     RETURNING
                    id, user_id, token_type, token, token_name, status, created_at, updated_at, last_used_at, expires_at \
                 """

    field_mapping = {
        "token_name": "token_name = :token_name",
        "status": "status = :status"
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
           DELETE FROM api_tokens
           WHERE id = :token_id AND user_id = :user_id
               RETURNING id \
           """


def build_update_last_used_query() -> str:
    """Обновление времени последнего внешнего использования (успех — без ошибки)."""
    return """
           UPDATE api_tokens
           SET last_used_at = :now,
               last_error = NULL,
               last_error_at = NULL,
               updated_at = :now
           WHERE id = :token_id
           """


def build_get_account_by_id_query() -> str:
    """Получение счета по ID"""
    return """
           SELECT id FROM portfolio_accounts
           WHERE user_id = :user_id AND account_id = :account_id \
           """


def build_create_account_query() -> str:
    """Создание нового счета"""
    return """
           INSERT INTO portfolio_accounts
           (user_id, account_id, account_type, account_name, account_status, opened_date, is_active)
           VALUES
               (:user_id, :account_id, :account_type, :account_name, :account_status, :opened_date, 1)
               RETURNING id \
           """


def build_update_account_query() -> str:
    """Обновление счета (opened_date заполняется, если в БД ещё NULL)."""
    return """
           UPDATE portfolio_accounts
           SET account_name = :account_name,
               account_status = :account_status,
               opened_date = COALESCE(opened_date, :opened_date),
               closed_date = COALESCE(closed_date, :closed_date),
               updated_at = :now
           WHERE id = :db_account_id \
           """


def build_create_snapshot_query() -> str:
    """Создание снимка портфеля"""
    return """
           INSERT INTO portfolio_snapshots
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
           INSERT INTO portfolio_positions
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
            FROM portfolio_snapshots
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
               last_token_id,
               created_at
           FROM portfolio_accounts
           WHERE user_id = :user_id AND is_active = 1
           ORDER BY created_at DESC \
           """


def build_update_account_sync_time_query() -> str:
    """Обновление времени синхронизации счета"""
    return """
           UPDATE portfolio_accounts
           SET last_sync_at = :now,
               last_token_id = COALESCE(:token_id, last_token_id)
           WHERE id = :account_id \
           """


def build_get_token_stats_query() -> str:
    """Получение статистики по токену"""
    return """
           SELECT
               COUNT(*) as total_requests,
               MAX(last_used_at) as last_used,
               COUNT(DISTINCT account_id) as accounts_accessed
           FROM api_tokens t
                    LEFT JOIN portfolio_snapshots s ON s.account_id IN (
               SELECT id FROM portfolio_accounts WHERE user_id = t.user_id
           )
           WHERE t.id = :token_id
           GROUP BY t.id \
           """


def build_get_account_row_query() -> str:
    """Получить запись portfolio_accounts по внутреннему id и user_id."""
    return """
           SELECT id, account_id
           FROM portfolio_accounts
           WHERE id = :account_db_id AND user_id = :user_id
           LIMIT 1 \
           """


def build_get_account_row_by_external_id_query() -> str:
    """Получить запись portfolio_accounts по внешнему account_id и user_id."""
    return """
           SELECT id, account_id
           FROM portfolio_accounts
           WHERE account_id = :external_account_id AND user_id = :user_id
           LIMIT 1 \
           """


def build_get_latest_operation_date_query() -> str:
    """Последняя дата операции по счету."""
    return """
           SELECT MAX(operation_date)
           FROM portfolio_operations
           WHERE account_id = :account_db_id \
           """


def build_delete_operations_by_period_query() -> str:
    """Удалить операции по счету в диапазоне дат (кроме зеркал ORDER_*)."""
    return """
           DELETE FROM portfolio_operations
           WHERE account_id = :account_db_id
             AND operation_date >= :from_dt
             AND operation_date <= :to_dt
             AND operation_type NOT LIKE 'ORDER%' \
           """


def build_upsert_operation_query() -> str:
    """Upsert операции в portfolio_operations по operation_id."""
    return """
           INSERT INTO portfolio_operations
           (
               account_id,
               operation_id,
               parent_operation_id,
               figi,
               instrument_type,
               instrument_uid,
               position_uid,
               operation_type,
               operation_date,
               quantity,
               quantity_rest,
               price,
               price_currency,
               payment,
               payment_currency,
               commission,
               commission_currency,
               status,
               trades,
               extra_data
           )
           VALUES
           (
               :account_id,
               :operation_id,
               :parent_operation_id,
               :figi,
               :instrument_type,
               :instrument_uid,
               :position_uid,
               :operation_type,
               :operation_date,
               :quantity,
               :quantity_rest,
               :price,
               :price_currency,
               :payment,
               :payment_currency,
               :commission,
               :commission_currency,
               :status,
               CAST(:trades AS jsonb),
               CAST(:extra_data AS jsonb)
           )
           ON CONFLICT (operation_id) DO UPDATE SET
               parent_operation_id = EXCLUDED.parent_operation_id,
               figi = EXCLUDED.figi,
               instrument_type = EXCLUDED.instrument_type,
               instrument_uid = EXCLUDED.instrument_uid,
               position_uid = EXCLUDED.position_uid,
               operation_type = EXCLUDED.operation_type,
               operation_date = EXCLUDED.operation_date,
               quantity = EXCLUDED.quantity,
               quantity_rest = EXCLUDED.quantity_rest,
               price = EXCLUDED.price,
               price_currency = EXCLUDED.price_currency,
               payment = EXCLUDED.payment,
               payment_currency = EXCLUDED.payment_currency,
               commission = EXCLUDED.commission,
               commission_currency = EXCLUDED.commission_currency,
               status = EXCLUDED.status,
               trades = EXCLUDED.trades,
               extra_data = EXCLUDED.extra_data \
           """


def build_get_operations_for_account_query() -> str:
    """Список операций счета за период."""
    return """
           SELECT
               operation_id,
               operation_date,
               operation_type,
               figi,
               instrument_type,
               quantity,
               price,
               payment,
               payment_currency,
               status,
               extra_data
           FROM portfolio_operations
           WHERE account_id = :account_db_id
             AND operation_date >= :from_dt
             AND operation_date <= :to_dt
           ORDER BY operation_date DESC
           LIMIT :limit \
           """


def build_insert_external_api_log_query() -> str:
    """Лог ручных/внешних вызовов брокерского API (аналог robot_logs)."""
    return """
           INSERT INTO external_api_logs (
               user_id,
               token_id,
               broker,
               context_type,
               context_ref,
               endpoint,
               request_data,
               response_status,
               response_data,
               started_at,
               finished_at,
               duration_ms,
               success,
               error_message
           )
           VALUES (
               :user_id,
               :token_id,
               :broker,
               :context_type,
               :context_ref,
               :endpoint,
               CAST(:request_data AS jsonb),
               :response_status,
               CAST(:response_data AS jsonb),
               :started_at,
               :finished_at,
               :duration_ms,
               :success,
               :error_message
           )
           """