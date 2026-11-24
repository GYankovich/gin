#///EPIC Modules.ITEM Module.TOPIC MoexSecuritiesUpdaterQueries [1]
"""SQL builders for MOEX securities reference updater and cron_table."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROBOT_NAME = "moex_securities_updater"

# Board configs: (engine, market, board, instrument_group, instrument_type_default)
MOEX_BOARDS: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("stock", "shares", "TQBR", "stock_shares", "common_share"),
    ("stock", "bonds", "TQOB", "stock_bonds", "ofz_bond"),
    ("stock", "bonds", "TQCB", "stock_bonds", "corporate_bond"),
)


def build_due_cron_jobs_query(
    *,
    now: Optional[datetime] = None,
) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if now is not None:
        params["now"] = now
        now_expr = ":now"
    else:
        now_expr = "CURRENT_TIMESTAMP"
    sql = f"""
        SELECT id, robot_name, fixed_delay, last_run, next_run
        FROM cron_table
        WHERE is_active = true
          AND (next_run IS NULL OR next_run <= {now_expr})
        ORDER BY next_run NULLS FIRST, id
    """
    return sql, params


def build_mark_cron_run_query(
    *,
    cron_id: int,
    last_run: datetime,
    next_run: datetime,
) -> Tuple[str, Dict[str, Any]]:
    return """
        UPDATE cron_table
        SET
            last_run = :last_run,
            next_run = :next_run,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        """, {
        "id": cron_id,
        "last_run": last_run,
        "next_run": next_run,
    }


def build_active_secids_for_boards_query(boards: Sequence[str]) -> Tuple[str, Dict[str, Any]]:
    return """
        SELECT secid
        FROM tqbr_securities
        WHERE primary_board = ANY(:boards)
          AND is_active = true
        """, {"boards": list(boards)}


def build_deactivate_missing_query(
    *,
    boards: Sequence[str],
    seen_secids: Sequence[str],
) -> Tuple[str, Dict[str, Any]]:
    """Mark board rows inactive when they disappeared from the latest ISS pull."""
    return """
        UPDATE tqbr_securities
        SET
            is_active = false,
            is_traded = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE primary_board = ANY(:boards)
          AND is_active = true
          AND NOT (secid = ANY(:seen_secids))
        """, {
        "boards": list(boards),
        "seen_secids": list(seen_secids),
    }


def build_upsert_securities_batch(
    rows: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Bulk upsert one batch of MOEX securities into tqbr_securities."""
    if not rows:
        raise ValueError("empty securities batch")

    parts: List[str] = []
    params: Dict[str, Any] = {}
    for i, row in enumerate(rows):
        parts.append(
            "("
            f":secid_{i}, :shortname_{i}, :isin_{i}, :name_{i}, :regnumber_{i}, "
            f":instrument_type_{i}, :instrument_group_{i}, :engine_{i}, :market_{i}, "
            f":primary_board_{i}, :is_traded_{i}, :currency_{i}, :face_value_{i}, "
            f":maturity_date_{i}, :lot_size_{i}, :issuer_{i}, :list_level_{i}, "
            f":is_active_{i}, CAST(:extra_data_{i} AS jsonb), CURRENT_TIMESTAMP"
            ")"
        )
        params[f"secid_{i}"] = row["secid"]
        params[f"shortname_{i}"] = row.get("shortname")
        params[f"isin_{i}"] = row.get("isin")
        params[f"name_{i}"] = row.get("name")
        params[f"regnumber_{i}"] = row.get("regnumber")
        params[f"instrument_type_{i}"] = row.get("instrument_type")
        params[f"instrument_group_{i}"] = row.get("instrument_group")
        params[f"engine_{i}"] = row.get("engine")
        params[f"market_{i}"] = row.get("market")
        params[f"primary_board_{i}"] = row.get("primary_board")
        params[f"is_traded_{i}"] = bool(row.get("is_traded", True))
        params[f"currency_{i}"] = row.get("currency")
        params[f"face_value_{i}"] = row.get("face_value")
        params[f"maturity_date_{i}"] = row.get("maturity_date")
        params[f"lot_size_{i}"] = row.get("lot_size")
        params[f"issuer_{i}"] = row.get("issuer")
        params[f"list_level_{i}"] = row.get("list_level")
        params[f"is_active_{i}"] = bool(row.get("is_active", True))
        params[f"extra_data_{i}"] = row.get("extra_data_json") or "{}"

    sql = f"""
        INSERT INTO tqbr_securities (
            secid, shortname, isin, name, regnumber,
            instrument_type, instrument_group, engine, market, primary_board,
            is_traded, currency, face_value, maturity_date, lot_size,
            issuer, list_level, is_active, extra_data, updated_at
        )
        VALUES {", ".join(parts)}
        ON CONFLICT (secid) DO UPDATE SET
            shortname = EXCLUDED.shortname,
            isin = EXCLUDED.isin,
            name = EXCLUDED.name,
            regnumber = EXCLUDED.regnumber,
            instrument_type = EXCLUDED.instrument_type,
            instrument_group = EXCLUDED.instrument_group,
            engine = EXCLUDED.engine,
            market = EXCLUDED.market,
            primary_board = EXCLUDED.primary_board,
            is_traded = EXCLUDED.is_traded,
            currency = EXCLUDED.currency,
            face_value = EXCLUDED.face_value,
            maturity_date = EXCLUDED.maturity_date,
            lot_size = EXCLUDED.lot_size,
            issuer = EXCLUDED.issuer,
            list_level = EXCLUDED.list_level,
            is_active = EXCLUDED.is_active,
            extra_data = EXCLUDED.extra_data,
            updated_at = CURRENT_TIMESTAMP
    """
    return sql, params


def build_equity_universe_query(
    *,
    board: str = "TQBR",
    active_only: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Equity-only SECID list for backtest/universe consumers."""
    conditions = ["primary_board = :board"]
    params: Dict[str, Any] = {"board": board.upper()}
    if active_only:
        conditions.append("is_active = true")
    sql = f"""
        SELECT secid
        FROM tqbr_securities
        WHERE {" AND ".join(conditions)}
        ORDER BY secid
    """
    return sql, params


def build_search_securities_query(
    *,
    prefix: str,
    board: Optional[str] = "TQBR",
    limit: int = 50,
    active_only: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    conditions = ["secid ILIKE :prefix"]
    params: Dict[str, Any] = {
        "prefix": f"{prefix.strip().upper()}%",
        "limit": limit,
    }
    if board:
        conditions.append("primary_board = :board")
        params["board"] = board.upper()
    if active_only:
        conditions.append("is_active = true")
    sql = f"""
        SELECT secid, shortname, isin
        FROM tqbr_securities
        WHERE {" AND ".join(conditions)}
        ORDER BY secid
        LIMIT :limit
    """
    return sql, params


def build_list_securities_bulk_query(
    *,
    board: Optional[str] = "TQBR",
    limit: int = 12_000,
    active_only: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit}
    if board:
        conditions.append("primary_board = :board")
        params["board"] = board.upper()
    if active_only:
        conditions.append("is_active = true")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT secid, shortname, isin
        FROM tqbr_securities
        {where}
        ORDER BY secid
        LIMIT :limit
    """
    return sql, params
