"""DB persistence for v2 backtest runs (public.backtest_runs)."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.trading_core.sim.metrics import BacktestMetricsCalculator

logger = logging.getLogger(__name__)

# Soft-degrade: details inlines signals up to this size; larger runs use pagination.
DETAILS_SIGNALS_INLINE_CAP = 5_000
REJECT_REASON_TOP_N = 8
SIGNAL_LOG_CAP = 25_000

NEXT_BAR_OPEN_EXECUTION_MODEL: dict[str, Any] = {
    "engine_version": "v2",
    "model": "NEXT_BAR_OPEN",
    "code": "NEXT_BAR_OPEN",
    "signal_on": "BAR_CLOSE",
    "fill_on": "NEXT_BAR_OPEN",
    "look_ahead": False,
    "label": "Fills at next bar open",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _normalize_soft_bind_robot_id(robot_id: int | None) -> int | None:
    """Soft bind id for DB; never persist fake ``0`` (host-only sentinel)."""
    if robot_id is None:
        return None
    rid = int(robot_id)
    if rid <= 0:
        return None
    return rid


def _snapshot_for_run(config_snapshot: dict[str, Any], robot_id: int | None) -> dict[str, Any]:
    """Build config_snapshot with engine_version=v2; set/clear v2RobotId for soft bind."""
    snap = {**config_snapshot, "engine_version": "v2"}
    if robot_id is not None:
        snap["v2RobotId"] = robot_id
    else:
        snap.pop("v2RobotId", None)
    return snap


_SNAPSHOT_RUN_META_KEYS = frozenset({"engine_version", "v2RobotId"})


def trading_config_from_snapshot(config_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Strip Lab/backtest metadata before persisting as robots_v2.config."""
    if not isinstance(config_snapshot, dict):
        raise ValueError("config_snapshot must be an object")
    return {k: v for k, v in config_snapshot.items() if k not in _SNAPSHOT_RUN_META_KEYS}


def _bound_robot_id_from_run(row: dict[str, Any]) -> int | None:
    rid = row.get("robot_id")
    if rid is not None:
        try:
            return int(rid)
        except (TypeError, ValueError):
            pass
    snap = row.get("config_snapshot")
    if isinstance(snap, dict):
        v2 = snap.get("v2RobotId")
        if v2 is not None and str(v2).strip():
            try:
                return int(v2)
            except (TypeError, ValueError):
                pass
    return None


def attach_backtest_run_to_robot(
    db: Session,
    *,
    run_id: int,
    user_id: int,
    robot_id: int,
) -> None:
    """Bind a completed run to a robot (robot_id + config_snapshot.v2RobotId). Caller commits."""
    row = fetch_db_run(db, run_id, user_id=user_id)
    if row is None:
        raise ValueError("run not found")
    bound = _bound_robot_id_from_run(row)
    new_id = int(robot_id)
    if bound is not None and bound != new_id:
        raise RuntimeError("attach conflict")
    snap_raw = row.get("config_snapshot")
    trading = trading_config_from_snapshot(snap_raw if isinstance(snap_raw, dict) else None)
    merged = _snapshot_for_run(trading, new_id)
    db.execute(
        text("""
            UPDATE backtest_runs
            SET robot_id = :robot_id,
                config_snapshot = CAST(:config_snapshot AS jsonb)
            WHERE id = :run_id AND user_id = :user_id
        """),
        {
            "run_id": int(run_id),
            "user_id": int(user_id),
            "robot_id": new_id,
            "config_snapshot": json.dumps(merged, ensure_ascii=False),
        },
    )


