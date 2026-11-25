"""SQL query builders for robots v2."""

from __future__ import annotations

from typing import Any

from app.modules.trading_core.brokers.routing import TOKEN_TYPE_BROKER, normalize_broker_type

# broker filter code → dictionary TOKEN.TYPE.num_value
_BROKER_FILTER_TO_TOKEN_TYPE = {
    code: num for num, code in TOKEN_TYPE_BROKER.items()
}


def build_list_robots_query(
    *,
    user_id: int,
    robot_status: list[int] | None = None,
    robot_type: list[int] | None = None,
    broker: list[str] | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"user_id": user_id}
    conditions = [
        "r.user_id = :user_id",
        "COALESCE(r.metadata->>'deletedAt', '') = ''",
    ]
    if robot_status:
        placeholders = ", ".join(f":status_{i}" for i in range(len(robot_status)))
        conditions.append(f"r.status IN ({placeholders})")
        for i, status in enumerate(robot_status):
            params[f"status_{i}"] = status
    if robot_type:
        placeholders = ", ".join(f":type_{i}" for i in range(len(robot_type)))
        conditions.append(f"r.type IN ({placeholders})")
        for i, t in enumerate(robot_type):
            params[f"type_{i}"] = t
    broker_nums: list[int] = []
    for raw in broker or []:
        code = normalize_broker_type(str(raw).strip())
        num = _BROKER_FILTER_TO_TOKEN_TYPE.get(code)
        if num is not None and num not in broker_nums:
            broker_nums.append(num)
    if broker_nums:
        placeholders = ", ".join(f":broker_type_{i}" for i in range(len(broker_nums)))
        conditions.append(f"at.token_type IN ({placeholders})")
        for i, num in enumerate(broker_nums):
            params[f"broker_type_{i}"] = num
    where = " AND ".join(conditions)
    query = f"""
        SELECT
            r.id,
            r.name,
            r.type,
            r.token_id,
            r.status,
            r.config_version,
            r.config,
            r.metadata,
            r.creation_date,
            r.modification_date,
            r.last_started,
            dt.name AS type_name,
            ds.name AS status_name,
            dtok.string_value AS broker_code,
            dtok.name AS broker_name,
            (
                SELECT COALESCE(
                    json_agg(
                        json_build_object(
                            'accountId', pa.account_id,
                            'accountName', pa.account_name
                        )
                        ORDER BY pa.id
                    ),
                    '[]'::json
                )
                  FROM {schema}.portfolio_accounts pa
                  JOIN {schema}.token_portfolio_accounts tpa
                    ON tpa.portfolio_account_id = pa.id
                   AND tpa.token_id = r.token_id
                   AND tpa.status = 1
                 WHERE pa.user_id = r.user_id
                   AND UPPER(pa.account_status) = 'OPEN'
            ) AS accounts_json
        FROM {schema}.robots r
        LEFT JOIN {schema}.api_tokens at
            ON at.id = r.token_id
        LEFT JOIN {schema}.dictionary dtok
            ON dtok.num_value = at.token_type
           AND dtok.table_name = 'TOKEN'
           AND dtok.column_name = 'TYPE'
        LEFT JOIN {schema}.dictionary dt
            ON r.type = dt.num_value
           AND dt.table_name = 'ROBOT'
           AND dt.column_name = 'TYPE'
        INNER JOIN {schema}.dictionary ds
            ON r.status = ds.num_value
           AND ds.table_name = 'ROBOT'
           AND ds.column_name = 'STATUS'
           AND COALESCE(ds.hide_from_ui, 0) != 1
        WHERE {where}
        ORDER BY r.creation_date DESC
    """
    return query, params


# Same window the /portfolio chart opens on (zoom «Месяц»).
FLEET_SNAPSHOT_DAYS = 30


