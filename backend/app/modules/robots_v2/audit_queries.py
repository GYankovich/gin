"""SQL query builders for robots v2 audit trail reads."""

from __future__ import annotations

from typing import Any
from uuid import UUID

AUDIT_TYPES = ("sessions", "fills", "cycles", "decisions", "signals", "orders", "roundTrips")


def build_list_sessions_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    query = f"""
        SELECT
            s.id,
            s.robot_id,
            s.mode,
            s.virtual_capital,
            s.account_id,
            s.started_at,
            s.ended_at,
            s.stop_reason
        FROM {schema}.robots_v2_sessions s
        JOIN {schema}.robots_v2 r ON r.id = s.robot_id
        WHERE s.robot_id = :robot_id AND r.user_id = :user_id
        ORDER BY s.started_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }


def build_count_sessions_query(
    *,
    robot_id: int,
    user_id: int,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_sessions s
        JOIN {schema}.robots_v2 r ON r.id = s.robot_id
        WHERE s.robot_id = :robot_id AND r.user_id = :user_id
    """
    return query, {"robot_id": robot_id, "user_id": user_id}


def _fills_session_filter(schema: str, session_id: UUID | None) -> tuple[str, dict[str, Any]]:
    if session_id is None:
        return "", {}
    return (
        f"""
            AND EXISTS (
                SELECT 1
                FROM {schema}.robots_v2_orders o
                JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
                WHERE o.id = f.order_id AND c.session_id = :session_id
            )
        """,
        {"session_id": session_id},
    )


def build_list_fills_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }
    session_filter, session_params = _fills_session_filter(schema, session_id)
    params.update(session_params)

    query = f"""
        SELECT
            f.id,
            f.order_id,
            f.robot_id,
            f.ticker,
            f.side,
            f.quantity,
            f.price,
            f.pnl,
            f.commission,
            f.kind,
            f.filled_at,
            c.session_id
        FROM {schema}.robots_v2_fills f
        JOIN {schema}.robots_v2_orders o ON o.id = f.order_id
        JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = f.robot_id
        WHERE f.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
        ORDER BY f.filled_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_count_fills_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _fills_session_filter(schema, session_id)
    params.update(session_params)
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_fills f
        JOIN {schema}.robots_v2 r ON r.id = f.robot_id
        WHERE f.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params


def _cycles_session_filter(session_id: UUID | None) -> tuple[str, dict[str, Any]]:
    if session_id is None:
        return "", {}
    return "AND c.session_id = :session_id", {"session_id": session_id}


def build_list_cycles_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }
    session_filter, session_params = _cycles_session_filter(session_id)
    params.update(session_params)

    query = f"""
        SELECT
            c.id,
            c.session_id,
            c.robot_id,
            c.cycle_number,
            c.triggered_by,
            c.started_at,
            c.finished_at,
            c.status,
            c.skip_reason,
            c.equity,
            c.stats
        FROM {schema}.robots_v2_cycles c
        JOIN {schema}.robots_v2 r ON r.id = c.robot_id
        WHERE c.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
        ORDER BY c.started_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_count_cycles_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _cycles_session_filter(session_id)
    params.update(session_params)
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_cycles c
        JOIN {schema}.robots_v2 r ON r.id = c.robot_id
        WHERE c.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params


def _decisions_session_filter(session_id: UUID | None) -> tuple[str, dict[str, Any]]:
    if session_id is None:
        return "", {}
    return (
        """
            AND EXISTS (
                SELECT 1
                FROM {schema}.robots_v2_cycles c
                WHERE c.id = d.cycle_id AND c.session_id = :session_id
            )
        """.format(schema="{schema}"),
        {"session_id": session_id},
    )