def _config_label_from_snapshot(config: dict[str, Any] | None) -> str | None:
    """Lab list hint: strategy archetype (or name) from snapshot."""
    if not isinstance(config, dict):
        return None
    strategy = config.get("strategy")
    if isinstance(strategy, dict):
        archetype = strategy.get("archetype")
        if archetype:
            return str(archetype)
    name = config.get("name")
    if name:
        return str(name)
    return None


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
    """Insert a v2 backtest run. ``robot_id`` may be NULL (Lab orphan / unbound)."""
    bind_id = _normalize_soft_bind_robot_id(robot_id)
    snap = _snapshot_for_run(config_snapshot, bind_id)
    params = {
        "robot_id": bind_id,
        "user_id": user_id,
        "requested_from": requested_from,
        "requested_to": requested_to,
        "started_at": datetime.now(timezone.utc),
        "board": "TQBR",
        "initial_capital": initial_capital,
        "config_snapshot": _json(snap),
        "execution_model": _json(NEXT_BAR_OPEN_EXECUTION_MODEL),
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
    # Prefer intended bind; legacy fallback nullifies only when a non-null insert fails
    # (e.g. residual NOT NULL on older DBs before 0067).
    attempts: list[dict[str, Any]] = [params]
    if bind_id is not None:
        orphan_snap = _snapshot_for_run(config_snapshot, None)
        attempts.append({**params, "robot_id": None, "config_snapshot": _json(orphan_snap)})

    if bind_id is None:
        logger.info(
            "event=backtest_run.create user_id=%s robot_id=null orphan=true",
            user_id,
        )
    else:
        logger.info(
            "event=backtest_run.create user_id=%s robot_id=%s orphan=false",
            user_id,
            bind_id,
        )

    for attempt in attempts:
        try:
            run_id = db.execute(text(sql), attempt).scalar()
            db.commit()
            if run_id is None:
                return None
            return int(run_id)
        except Exception as exc:
            logger.warning("v2 backtest DB create attempt failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
    return None


def nullify_robot_soft_bind(db: Session, *, robot_id: int) -> int:
    """On robot delete: clear soft bind so runs become Lab orphans (SPEC-05 §5/§10).

    Sets ``robot_id`` NULL and removes ``config_snapshot.v2RobotId`` when it matches.
    Does not commit/rollback — caller owns the transaction.
    Returns number of rows updated (best-effort; 0 on failure).
    """
    rid = int(robot_id)
    try:
        result = db.execute(
            text("""
                UPDATE backtest_runs
                SET
                    robot_id = NULL,
                    config_snapshot = CASE
                        WHEN (config_snapshot->>'v2RobotId') = CAST(:robot_id AS text)
                        THEN config_snapshot - 'v2RobotId'
                        ELSE config_snapshot
                    END
                WHERE robot_id = :robot_id
                   OR (config_snapshot->>'v2RobotId') = CAST(:robot_id AS text)
            """),
            {"robot_id": rid},
        )
        n = int(result.rowcount or 0)
        logger.info(
            "event=backtest_run.nullify_bind robot_id=%s rows=%s",
            rid,
            n,
        )
        return n
    except Exception as exc:
        logger.warning("nullify_robot_soft_bind failed robot_id=%s: %s", rid, exc)
        return 0


def update_db_run(db: Session, run_id: int, **fields: Any) -> bool:
    """Update backtest_runs row. Returns False if the write failed (swallowed)."""
    if not fields:
        return True
    allowed = {
        "status", "run_phase", "progress_percent", "phase_units_done", "phase_units_total",
        "finished_at", "error_message", "cancel_requested", "partial_result",
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


_CRITICAL_RUN_FIELDS = frozenset({
    "status", "cancel_requested", "finished_at", "error_message", "partial_result",
})


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


def _normalize_signal_status(raw: Any, *, was_executed: Any = None) -> str:
    status = str(raw or "").lower().strip()
    if status in ("filled", "submitted"):
        return "filled"
    if status == "deferred":
        return "deferred"
    if status == "rejected":
        return "rejected"
    if int(was_executed or 0):
        return "filled"
    if status:
        return status
    return "rejected"


def promote_deferred_signals_to_filled(
    signals: list[dict[str, Any]],
    *,
    fills: list[dict[str, Any]] | None = None,
    trades: list[dict[str, Any]] | None = None,
    execution_events: list[dict[str, Any]] | None = None,
) -> int:
    """Promote deferred signal rows to filled once a next-open fill is known.

    Matching preference: ``intent_id``, then ``(cycle_id, ticker[, kind])``.

    Reject-lens semantics after this + :func:`build_observability`:
    - ``filled``: successful fills (native filled signals + promoted deferred)
    - ``deferred``: still waiting at count time (not yet filled)
    - ``rejected``: reject / drop signals
    """
    filled_intent_ids: set[str] = set()
    filled_keys: set[tuple[str, str, str]] = set()

    def _note_fill(row: dict[str, Any]) -> None:
        iid = str(row.get("intent_id") or "").strip()
        if iid:
            filled_intent_ids.add(iid)
        cid = str(row.get("cycle_id") or "").strip()
        ticker = str(row.get("ticker") or row.get("figi") or "").upper().strip()
        kind = str(row.get("kind") or "").strip()
        if cid and ticker:
            filled_keys.add((cid, ticker, kind))
            filled_keys.add((cid, ticker, ""))

    for row in fills or []:
        _note_fill(row)
    for row in trades or []:
        _note_fill(row)
    for row in execution_events or []:
        if str(row.get("status") or "").lower() != "filled":
            continue
        _note_fill(row)

    if not filled_intent_ids and not filled_keys:
        return 0

    promoted = 0
    for signal in signals:
        status = _normalize_signal_status(
            signal.get("status"), was_executed=signal.get("was_executed"),
        )
        if status != "deferred":
            continue
        iid = str(signal.get("intent_id") or "").strip()
        cid = str(signal.get("cycle_id") or "").strip()
        ticker = str(signal.get("figi") or signal.get("ticker") or "").upper().strip()
        kind = str(signal.get("kind") or "").strip()
        matched = bool(iid and iid in filled_intent_ids)
        if not matched and cid and ticker:
            matched = (cid, ticker, kind) in filled_keys or (cid, ticker, "") in filled_keys
        if not matched:
            continue
        signal["status"] = "filled"
        signal["was_executed"] = 1
        if iid:
            signal["intent_id"] = iid
        promoted += 1
    return promoted


def build_observability(
    signals: list[dict[str, Any]],
    *,
    history_stats: dict[str, Any] | None = None,
    signal_log_cap: int = SIGNAL_LOG_CAP,
) -> dict[str, Any]:
    """Aggregate glass-box summary for UI reject lens + honesty banner.

    ``status_counts`` buckets (after deferred→filled promotion on host/enrich):
    - filled: successful fills
    - deferred: still waiting (not filled yet)
    - rejected: reject / dropped-deferred signals
    """
    stats = history_stats or {}
    reject_counts: Counter[str] = Counter()
    status_counts = {"filled": 0, "rejected": 0, "deferred": 0}
    for s in signals:
        status = _normalize_signal_status(s.get("status"), was_executed=s.get("was_executed"))
        if status in status_counts:
            status_counts[status] += 1
        else:
            # Keep status_counts exhaustive for glass-box UI (unknown → rejected bucket).
            status_counts["rejected"] += 1
            status = "rejected"
        if status == "rejected":
            rr = s.get("reject_reason")
            if rr:
                reject_counts[str(rr)] += 1
    top = [
        {"code": code, "count": int(count)}
        for code, count in reject_counts.most_common(REJECT_REASON_TOP_N)
    ]
    truncated = bool(stats.get("signals_truncated"))
    logged = int(stats.get("signals") or len(signals))
    return {
        "execution_model": {
            "code": "NEXT_BAR_OPEN",
            "label": "Fills at next bar open",
            "look_ahead": False,
        },
        "signals_logged": logged,
        "signals_truncated": truncated,
        "signal_log_cap": int(signal_log_cap),
        "reject_reason_counts": top,
        "status_counts": status_counts,
    }


def _attach_linked_trade_ids(
    signals: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> None:
    """Best-effort cycle→trade linkage; incomplete when cycle_id missing (old runs)."""
    by_cycle: dict[str, list[int]] = {}
    for t in trades:
        cid = t.get("cycle_id")
        if not cid:
            continue
        tid = t.get("id")
        if tid is None:
            continue
        by_cycle.setdefault(str(cid), []).append(int(tid))
    for s in signals:
        cid = s.get("cycle_id")
        if cid:
            s["linked_trade_ids"] = list(by_cycle.get(str(cid), []))
        else:
            s.setdefault("linked_trade_ids", [])


def persist_result_payload(
    db: Session,
    run_id: int,
    payload: dict[str, Any],
    *,
    orders: list[dict[str, Any]] | None = None,
    portfolio_snapshots: list[dict[str, Any]] | None = None,
    signals: list[dict[str, Any]] | None = None,
    universe_by_day: dict[Any, list[str]] | None = None,
    execution_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trades = payload.get("trades") or []
    pnls = [float(t["pnl_net"]) for t in trades if t.get("pnl_net") is not None]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = (wins / len(pnls) * 100.0) if pnls else None
    avg_pnl = (sum(pnls) / len(pnls)) if pnls else None
    order_rows = orders if orders is not None else (payload.get("orders") or trades)
    snap_rows = portfolio_snapshots if portfolio_snapshots is not None else (payload.get("portfolio_snapshots") or [])
    signal_rows = signals if signals is not None else (payload.get("signals") or [])
    daily_summary = payload.get("daily_summary") or []
    history_stats = payload.get("history_stats") or {}
    observability = payload.get("observability") or build_observability(
        signal_rows,
        history_stats=history_stats,
    )
    fee_summary = payload.get("fee_summary")
    if not isinstance(fee_summary, dict):
        from app.modules.robots_v2.backtest.host import build_fee_summary

        fee_summary = build_fee_summary(
            trades,
            funding_total=float(payload.get("funding_charges_total") or 0),
            funding_events=int(history_stats.get("funding_events") or 0),
        )
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
        "history_stats": history_stats,
        "equity_curve": payload.get("equity_curve") or [],
        "trades": trades,
        "daily_summary": daily_summary,
        "funding_charges_total": payload.get("funding_charges_total"),
        "fee_summary": fee_summary,
        "observability": observability,
        "narrative": list(payload.get("narrative") or []),
    }
    try:
        db.execute(
            text("""
                UPDATE backtest_runs
                SET metrics_summary = CAST(:summary AS jsonb),
                    execution_model = CAST(:execution_model AS jsonb)
                WHERE id = :rid
            """),
            {
                "rid": run_id,
                "summary": _json(summary),
                "execution_model": _json(NEXT_BAR_OPEN_EXECUTION_MODEL),
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest metrics_summary persist failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        # Fallback without execution_model column rewrite (older schemas / partial deploys).
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
        except Exception as exc2:
            logger.warning("v2 backtest metrics_summary fallback failed run_id=%s: %s", run_id, exc2)
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
                    "history_stats": history_stats,
                    "sortino_ratio": round(sortino, 4) if sortino is not None else None,
                    "calmar_ratio": round(calmar, 4) if calmar is not None else None,
                    "observability": observability,
                    "fee_summary": fee_summary,
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

    _persist_child_tables(
        db,
        run_id,
        trades=trades,
        orders=order_rows,
        snapshots=snap_rows,
        signals=signal_rows,
    )
    uni = universe_by_day if universe_by_day is not None else payload.get("universe_by_day")
    if isinstance(uni, dict):
        # Always replace (including empty) so re-persists do not leave stale membership.
        persist_universe_membership(db, run_id, uni)
    events = (
        execution_events
        if execution_events is not None
        else list(payload.get("execution_events") or [])
    )
    persist_execution_events(db, run_id, events)
    return {
        "sharpe_ratio": summary["sharpe_ratio"],
        "sortino_ratio": summary["sortino_ratio"],
        "calmar_ratio": summary["calmar_ratio"],
        "win_rate_percent": summary["win_rate_percent"],
        "observability": observability,
        "fee_summary": fee_summary,
        "narrative": summary["narrative"],
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
    signals: list[dict[str, Any]] | None = None,
) -> None:
    """Replace child rows for this run (signal log, orders, portfolio snapshots)."""
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

    signal_rows = list(signals or [])
    if not signal_rows:
        # Fallback for older payloads: derive executed-only rows from trades.
        for t in trades:
            signal_rows.append({
                "signal_time": t.get("bar_time"),
                "figi": t.get("figi") or t.get("ticker"),
                "signal_type": t.get("side") or "buy",
                "price": t.get("price"),
                "was_executed": 1,
                "reason": t.get("reason"),
                "kind": t.get("kind"),
                "quantity": t.get("quantity"),
                "status": "filled",
                "pnl_net": t.get("pnl_net"),
            })

    for s in signal_rows:
        try:
            db.execute(
                text("""
                    INSERT INTO backtest_signals
                        (run_id, signal_time, figi, signal_type, price, was_executed, payload)
                    VALUES
                        (:rid, :ts, :figi, :stype, :price, :exec, CAST(:payload AS jsonb))
                """),
                {
                    "rid": run_id,
                    "ts": _parse_dt(s.get("signal_time") or s.get("bar_time")),
                    "figi": str(s.get("figi") or s.get("ticker") or "")[:20],
                    "stype": str(s.get("signal_type") or s.get("side") or "buy").lower()[:20],
                    "price": s.get("price"),
                    "exec": int(s.get("was_executed") or 0),
                    "payload": _json({
                        "reason": s.get("reason"),
                        "reject_reason": s.get("reject_reason"),
                        "kind": s.get("kind"),
                        "status": s.get("status"),
                        "quantity": s.get("quantity"),
                        "cycle_id": s.get("cycle_id"),
                        "intent_id": s.get("intent_id"),
                        "signal_time": s.get("signal_time") or s.get("bar_time"),
                        "pnl_net": s.get("pnl_net"),
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
                    "status": str(o.get("status") or "filled").lower()[:20],
                    "qty": float(o.get("quantity") or o.get("qty") or 0),
                    "rp": o.get("price"),
                    "ep": o.get("price"),
                    "comm": o.get("commission"),
                    "pnl": o.get("pnl") if o.get("pnl") is not None else o.get("pnl_net"),
                    "payload": _json({
                        "kind": o.get("kind"),
                        "reason": o.get("reason"),
                        "cycle_id": o.get("cycle_id"),
                        "intent_id": o.get("intent_id"),
                        "signal_time": o.get("signal_time"),
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
            holdings = s.get("positions")
            if isinstance(holdings, list):
                positions_payload = {
                    "positions": holdings,
                    "positions_count": int(s.get("positions_count") or len(holdings)),
                    "engine_version": "v2",
                }
            else:
                # Legacy: positions was a count integer.
                positions_payload = {
                    "positions": [],
                    "positions_count": int(holdings or s.get("positions_count") or 0),
                    "engine_version": "v2",
                }
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
                    "positions": _json(positions_payload),
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


def persist_universe_membership(
    db: Session,
    run_id: int,
    universe_by_day: dict[Any, list[str]],
    *,
    source: str | None = "v2_host",
) -> None:
    """Replace daily universe membership rows for a run (P1)."""
    try:
        db.execute(
            text("DELETE FROM backtest_universe_membership WHERE run_id = :rid"),
            {"rid": run_id},
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest universe delete failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return

    rows = 0
    for day_key, tickers in (universe_by_day or {}).items():
        trade_date = _coerce_trade_date(day_key)
        if trade_date is None:
            continue
        for raw_ticker in tickers or []:
            ticker = str(raw_ticker or "").upper().strip()
            if not ticker:
                continue
            try:
                db.execute(
                    text("""
                        INSERT INTO backtest_universe_membership
                            (run_id, trade_date, ticker, source, filter_result, reject_reason)
                        VALUES
                            (:rid, :d, :ticker, :source, NULL, NULL)
                        ON CONFLICT (run_id, trade_date, ticker) DO NOTHING
                    """),
                    {
                        "rid": run_id,
                        "d": trade_date,
                        "ticker": ticker[:32],
                        "source": source,
                    },
                )
                rows += 1
            except Exception as exc:
                logger.warning(
                    "v2 backtest universe insert failed run_id=%s day=%s: %s",
                    run_id, trade_date, exc,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
                return
    try:
        db.commit()
        logger.info("v2 backtest universe membership persisted run_id=%s rows=%s", run_id, rows)
    except Exception as exc:
        logger.warning("v2 backtest universe commit failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def _coerce_trade_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def load_universe_membership(
    db: Session,
    run_id: int,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    clauses = ["run_id = :rid"]
    params: dict[str, Any] = {"rid": run_id}
    if from_date is not None:
        clauses.append("trade_date >= :from_d")
        params["from_d"] = from_date
    if to_date is not None:
        clauses.append("trade_date <= :to_d")
        params["to_d"] = to_date
    try:
        rows = db.execute(
            text(f"""
                SELECT trade_date, ticker, source, filter_result, reject_reason
                FROM backtest_universe_membership
                WHERE {' AND '.join(clauses)}
                ORDER BY trade_date ASC, ticker ASC
            """),
            params,
        ).mappings().all()
    except Exception as exc:
        logger.warning("v2 backtest universe load failed run_id=%s: %s", run_id, exc)
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        d = row.get("trade_date")
        out.append({
            "trade_date": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "ticker": row.get("ticker"),
            "source": row.get("source"),
            "filter_result": row.get("filter_result"),
            "reject_reason": row.get("reject_reason"),
        })
    return out


def persist_execution_events(
    db: Session,
    run_id: int,
    events: list[dict[str, Any]],
) -> None:
    """Replace intent↔fill lifecycle rows for a run (P2 / [R-13])."""
    try:
        db.execute(
            text("DELETE FROM backtest_execution_events WHERE run_id = :rid"),
            {"rid": run_id},
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest execution_events delete failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return

    for ev in events or []:
        try:
            db.execute(
                text("""
                    INSERT INTO backtest_execution_events
                        (run_id, event_time, intent_id, cycle_id, ticker, side, kind, status,
                         reason, reject_reason, quantity, price, trade_id, payload)
                    VALUES
                        (:rid, :ts, :intent_id, :cycle_id, :ticker, :side, :kind, :status,
                         :reason, :reject_reason, :qty, :price, :trade_id, CAST(:payload AS jsonb))
                """),
                {
                    "rid": run_id,
                    "ts": _parse_dt(ev.get("ts") or ev.get("event_time")) or datetime.now(timezone.utc),
                    "intent_id": str(ev.get("intent_id") or "")[:64] or "unknown",
                    "cycle_id": (str(ev.get("cycle_id"))[:64] if ev.get("cycle_id") else None),
                    "ticker": str(ev.get("ticker") or "")[:32],
                    "side": (str(ev.get("side"))[:10] if ev.get("side") else None),
                    "kind": (str(ev.get("kind"))[:32] if ev.get("kind") else None),
                    "status": str(ev.get("status") or "unknown")[:20],
                    "reason": (str(ev.get("reason"))[:64] if ev.get("reason") else None),
                    "reject_reason": (
                        str(ev.get("reject_reason"))[:64] if ev.get("reject_reason") else None
                    ),
                    "qty": ev.get("quantity"),
                    "price": ev.get("price"),
                    "trade_id": ev.get("trade_id"),
                    "payload": _json({
                        "event_id": ev.get("event_id"),
                        "signal_time": ev.get("signal_time"),
                        "engine_version": "v2",
                    }),
                },
            )
        except Exception as exc:
            logger.warning("v2 backtest execution_events insert failed run_id=%s: %s", run_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return
    try:
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest execution_events commit failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def load_execution_events(
    db: Session,
    run_id: int,
    *,
    cycle_id: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    clauses = ["run_id = :rid"]
    params: dict[str, Any] = {
        "rid": run_id,
        "lim": max(1, min(int(limit), 25_000)),
    }
    if cycle_id:
        clauses.append("cycle_id = :cid")
        params["cid"] = str(cycle_id)
    try:
        rows = db.execute(
            text(f"""
                SELECT id, event_time, intent_id, cycle_id, ticker, side, kind, status,
                       reason, reject_reason, quantity, price, trade_id, payload
                FROM backtest_execution_events
                WHERE {' AND '.join(clauses)}
                ORDER BY id ASC
                LIMIT :lim
            """),
            params,
        ).mappings().all()
    except Exception as exc:
        logger.warning("v2 backtest execution_events load failed run_id=%s: %s", run_id, exc)
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = _parse_json(row.get("payload")) or {}
        ts = row.get("event_time")
        out.append({
            "id": int(row["id"]) if row.get("id") is not None else None,
            "event_id": payload.get("event_id"),
            "ts": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "intent_id": row.get("intent_id"),
            "cycle_id": row.get("cycle_id"),
            "ticker": row.get("ticker"),
            "side": row.get("side"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "reason": row.get("reason"),
            "reject_reason": row.get("reject_reason"),
            "quantity": float(row["quantity"]) if row.get("quantity") is not None else None,
            "price": float(row["price"]) if row.get("price") is not None else None,
            "trade_id": int(row["trade_id"]) if row.get("trade_id") is not None else None,
            "signal_time": payload.get("signal_time"),
        })
    return out


def build_cycle_inspector_bundle(
    run: dict[str, Any],
    cycle_id: str,
) -> dict[str, Any] | None:
    """Assemble decision inspector packet for one cycle_id (SPEC §6.2 + P2 events)."""
    cid = str(cycle_id or "").strip()
    if not cid:
        return None
    signals = [
        s for s in (run.get("signals") or [])
        if str(s.get("cycle_id") or "") == cid
    ]
    payload = run.get("result_payload") if isinstance(run.get("result_payload"), dict) else {}
    trades = [
        t for t in (payload.get("trades") or [])
        if str(t.get("cycle_id") or "") == cid
    ]
    orders = [
        o for o in (run.get("orders") or [])
        if str(o.get("cycle_id") or "") == cid
    ]
    exec_events = [
        e for e in (run.get("execution_events") or [])
        if str(e.get("cycle_id") or "") == cid
    ]
    if not signals and not trades and not orders and not exec_events:
        return None
    config = run.get("config_snapshot") if isinstance(run.get("config_snapshot"), dict) else {}
    risk = config.get("risk") if isinstance(config.get("risk"), dict) else {}
    strategy = config.get("strategy") if isinstance(config.get("strategy"), dict) else {}
    excerpt = {
        "archetype": strategy.get("archetype") or strategy.get("archetypeName"),
        "timeframe": strategy.get("timeframe"),
        "stopLossPct": risk.get("stopLossPct") or risk.get("stop_loss_pct"),
        "takeProfitPct": risk.get("takeProfitPct") or risk.get("take_profit_pct"),
        "maxPositionSharePct": risk.get("maxPositionSharePct") or risk.get("max_position_share_pct"),
        "maxConcurrentPositions": (
            risk.get("maxConcurrentPositions") or risk.get("max_concurrent_positions")
        ),
        "brokerCommissionPct": risk.get("brokerCommissionPct") or risk.get("broker_commission_pct"),
    }
    return {
        "cycle_id": cid,
        "signals": signals,
        "trades": trades,
        "orders": orders,
        "execution_events": exec_events,
        "config_risk_excerpt": {k: v for k, v in excerpt.items() if v is not None},
    }


def load_child_artifacts(db: Session, run_id: int) -> dict[str, list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    snaps: list[dict[str, Any]] = []
    try:
        for row in db.execute(
            text("""
                SELECT id, signal_time, figi, signal_type, price, was_executed, payload
                FROM backtest_signals WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            payload = _parse_json(row.get("payload")) or {}
            signals.append({
                "id": int(row["id"]) if row.get("id") is not None else None,
                "signal_time": row.get("signal_time"),
                "figi": row.get("figi"),
                "signal_type": row.get("signal_type"),
                "price": float(row["price"]) if row.get("price") is not None else None,
                "was_executed": int(row.get("was_executed") or 0),
                "reason": payload.get("reason"),
                "reject_reason": payload.get("reject_reason"),
                "kind": payload.get("kind"),
                "status": payload.get("status"),
                "quantity": payload.get("quantity"),
                "cycle_id": payload.get("cycle_id"),
                "intent_id": payload.get("intent_id"),
                "pnl_net": payload.get("pnl_net"),
                "payload": payload,
            })
        for row in db.execute(
            text("""
                SELECT id, signal_time, figi, side, status, quantity, requested_price, executed_price,
                       commission, pnl_net, payload
                FROM backtest_orders WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            payload = _parse_json(row.get("payload")) or {}
            orders.append({
                "id": int(row["id"]) if row.get("id") is not None else None,
                "time": row.get("signal_time"),
                "ticker": row.get("figi"),
                "side": row.get("side"),
                "status": row.get("status"),
                "quantity": float(row["quantity"]) if row.get("quantity") is not None else 0,
                "price": float(row["executed_price"]) if row.get("executed_price") is not None else None,
                "commission": float(row["commission"]) if row.get("commission") is not None else None,
                "pnl_net": float(row["pnl_net"]) if row.get("pnl_net") is not None else None,
                "kind": payload.get("kind"),
                "reason": payload.get("reason"),
                "cycle_id": payload.get("cycle_id"),
                "intent_id": payload.get("intent_id"),
                "signal_time": payload.get("signal_time"),
                "payload": payload,
            })
        for row in db.execute(
            text("""
                SELECT snapshot_time, cash_balance, equity, positions_payload
                FROM backtest_portfolio_snapshots WHERE run_id = :rid ORDER BY id
            """),
            {"rid": run_id},
        ).mappings().all():
            raw_payload = _parse_json(row.get("positions_payload")) or {}
            holdings, count = _normalize_snapshot_positions(raw_payload)
            snaps.append({
                "snapshot_time": row.get("snapshot_time"),
                "cash": float(row.get("cash_balance") or 0),
                "equity": float(row.get("equity") or 0),
                "positions": holdings,
                "positions_count": count,
                "positions_payload": raw_payload,
            })
    except Exception as exc:
        logger.warning("v2 backtest child load failed run_id=%s: %s", run_id, exc)
    return {"signals": signals, "orders": orders, "portfolio_snapshots": snaps}


def _normalize_snapshot_positions(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Return (holdings list, count) from positions_payload (P1 or legacy int)."""
    if isinstance(payload, list):
        # Very old shape: bare list of holdings.
        holdings = [h for h in payload if isinstance(h, dict)]
        return holdings, len(holdings)
    if not isinstance(payload, dict):
        return [], 0
    positions = payload.get("positions")
    if isinstance(positions, list):
        holdings = [h for h in positions if isinstance(h, dict)]
        count = int(payload.get("positions_count") or len(holdings))
        return holdings, count
    if isinstance(positions, (int, float)):
        return [], int(positions)
    count = payload.get("positions_count")
    if isinstance(count, (int, float)):
        return [], int(count)
    return [], 0


def filter_signals(
    signals: list[dict[str, Any]],
    *,
    status: str | None = None,
    reject_reason: str | None = None,
    ticker: str | None = None,
    cycle_id: str | None = None,
) -> list[dict[str, Any]]:
    out = signals
    if status:
        want = _normalize_signal_status(status)
        out = [
            s for s in out
            if _normalize_signal_status(s.get("status"), was_executed=s.get("was_executed")) == want
        ]
    if reject_reason:
        want_rr = str(reject_reason)
        out = [s for s in out if str(s.get("reject_reason") or "") == want_rr]
    if ticker:
        want_t = str(ticker).upper()
        out = [s for s in out if str(s.get("figi") or s.get("ticker") or "").upper() == want_t]
    if cycle_id:
        want_c = str(cycle_id)
        out = [s for s in out if str(s.get("cycle_id") or "") == want_c]
    return out


def paginate_signals(
    signals: list[dict[str, Any]],
    *,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    total = len(signals)
    lim = max(1, min(int(limit), 1000))
    off = max(0, int(offset))
    return signals[off: off + lim], total



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
                   partial_result, config_snapshot, metrics_summary, execution_model
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
    out["execution_events"] = load_execution_events(db, run_id)
    enrich_run_observability(out)
    return out


def _honest_execution_model_banner(
    stored_em: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Force NEXT_BAR_OPEN honesty; never surface legacy BAR_CLOSE as the fill model."""
    label = "Fills at next bar open"
    look_ahead = False
    if isinstance(stored_em, dict):
        model = str(stored_em.get("model") or stored_em.get("code") or "").upper()
        if model == "NEXT_BAR_OPEN":
            label = str(stored_em.get("label") or label)
            look_ahead = bool(stored_em.get("look_ahead", False))
    return {
        "code": "NEXT_BAR_OPEN",
        "label": label,
        "look_ahead": look_ahead,
    }


def enrich_run_observability(out: dict[str, Any]) -> dict[str, Any]:
    """Attach observability + linked_trade_ids; soft-degrade for legacy runs."""
    payload = out.get("result_payload") if isinstance(out.get("result_payload"), dict) else {}
    signals = list(out.get("signals") or [])
    trades = list((payload or {}).get("trades") or [])
    # Prefer metrics_summary trades (have cycle_id after P0); fall back to orders.
    if not trades and out.get("orders"):
        trades = [
            {
                "id": o.get("id"),
                "cycle_id": o.get("cycle_id"),
                "figi": o.get("ticker") or o.get("figi"),
                "kind": o.get("kind"),
                "intent_id": o.get("intent_id"),
            }
            for o in (out.get("orders") or [])
            if o.get("cycle_id") or o.get("id") is not None
        ]
    _attach_linked_trade_ids(signals, trades)
    # Legacy runs may still store deferred signals after next-open fills.
    promote_deferred_signals_to_filled(
        signals,
        trades=trades,
        execution_events=list(out.get("execution_events") or []),
    )
    out["signals"] = signals

    stored_em = out.get("execution_model") if isinstance(out.get("execution_model"), dict) else None
    # Rewrite dishonest legacy column values on read (BAR_CLOSE → NEXT_BAR_OPEN).
    if stored_em is not None:
        model = str(stored_em.get("model") or stored_em.get("code") or "").upper()
        if model != "NEXT_BAR_OPEN":
            out["execution_model"] = dict(NEXT_BAR_OPEN_EXECUTION_MODEL)
            stored_em = out["execution_model"]

    history_stats = (payload or {}).get("history_stats") if isinstance(payload, dict) else {}
    # Always rebuild status_counts from (possibly promoted) signals so reject-lens
    # «Исполнено» matches trades / filled execution events on legacy runs.
    obs = build_observability(signals, history_stats=history_stats or {})
    obs = {
        **obs,
        "execution_model": _honest_execution_model_banner(stored_em),
    }
    if isinstance(payload, dict):
        payload = {**payload, "observability": obs}
        out["result_payload"] = payload
    out["observability"] = obs
    out["signals_total"] = int(
        (obs or {}).get("signals_logged")
        or len(signals)
        or ((payload or {}).get("history_stats") or {}).get("signals")
        or 0
    )
    return out


def apply_signals_page_to_details(
    out: dict[str, Any],
    *,
    signals_limit: int | None = None,
    signals_offset: int = 0,
    signals_status: str | None = None,
    reject_reason: str | None = None,
) -> dict[str, Any]:
    """Paginate/filter signals on details; omit inline body when total > 5k unless filtered/limited."""
    enrich_run_observability(out)
    all_signals = list(out.get("signals") or [])
    filtered = filter_signals(
        all_signals,
        status=signals_status,
        reject_reason=reject_reason,
    )
    total = len(filtered)
    out["signals_total"] = total

    force_page = total > DETAILS_SIGNALS_INLINE_CAP
    explicit_limit = signals_limit is not None or signals_offset > 0 or signals_status or reject_reason
    if force_page and not explicit_limit:
        # SPEC §10: force paginated /signals when >5k — details returns empty slice + total.
        out["signals"] = []
        out["signals_truncated_inline"] = True
        return out

    lim = 200 if signals_limit is None and force_page else (
        int(signals_limit) if signals_limit is not None else total
    )
    page, _ = paginate_signals(filtered, limit=max(1, lim), offset=signals_offset)
    out["signals"] = page
    out["signals_truncated_inline"] = force_page
    return out


def fetch_db_run_by_id(db: Session, run_id: int) -> dict[str, Any] | None:
    """Worker-side load (no user filter)."""
    row = db.execute(
        text("""
            SELECT id, robot_id, user_id, status, requested_from, requested_to, started_at, finished_at,
                   initial_capital, progress_percent, run_phase, error_message, cancel_requested,
                   partial_result, config_snapshot, metrics_summary, execution_model
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
    execution_model = _parse_json(row.get("execution_model")) if "execution_model" in row else None
    payload = summary if isinstance(summary, dict) else {}
    partial = bool(row.get("partial_result")) if "partial_result" in row else None
    robot_id_raw = row.get("robot_id")
    robot_id = int(robot_id_raw) if robot_id_raw is not None else None
    out = {
        "run_id": int(row["id"]),
        "robot_id": robot_id,
        "bound": robot_id is not None,
        "config_label": _config_label_from_snapshot(config if isinstance(config, dict) else None),
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
        "partial_result": partial,
        "error_message": row.get("error_message"),
        "config_snapshot": config,
        "execution_model": execution_model if isinstance(execution_model, dict) else None,
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
        "observability": payload.get("observability"),
        "fee_summary": payload.get("fee_summary"),
        "narrative": list(payload.get("narrative") or []),
        "execution_events": [],
        "signals_total": int(
            (payload.get("observability") or {}).get("signals_logged")
            or (payload.get("history_stats") or {}).get("signals")
            or 0
        ),
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
        fee = p.get("fee_summary") if isinstance(p.get("fee_summary"), dict) else (
            row.get("fee_summary") if isinstance(row.get("fee_summary"), dict) else {}
        )
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
            "commission_total": fee.get("commission_total"),
            "funding_total": fee.get("funding_total"),
            "funding_events": fee.get("funding_events"),
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