def build_fleet_snapshot_curve_query(*, user_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    """Daily portfolio value per robot, same source as /portfolio chart.

    portfolio_snapshot_daily is the last snapshot of each Europe/Moscow day.
    Several accounts on one token are summed on that day.
    """
    query = f"""
        SELECT
            days.robot_id,
            COALESCE(
                json_agg(
                    json_build_object(
                        'time', days.snapshot_day,
                        'equity', days.equity
                    )
                    ORDER BY days.snapshot_day
                ),
                '[]'::json
            ) AS equity_curve
        FROM (
            SELECT
                r.id AS robot_id,
                d.snapshot_day,
                SUM(d.total_amount_portfolio) AS equity
            FROM {schema}.robots r
            JOIN {schema}.token_portfolio_accounts tpa
                ON tpa.token_id = r.token_id
               AND tpa.status = 1
            JOIN {schema}.portfolio_accounts pa
                ON pa.id = tpa.portfolio_account_id
               AND pa.user_id = r.user_id
               AND UPPER(pa.account_status) = 'OPEN'
            JOIN {schema}.portfolio_snapshot_daily d
                ON d.account_id = pa.id
               AND d.snapshot_day >= (timezone('Europe/Moscow', CURRENT_TIMESTAMP))::date
                                    - :snapshot_days
            WHERE r.user_id = :user_id
              AND COALESCE(r.metadata->>'deletedAt', '') = ''
            GROUP BY r.id, d.snapshot_day
        ) days
        GROUP BY days.robot_id
    """
    return query, {"user_id": user_id, "snapshot_days": FLEET_SNAPSHOT_DAYS}


def build_fleet_latest_snapshot_query(*, user_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    """Latest portfolio snapshot per robot: equity, time, open positions."""
    query = f"""
        SELECT
            r.id AS robot_id,
            SUM(latest.total_amount_portfolio) AS equity,
            MAX(latest.snapshot_date) AS snapshot_date,
            SUM(latest.positions_count) AS positions_count,
            SUM(funds.own_funds) AS own_funds
        FROM {schema}.robots r
        JOIN {schema}.token_portfolio_accounts tpa
            ON tpa.token_id = r.token_id
           AND tpa.status = 1
        JOIN {schema}.portfolio_accounts pa
            ON pa.id = tpa.portfolio_account_id
           AND pa.user_id = r.user_id
           AND UPPER(pa.account_status) = 'OPEN'
        JOIN LATERAL (
            SELECT
                ps.total_amount_portfolio,
                ps.snapshot_date,
                ps.currency,
                (
                    SELECT COUNT(*)
                    FROM {schema}.portfolio_positions pp
                    WHERE pp.snapshot_id = ps.id
                ) AS positions_count
            FROM {schema}.portfolio_snapshots ps
            WHERE ps.account_id = pa.id
            ORDER BY ps.snapshot_date DESC
            LIMIT 1
        ) latest ON TRUE
        LEFT JOIN LATERAL (
            SELECT SUM(signed_payment) AS own_funds
            FROM (
                SELECT
                    CASE
                        WHEN operation_type IN (
                            'OPERATION_TYPE_INPUT',
                            'OPERATION_TYPE_INPUT_ACQUIRING',
                            'OPERATION_TYPE_INP_MULTI'
                        )
                        AND status = 'OPERATION_STATE_EXECUTED'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                        AND ABS(payment) > 1e-9
                            THEN payment
                        WHEN operation_type IN (
                            'OPERATION_TYPE_OUTPUT',
                            'OPERATION_TYPE_OUTPUT_ACQUIRING',
                            'OPERATION_TYPE_OUT_MULTI'
                        )
                        AND status = 'OPERATION_STATE_EXECUTED'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                        AND ABS(payment) > 1e-9
                            THEN -ABS(payment)
                        WHEN operation_type LIKE 'BYBIT_FUND_IN%'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                            THEN CASE
                                WHEN ABS(payment) > 1e-9 THEN payment
                                WHEN ABS(quantity) > 1e-9 THEN ABS(quantity)
                                ELSE NULL
                            END
                        WHEN operation_type LIKE 'BYBIT_FUND_OUT%'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                            THEN CASE
                                WHEN ABS(payment) > 1e-9 THEN -ABS(payment)
                                WHEN ABS(quantity) > 1e-9 THEN -ABS(quantity)
                                ELSE NULL
                            END
                        WHEN operation_type LIKE 'BYBIT_TRANSFER_IN%'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                            THEN CASE
                                WHEN ABS(payment) > 1e-9 THEN payment
                                WHEN ABS(quantity) > 1e-9 THEN ABS(quantity)
                                ELSE NULL
                            END
                        WHEN operation_type LIKE 'BYBIT_TRANSFER_OUT%'
                        AND UPPER(payment_currency) = UPPER(latest.currency)
                            THEN CASE
                                WHEN ABS(payment) > 1e-9 THEN -ABS(payment)
                                WHEN ABS(quantity) > 1e-9 THEN -ABS(quantity)
                                ELSE NULL
                            END
                        ELSE NULL
                    END AS signed_payment
                FROM {schema}.portfolio_operations
                WHERE account_id = pa.id
            ) cashflows
            WHERE signed_payment IS NOT NULL
        ) funds ON TRUE
        WHERE r.user_id = :user_id
          AND COALESCE(r.metadata->>'deletedAt', '') = ''
        GROUP BY r.id
    """
    return query, {"user_id": user_id}


def build_fleet_trade_stats_query(*, user_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    """Closed robot fills over the same Moscow window as the fleet equity curve.

    A close is a SELL or an exit-* kind. Wins and losses use the stored fill pnl.
    """
    query = f"""
        SELECT
            f.robot_id,
            COUNT(*) FILTER (
                WHERE UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%'
            ) AS trades_count,
            COUNT(*) FILTER (
                WHERE (UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%')
                  AND f.pnl > 0
            ) AS wins,
            COUNT(*) FILTER (
                WHERE (UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%')
                  AND f.pnl < 0
            ) AS losses
        FROM {schema}.robot_fills f
        JOIN {schema}.robots r
            ON r.id = f.robot_id
           AND r.user_id = :user_id
           AND COALESCE(r.metadata->>'deletedAt', '') = ''
        WHERE f.filled_at >= (
            ((timezone('Europe/Moscow', CURRENT_TIMESTAMP))::date - :snapshot_days)
            ::timestamp AT TIME ZONE 'Europe/Moscow'
        )
        GROUP BY f.robot_id
    """
    return query, {"user_id": user_id, "snapshot_days": FLEET_SNAPSHOT_DAYS}


def build_has_broker_accounts_query(*, user_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    query = f"""
        SELECT EXISTS (
            SELECT 1
              FROM {schema}.portfolio_accounts pa
             WHERE pa.user_id = :user_id
               AND UPPER(pa.account_status) = 'OPEN'
        ) AS has_accounts
    """
    return query, {"user_id": user_id}


def build_get_robot_query(*, robot_id: int, user_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    query = f"""
        SELECT
            r.id,
            r.name,
            r.type,
            r.token_id,
            r.status,
            r.config_version,
            r.config,
            r.metadata,
            r.creation_date,
            r.modification_date,
            r.last_started,
            dt.name AS type_name,
            ds.name AS status_name
        FROM {schema}.robots r
        LEFT JOIN {schema}.dictionary dt
            ON r.type = dt.num_value
           AND dt.table_name = 'ROBOT'
           AND dt.column_name = 'TYPE'
        LEFT JOIN {schema}.dictionary ds
            ON r.status = ds.num_value
           AND ds.table_name = 'ROBOT'
           AND ds.column_name = 'STATUS'
        WHERE r.id = :robot_id
          AND r.user_id = :user_id
          AND COALESCE(r.metadata->>'deletedAt', '') = ''
    """
    return query, {"robot_id": robot_id, "user_id": user_id}


def build_insert_robot_query(schema: str = "public") -> str:
    return f"""
        INSERT INTO {schema}.robots (
            name, user_id, token_id, type, status, config_version, config, metadata, usercre
        ) VALUES (
            :name, :user_id, :token_id, :type, :status, :config_version, :config, :metadata,
            (SELECT login FROM {schema}."user" WHERE id = :user_id)
        )
        RETURNING id
    """


def build_update_robot_query(schema: str = "public") -> str:
    return f"""
        UPDATE {schema}.robots
        SET
            name = :name,
            token_id = :token_id,
            type = :type,
            status = :status,
            config_version = :config_version,
            config = :config,
            metadata = :metadata,
            usermod = (SELECT login FROM {schema}."user" WHERE id = :user_id),
            modification_date = NOW()
        WHERE id = :robot_id AND user_id = :user_id
        RETURNING id
    """


def build_soft_delete_robot_query(schema: str = "public") -> str:
    """Soft delete: metadata.deletedAt + status=0 for portfolio (legacy parity)."""
    return f"""
        UPDATE {schema}.robots
        SET
            status = :status,
            metadata = CAST(:metadata AS jsonb),
            usermod = (SELECT login FROM {schema}."user" WHERE id = :user_id),
            modification_date = NOW()
        WHERE id = :robot_id
          AND user_id = :user_id
          AND COALESCE(metadata->>'deletedAt', '') = ''
        RETURNING id
    """


def build_insert_config_history_query(schema: str = "public") -> str:
    return f"""
        INSERT INTO {schema}.robot_config_history (
            id, robot_id, version, config, created_by
        ) VALUES (
            :id, :robot_id, :version, :config, :created_by
        )
    """


def build_next_config_version_query(*, robot_id: int, schema: str = "public") -> tuple[str, dict[str, Any]]:
    query = f"""
        SELECT COALESCE(MAX(version), 0) + 1 AS next_version
        FROM {schema}.robot_config_history
        WHERE robot_id = :robot_id
    """
    return query, {"robot_id": robot_id}


def build_update_status_query(schema: str = "public") -> str:
    return f"""
        UPDATE {schema}.robots
        SET status = :status,
            usermod = (SELECT login FROM {schema}."user" WHERE id = :user_id),
            modification_date = NOW()
        WHERE id = :robot_id AND user_id = :user_id
        RETURNING id
    """