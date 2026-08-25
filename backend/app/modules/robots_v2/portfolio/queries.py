"""SQL for portfolio updater scheduler (robots_v2 type=1)."""

from __future__ import annotations


def build_get_active_portfolio_v2_robots_query(*, schema: str = "public") -> str:
    """Active portfolio updaters: robots_v2 type=1, enabled, not soft-deleted, active token."""
    return f"""
        SELECT
            r.id AS robot_id,
            r.user_id,
            r.token_id,
            at.token AS token_value,
            da.string_value AS broker_type,
            at.extra_data AS token_extra_data,
            at.token_type
        FROM {schema}.robots_v2 r
        INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
        INNER JOIN {schema}.dictionary da
                ON at.token_type = da.num_value
               AND da.table_name = 'TOKEN'
               AND da.column_name = 'TYPE'
        WHERE r.type = :robot_type
          AND r.status = :status_active
          AND COALESCE(r.metadata->>'deletedAt', '') = ''
          AND at.status = 1
    """


def build_update_portfolio_last_started_query(*, schema: str = "public") -> str:
    return f"""
        UPDATE {schema}.robots_v2
        SET last_started = :now,
            date_modification = :now
        WHERE id = :robot_id
    """


def build_find_portfolio_v2_by_token_query(*, schema: str = "public") -> str:
    return f"""
        SELECT id
        FROM {schema}.robots_v2
        WHERE token_id = :token_id
          AND user_id = :user_id
          AND type = 1
          AND status = 1
          AND COALESCE(metadata->>'deletedAt', '') = ''
        ORDER BY id
        LIMIT 1
    """