def build_list_decisions_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }
    if session_id is not None:
        session_filter = f"""
            AND EXISTS (
                SELECT 1
                FROM {schema}.robots_v2_cycles c
                WHERE c.id = d.cycle_id AND c.session_id = :session_id
            )
        """
        params["session_id"] = session_id
    else:
        session_filter = ""

    query = f"""
        SELECT
            d.id,
            d.cycle_id,
            d.robot_id,
            d.stage,
            d.outcome,
            d.code,
            d.message,
            d.ticker,
            d.context,
            d.created_at
        FROM {schema}.robots_v2_decisions d
        JOIN {schema}.robots_v2 r ON r.id = d.robot_id
        WHERE d.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
        ORDER BY d.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_count_decisions_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    if session_id is not None:
        session_filter = f"""
            AND EXISTS (
                SELECT 1
                FROM {schema}.robots_v2_cycles c
                WHERE c.id = d.cycle_id AND c.session_id = :session_id
            )
        """
        params["session_id"] = session_id
    else:
        session_filter = ""
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_decisions d
        JOIN {schema}.robots_v2 r ON r.id = d.robot_id
        WHERE d.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params


def _signals_session_filter(session_id: UUID | None) -> tuple[str, dict[str, Any]]:
    if session_id is None:
        return "", {}
    return "AND c.session_id = :session_id", {"session_id": session_id}


def build_list_signals_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }
    session_filter, session_params = _signals_session_filter(session_id)
    params.update(session_params)

    query = f"""
        SELECT
            s.id,
            s.cycle_id,
            s.robot_id,
            s.ticker,
            s.side,
            s.kind,
            s.reason,
            s.price,
            s.entry_price,
            s.delta_pct,
            s.created_at
        FROM {schema}.robots_v2_signals s
        JOIN {schema}.robots_v2_cycles c ON c.id = s.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = s.robot_id
        WHERE s.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
        ORDER BY s.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_count_signals_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _signals_session_filter(session_id)
    params.update(session_params)
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_signals s
        JOIN {schema}.robots_v2_cycles c ON c.id = s.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = s.robot_id
        WHERE s.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params


def _orders_session_filter(session_id: UUID | None) -> tuple[str, dict[str, Any]]:
    if session_id is None:
        return "", {}
    return "AND c.session_id = :session_id", {"session_id": session_id}


def build_list_orders_query(
    *,
    robot_id: int,
    user_id: int,
    limit: int,
    offset: int = 0,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "robot_id": robot_id,
        "user_id": user_id,
        "limit": limit,
        "offset": offset,
    }
    session_filter, session_params = _orders_session_filter(session_id)
    params.update(session_params)

    query = f"""
        SELECT
            o.id,
            o.cycle_id,
            o.robot_id,
            o.ticker,
            o.side,
            o.kind,
            o.quantity,
            o.price,
            o.status,
            o.mode,
            o.broker_order_id,
            o.reject_reason,
            o.submitted_at,
            COALESCE(o.order_type, 'MARKET') AS order_type
        FROM {schema}.robots_v2_orders o
        JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = o.robot_id
        WHERE o.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
        ORDER BY o.submitted_at DESC
        LIMIT :limit OFFSET :offset
    """
    return query, params


def build_count_orders_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _orders_session_filter(session_id)
    params.update(session_params)
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM {schema}.robots_v2_orders o
        JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = o.robot_id
        WHERE o.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params


def build_exit_reasons_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _orders_session_filter(session_id)
    params.update(session_params)
    query = f"""
        SELECT d.cycle_id, d.ticker, d.code
        FROM {schema}.robots_v2_decisions d
        JOIN {schema}.robots_v2_cycles c ON c.id = d.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = d.robot_id
        WHERE d.robot_id = :robot_id AND r.user_id = :user_id
          AND d.stage = 'exits'
          AND d.ticker IS NOT NULL
        {session_filter}
        ORDER BY d.created_at ASC
    """
    return query, params


def build_list_orders_all_query(
    *,
    robot_id: int,
    user_id: int,
    session_id: UUID | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"robot_id": robot_id, "user_id": user_id}
    session_filter, session_params = _orders_session_filter(session_id)
    params.update(session_params)
    query = f"""
        SELECT
            o.id,
            o.cycle_id,
            o.ticker,
            o.side,
            o.kind,
            o.quantity,
            o.price,
            o.status,
            o.reject_reason,
            COALESCE(o.order_type, 'MARKET') AS order_type
        FROM {schema}.robots_v2_orders o
        JOIN {schema}.robots_v2_cycles c ON c.id = o.cycle_id
        JOIN {schema}.robots_v2 r ON r.id = o.robot_id
        WHERE o.robot_id = :robot_id AND r.user_id = :user_id
        {session_filter}
    """
    return query, params
