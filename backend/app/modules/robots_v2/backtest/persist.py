"""DB persistence for v2 backtest runs (public.backtest_runs)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def create_db_run(
    db: Session,
    *,
    user_id: int,
    robot_id: int | None,
    requested_from: datetime,
    requested_to: datetime,
    initial_capital: float,
    config_snapshot: dict[str, Any],
) -> int | None:
    snap = {**config_snapshot, "engine_version": "v2", "v2RobotId": robot_id}
    params = {
        "robot_id": robot_id,
        "user_id": user_id,
        "requested_from": requested_from,
        "requested_to": requested_to,
        "started_at": datetime.now(timezone.utc),
        "board": "TQBR",
        "initial_capital": initial_capital,
        "config_snapshot": _json(snap),
        "execution_model": _json({"engine_version": "v2", "model": "BAR_CLOSE"}),
    }
    sql = """
        INSERT INTO backtest_runs
        (robot_id, user_id, requested_from, requested_to, started_at, status, board,
         initial_capital, config_snapshot, execution_model, cancel_requested, partial_result,
         run_phase, progress_percent)
        VALUES
        (:robot_id, :user_id, :requested_from, :requested_to, :started_at, 'QUEUED', :board,
         :initial_capital, CAST(:config_snapshot AS jsonb), CAST(:execution_model AS jsonb),
         false, false, 'queued', 0)
        RETURNING id
    """
    attempts: list[dict[str, Any]] = [params, {**params, "robot_id": None}]
    for attempt in attempts:
        try:
            run_id = db.execute(text(sql), attempt).scalar()
            db.commit()
            return int(run_id) if run_id is not None else None
        except Exception as exc:
            logger.warning("v2 backtest DB create attempt failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
    return None


def update_db_run(db: Session, run_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "status", "run_phase", "progress_percent", "phase_units_done", "phase_units_total",
        "finished_at", "error_message", "cancel_requested",
    }
    sets = []
    params: dict[str, Any] = {"rid": run_id}
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = :{key}")
        params[key] = value
    if not sets:
        return
    try:
        db.execute(text(f"UPDATE backtest_runs SET {', '.join(sets)} WHERE id = :rid"), params)
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest DB update failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def persist_result_payload(db: Session, run_id: int, payload: dict[str, Any]) -> None:
    trades = payload.get("trades") or []
    pnls = [float(t["pnl_net"]) for t in trades if t.get("pnl_net") is not None]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = (wins / len(pnls) * 100.0) if pnls else None
    avg_pnl = (sum(pnls) / len(pnls)) if pnls else None
    summary = {
        "total_return_percent": payload.get("total_return_percent"),
        "max_drawdown_percent": payload.get("max_drawdown_percent"),
        "trades_total": len(trades),
        "final_equity": payload.get("final_equity"),
        "initial_capital": payload.get("initial_capital"),
        "win_rate_percent": round(win_rate, 4) if win_rate is not None else None,
        "engine_version": "v2",
        "stages": payload.get("stages") or [],
        "history_stats": payload.get("history_stats") or {},
        "equity_curve": payload.get("equity_curve") or [],
        "trades": trades,
    }
    try:
        db.execute(
            text("""
                UPDATE backtest_runs
                SET metrics_summary = CAST(:summary AS jsonb)
                WHERE id = :rid
            """),
            {"rid": run_id, "summary": _json(summary)},
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest metrics_summary persist failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
    try:
        db.execute(
            text("""
                INSERT INTO backtest_metrics
                (run_id, total_return_percent, max_drawdown_percent, trades_total,
                 win_rate_percent, avg_pnl_per_trade, final_equity, payload)
                VALUES
                (:rid, :ret, :dd, :trades, :win, :avg_pnl, :equity, CAST(:payload AS jsonb))
                ON CONFLICT (run_id) DO UPDATE SET
                    total_return_percent = EXCLUDED.total_return_percent,
                    max_drawdown_percent = EXCLUDED.max_drawdown_percent,
                    trades_total = EXCLUDED.trades_total,
                    win_rate_percent = EXCLUDED.win_rate_percent,
                    avg_pnl_per_trade = EXCLUDED.avg_pnl_per_trade,
                    final_equity = EXCLUDED.final_equity,
                    payload = EXCLUDED.payload
            """),
            {
                "rid": run_id,
                "ret": payload.get("total_return_percent"),
                "dd": payload.get("max_drawdown_percent"),
                "trades": len(trades),
                "win": win_rate,
                "avg_pnl": avg_pnl,
                "equity": payload.get("final_equity"),
                "payload": _json({"engine_version": "v2", "history_stats": payload.get("history_stats") or {}}),
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest metrics row persist failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def _parse_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def fetch_db_run(db: Session, run_id: int, *, user_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text("""
            SELECT id, robot_id, status, requested_from, requested_to, started_at, finished_at,
                   initial_capital, progress_percent, run_phase, error_message, cancel_requested,
                   config_snapshot, metrics_summary
            FROM backtest_runs
            WHERE id = :rid AND user_id = :uid
            LIMIT 1
        """),
        {"rid": run_id, "uid": user_id},
    ).mappings().first()
    if row is None:
        return None
    return _row_to_dict(row)


def list_db_runs(
    db: Session,
    *,
    user_id: int,
    robot_id: int | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    where = ["user_id = :uid"]
    params: dict[str, Any] = {"uid": user_id, "lim": max(1, min(int(limit), 100))}
    if robot_id is not None:
        where.append(
            "(robot_id = :robot_id OR (config_snapshot->>'v2RobotId') = CAST(:robot_id AS text))"
        )
        params["robot_id"] = robot_id
    where.append(
        "(config_snapshot->>'engine_version' = 'v2' "
        "OR COALESCE(execution_model->>'engine_version','') = 'v2')"
    )
    rows = db.execute(
        text(f"""
            SELECT id, robot_id, status, requested_from, requested_to, started_at, finished_at,
                   initial_capital, progress_percent, run_phase, error_message, cancel_requested,
                   config_snapshot, metrics_summary
            FROM backtest_runs
            WHERE {' AND '.join(where)}
            ORDER BY started_at DESC
            LIMIT :lim
        """),
        params,
    ).mappings().all()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    summary = _parse_json(row.get("metrics_summary")) or {}
    config = _parse_json(row.get("config_snapshot")) or {}
    payload = summary if isinstance(summary, dict) else {}
    return {
        "run_id": int(row["id"]),
        "robot_id": row.get("robot_id"),
        "status": row.get("status") or "UNKNOWN",
        "requested_from": row.get("requested_from"),
        "requested_to": row.get("requested_to"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "initial_capital": float(row.get("initial_capital") or 0),
        "progress_percent": float(row.get("progress_percent") or 0),
        "run_phase": row.get("run_phase"),
        "phase_label": row.get("run_phase"),
        "cancel_requested": bool(row.get("cancel_requested")),
        "error_message": row.get("error_message"),
        "config_snapshot": config,
        "total_return_percent": payload.get("total_return_percent"),
        "max_drawdown_percent": payload.get("max_drawdown_percent"),
        "final_equity": payload.get("final_equity"),
        "trades_total": int(payload.get("trades_total") or len(payload.get("trades") or [])),
        "result_payload": payload,
        "signals": [],
        "orders": payload.get("trades") or [],
        "portfolio_snapshots": [],
        "daily_summary": payload.get("daily_summary") or [],
    }


def nested_config_diff(base: dict[str, Any], compare: dict[str, Any]) -> dict[str, Any]:
    """Leaf-level diff of nested dicts: path -> {base, compare}."""
    out: dict[str, Any] = {}

    def walk(a: Any, b: Any, path: str) -> None:
        if isinstance(a, dict) or isinstance(b, dict):
            keys = sorted(set((a or {}) if isinstance(a, dict) else []) | set((b or {}) if isinstance(b, dict) else []))
            for k in keys:
                av = a.get(k) if isinstance(a, dict) else None
                bv = b.get(k) if isinstance(b, dict) else None
                nxt = f"{path}.{k}" if path else str(k)
                walk(av, bv, nxt)
            return
        if a != b:
            out[path] = {"base": a, "compare": b}

    walk(base or {}, compare or {}, "")
    return out


def compare_runs(base: dict[str, Any], compare: dict[str, Any]) -> dict[str, Any]:
    def metrics(row: dict[str, Any]) -> dict[str, Any]:
        p = row.get("result_payload") or {}
        return {
            "total_return_percent": p.get("total_return_percent"),
            "max_drawdown_percent": p.get("max_drawdown_percent"),
            "final_equity": p.get("final_equity"),
            "trades_total": row.get("trades_total") or len(p.get("trades") or []),
            "win_rate_percent": p.get("win_rate_percent"),
            "initial_capital": row.get("initial_capital"),
        }

    base_m = metrics(base)
    comp_m = metrics(compare)
    diff: dict[str, Any] = {}
    for k, bv in base_m.items():
        cv = comp_m.get(k)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            diff[k] = round(float(cv) - float(bv), 6)
        else:
            diff[k] = None
    return {
        "base_run_id": base["run_id"],
        "compare_run_id": compare["run_id"],
        "metrics_base": base_m,
        "metrics_compare": comp_m,
        "metrics_diff": diff,
        "config_diff": nested_config_diff(base.get("config_snapshot") or {}, compare.get("config_snapshot") or {}),
        "base": {
            "requested_from": base.get("requested_from"),
            "requested_to": base.get("requested_to"),
            "initial_capital": base.get("initial_capital"),
            "status": base.get("status"),
        },
        "compare": {
            "requested_from": compare.get("requested_from"),
            "requested_to": compare.get("requested_to"),
            "initial_capital": compare.get("initial_capital"),
            "status": compare.get("status"),
        },
    }
