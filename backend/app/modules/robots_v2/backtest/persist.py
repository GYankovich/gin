"""DB persistence for v2 backtest runs (public.backtest_runs)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.trading_core.sim.metrics import BacktestMetricsCalculator

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


def update_db_run(db: Session, run_id: int, **fields: Any) -> bool:
    """Update backtest_runs row. Returns False if the write failed (swallowed)."""
    if not fields:
        return True
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
        return True
    try:
        db.execute(text(f"UPDATE backtest_runs SET {', '.join(sets)} WHERE id = :rid"), params)
        db.commit()
        return True
    except Exception as exc:
        logger.warning("v2 backtest DB update failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False


_CRITICAL_RUN_FIELDS = frozenset({"status", "cancel_requested", "finished_at", "error_message"})


def update_db_run_required(db: Session, run_id: int, **fields: Any) -> None:
    """Like update_db_run but raises when terminal/cancel fields fail to persist."""
    ok = update_db_run(db, run_id, **fields)
    if ok:
        return
    critical = _CRITICAL_RUN_FIELDS.intersection(fields)
    if critical:
        raise RuntimeError(
            f"failed to persist backtest run {run_id} fields={sorted(critical)}"
        )


def _risk_adjusted_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    res = SimpleNamespace(
        trades=payload.get("trades") or [],
        equity_curve=payload.get("equity_curve") or [],
        initial_capital=float(payload.get("initial_capital") or 0),
        final_equity=float(payload.get("final_equity") or 0),
        max_drawdown_percent=payload.get("max_drawdown_percent"),
        fee_summary=payload.get("fee_summary") or {},
    )
    broker = str(payload.get("broker_type") or "moex")
    return BacktestMetricsCalculator.calculate(res=res, broker_type=broker)


def persist_result_payload(
    db: Session,
    run_id: int,
    payload: dict[str, Any],
    *,
    orders: list[dict[str, Any]] | None = None,
    portfolio_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trades = payload.get("trades") or []
    pnls = [float(t["pnl_net"]) for t in trades if t.get("pnl_net") is not None]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = (wins / len(pnls) * 100.0) if pnls else None
    avg_pnl = (sum(pnls) / len(pnls)) if pnls else None
    order_rows = orders if orders is not None else (payload.get("orders") or trades)
    snap_rows = portfolio_snapshots if portfolio_snapshots is not None else (payload.get("portfolio_snapshots") or [])
    risk = _risk_adjusted_metrics(payload)
    sharpe = risk.get("sharpe_val")
    sortino = risk.get("sortino_val")
    calmar = risk.get("calmar_val")
    summary = {
        "total_return_percent": payload.get("total_return_percent"),
        "max_drawdown_percent": payload.get("max_drawdown_percent"),
        "trades_total": len(trades),
        "final_equity": payload.get("final_equity"),
        "initial_capital": payload.get("initial_capital"),
        "win_rate_percent": round(win_rate, 4) if win_rate is not None else None,
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 4) if sortino is not None else None,
        "calmar_ratio": round(calmar, 4) if calmar is not None else None,
        "engine_version": "v2",
        "stages": payload.get("stages") or [],
        "history_stats": payload.get("history_stats") or {},
        "equity_curve": payload.get("equity_curve") or [],
        "trades": trades,
        "funding_charges_total": payload.get("funding_charges_total"),
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
                (run_id, total_return_percent, max_drawdown_percent, sharpe_ratio, trades_total,
                 win_rate_percent, avg_pnl_per_trade, final_equity, payload)
                VALUES
                (:rid, :ret, :dd, :sharpe, :trades, :win, :avg_pnl, :equity, CAST(:payload AS jsonb))
                ON CONFLICT (run_id) DO UPDATE SET
                    total_return_percent = EXCLUDED.total_return_percent,
                    max_drawdown_percent = EXCLUDED.max_drawdown_percent,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
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
                "sharpe": round(sharpe, 4) if sharpe is not None else None,
                "trades": len(trades),
                "win": win_rate,
                "avg_pnl": avg_pnl,
                "equity": payload.get("final_equity"),
                "payload": _json({
                    "engine_version": "v2",
                    "history_stats": payload.get("history_stats") or {},
                    "sortino_ratio": round(sortino, 4) if sortino is not None else None,
                    "calmar_ratio": round(calmar, 4) if calmar is not None else None,
                }),
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest metrics row persist failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass

    _persist_child_tables(db, run_id, trades=trades, orders=order_rows, snapshots=snap_rows)
    return {
        "sharpe_ratio": summary["sharpe_ratio"],
        "sortino_ratio": summary["sortino_ratio"],
        "calmar_ratio": summary["calmar_ratio"],
        "win_rate_percent": summary["win_rate_percent"],
    }


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _persist_child_tables(
    db: Session,
    run_id: int,
    *,
    trades: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> None:
    """Replace child rows for this run (signals from trades, orders, portfolio snapshots)."""
    try:
        db.execute(text("DELETE FROM backtest_signals WHERE run_id = :rid"), {"rid": run_id})
        db.execute(text("DELETE FROM backtest_orders WHERE run_id = :rid"), {"rid": run_id})
        db.execute(text("DELETE FROM backtest_portfolio_snapshots WHERE run_id = :rid"), {"rid": run_id})
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest child delete failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return

    for t in trades:
        try:
            db.execute(
                text("""
                    INSERT INTO backtest_signals
                        (run_id, signal_time, figi, signal_type, price, was_executed, payload)
                    VALUES
                        (:rid, :ts, :figi, :stype, :price, 1, CAST(:payload AS jsonb))
                """),
                {
                    "rid": run_id,
                    "ts": _parse_dt(t.get("bar_time")),
                    "figi": str(t.get("figi") or t.get("ticker") or "")[:20],
                    "stype": str(t.get("side") or "buy").lower()[:20],
                    "price": t.get("price"),
                    "payload": _json({
                        "reason": t.get("reason"),
                        "kind": t.get("kind"),
                        "quantity": t.get("quantity"),
                        "pnl_net": t.get("pnl_net"),
                        "engine_version": "v2",
                    }),
                },
            )
        except Exception as exc:
            logger.warning("v2 backtest signal insert failed run_id=%s: %s", run_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    for o in orders:
        try:
            db.execute(
                text("""
                    INSERT INTO backtest_orders
                        (run_id, signal_time, figi, side, status, quantity, requested_price,
                         executed_price, slippage_pct, commission, tax, pnl_net, payload)
                    VALUES
                        (:rid, :ts, :figi, :side, :status, :qty, :rp, :ep, 0, :comm, NULL, :pnl,
                         CAST(:payload AS jsonb))
                """),
                {
                    "rid": run_id,
                    "ts": _parse_dt(o.get("time") or o.get("bar_time")),
                    "figi": str(o.get("ticker") or o.get("figi") or "")[:20],
                    "side": str(o.get("side") or "buy").lower()[:10],
                    "status": "filled",
                    "qty": float(o.get("quantity") or o.get("qty") or 0),
                    "rp": o.get("price"),
                    "ep": o.get("price"),
                    "comm": o.get("commission"),
                    "pnl": o.get("pnl") if o.get("pnl") is not None else o.get("pnl_net"),
                    "payload": _json({
                        "kind": o.get("kind"),
                        "reason": o.get("reason"),
                        "engine_version": "v2",
                    }),
                },
            )
        except Exception as exc:
            logger.warning("v2 backtest order insert failed run_id=%s: %s", run_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # Persist a sampled curve of snapshots (cap to keep DB lean).
    max_snaps = 500
    step = max(1, len(snapshots) // max_snaps) if snapshots else 1
    for i, s in enumerate(snapshots):
        if i % step != 0 and i != len(snapshots) - 1:
            continue
        try:
            db.execute(
                text("""
                    INSERT INTO backtest_portfolio_snapshots
                        (run_id, snapshot_time, cash_balance, equity, positions_payload)
                    VALUES
                        (:rid, :ts, :cash, :equity, CAST(:positions AS jsonb))
                """),
                {
                    "rid": run_id,
                    "ts": _parse_dt(s.get("snapshot_time")) or datetime.now(timezone.utc),
                    "cash": float(s.get("cash") or 0),
                    "equity": float(s.get("equity") or 0),
                    "positions": _json({"positions": s.get("positions"), "engine_version": "v2"}),
                },
            )
        except Exception as exc:
            logger.warning("v2 backtest snapshot insert failed run_id=%s: %s", run_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def load_child_artifacts(db: Session, run_id: int) -> dict[str, list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    snaps: list[dict[str, Any]] = []
    try:
        for row in db.execute(
            text("""
                SELECT signal_time, figi, signal_type, price, was_executed, payload
                FROM backtest_signals WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            signals.append({
                "signal_time": row.get("signal_time"),
                "figi": row.get("figi"),
                "signal_type": row.get("signal_type"),
                "price": float(row["price"]) if row.get("price") is not None else None,
                "was_executed": int(row.get("was_executed") or 0),
                "payload": _parse_json(row.get("payload")) or {},
            })
        for row in db.execute(
            text("""
                SELECT signal_time, figi, side, status, quantity, requested_price, executed_price,
                       commission, pnl_net, payload
                FROM backtest_orders WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            orders.append({
                "time": row.get("signal_time"),
                "ticker": row.get("figi"),
                "side": row.get("side"),
                "status": row.get("status"),
                "quantity": float(row["quantity"]) if row.get("quantity") is not None else 0,
                "price": float(row["executed_price"]) if row.get("executed_price") is not None else None,
                "commission": float(row["commission"]) if row.get("commission") is not None else None,
                "pnl_net": float(row["pnl_net"]) if row.get("pnl_net") is not None else None,
                "payload": _parse_json(row.get("payload")) or {},
            })
        for row in db.execute(
            text("""
                SELECT snapshot_time, cash_balance, equity, positions_payload
                FROM backtest_portfolio_snapshots WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            snaps.append({
                "snapshot_time": row.get("snapshot_time"),
                "cash": float(row.get("cash_balance") or 0),
                "equity": float(row.get("equity") or 0),
                "positions_payload": _parse_json(row.get("positions_payload")) or {},
            })
    except Exception as exc:
        logger.warning("v2 backtest child load failed run_id=%s: %s", run_id, exc)
    return {"signals": signals, "orders": orders, "portfolio_snapshots": snaps}


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
            SELECT id, robot_id, user_id, status, requested_from, requested_to, started_at, finished_at,
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
    out = _row_to_dict(row)
    children = load_child_artifacts(db, run_id)
    if children["signals"]:
        out["signals"] = children["signals"]
    if children["orders"]:
        out["orders"] = children["orders"]
    if children["portfolio_snapshots"]:
        out["portfolio_snapshots"] = children["portfolio_snapshots"]
    return out


def fetch_db_run_by_id(db: Session, run_id: int) -> dict[str, Any] | None:
    """Worker-side load (no user filter)."""
    row = db.execute(
        text("""
            SELECT id, robot_id, user_id, status, requested_from, requested_to, started_at, finished_at,
                   initial_capital, progress_percent, run_phase, error_message, cancel_requested,
                   config_snapshot, metrics_summary
            FROM backtest_runs
            WHERE id = :rid
            LIMIT 1
        """),
        {"rid": run_id},
    ).mappings().first()
    if row is None:
        return None
    return _row_to_dict(row)


def is_cancel_requested(db: Session, run_id: int) -> bool:
    val = db.execute(
        text("SELECT cancel_requested FROM backtest_runs WHERE id = :rid LIMIT 1"),
        {"rid": run_id},
    ).scalar()
    return bool(val)


def count_v2_runs_by_status(db: Session, *, user_id: int, statuses: tuple[str, ...]) -> int:
    if not statuses:
        return 0
    placeholders = ", ".join(f":s{i}" for i in range(len(statuses)))
    params: dict[str, Any] = {"uid": user_id}
    for i, st in enumerate(statuses):
        params[f"s{i}"] = st
    n = db.execute(
        text(f"""
            SELECT COUNT(*) FROM backtest_runs
            WHERE user_id = :uid
              AND UPPER(status) IN ({placeholders})
              AND (
                config_snapshot->>'engine_version' = 'v2'
                OR COALESCE(execution_model->>'engine_version','') = 'v2'
              )
        """),
        params,
    ).scalar()
    return int(n or 0)


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
    out = {
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
        "sharpe_ratio": payload.get("sharpe_ratio"),
        "sortino_ratio": payload.get("sortino_ratio"),
        "calmar_ratio": payload.get("calmar_ratio"),
        "win_rate_percent": payload.get("win_rate_percent"),
        "trades_total": int(payload.get("trades_total") or len(payload.get("trades") or [])),
        "result_payload": payload,
        "signals": [],
        "orders": payload.get("trades") or [],
        "portfolio_snapshots": [],
        "daily_summary": payload.get("daily_summary") or [],
    }
    if "user_id" in row and row.get("user_id") is not None:
        out["user_id"] = int(row["user_id"])
    return out


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
            "sharpe_ratio": p.get("sharpe_ratio"),
            "sortino_ratio": p.get("sortino_ratio"),
            "calmar_ratio": p.get("calmar_ratio"),
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
