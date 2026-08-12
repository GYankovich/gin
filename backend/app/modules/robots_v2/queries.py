"""SQL query builders for robots v2."""

from __future__ import annotations

from typing import Any


def build_list_robots_query(
    *,
    user_id: int,
    robot_status: list[int] | None = None,
    robot_type: list[int] | None = None,
    schema: str = "public",
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"user_id": user_id}
    conditions = ["r.user_id = :user_id"]
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
            r.date_creation,
            r.date_modification
        FROM {schema}.robots_v2 r
        WHERE {where}
        ORDER BY r.date_creation DESC
    """
    return query, params


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
            r.date_creation,
            r.date_modification
        FROM {schema}.robots_v2 r
        WHERE r.id = :robot_id AND r.user_id = :user_id
    """
    return query, {"robot_id": robot_id, "user_id": user_id}


def build_insert_robot_query(schema: str = "public") -> str:
    return f"""
        INSERT INTO {schema}.robots_v2 (
            name, user_id, token_id, type, status, config_version, config, metadata, usercre
        ) VALUES (
            :name, :user_id, :token_id, :type, :status, :config_version, :config, :metadata, :usercre
        )
        RETURNING id
    """


def build_update_robot_query(schema: str = "public") -> str:
    return f"""
        UPDATE {schema}.robots_v2
        SET
            name = :name,
            token_id = :token_id,
            type = :type,
            status = :status,
            config_version = :config_version,
            config = :config,
            metadata = :metadata,
            usermod = :usermod,
            date_modification = NOW()
        WHERE id = :robot_id AND user_id = :user_id
        RETURNING id
    """


def build_delete_robot_query(schema: str = "public") -> str:
    return f"""
        DELETE FROM {schema}.robots_v2
        WHERE id = :robot_id AND user_id = :user_id
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
        UPDATE {schema}.robots_v2
        SET status = :status, usermod = :usermod, date_modification = NOW()
        WHERE id = :robot_id AND user_id = :user_id
        RETURNING id
    """
