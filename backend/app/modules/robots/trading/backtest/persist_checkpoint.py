"""On-disk checkpoint so backtest persist can resume after DB connectivity loss."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.modules.robots.trading.backtest.run_file_logger import (
    backtest_run_dir,
    find_backtest_run_dir,
)
from app.modules.robots.trading.backtest.types import BacktestResult

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1
CHECKPOINT_FILENAME = "persist_checkpoint.json"


def backtest_result_to_dict(res: BacktestResult) -> Dict[str, Any]:
    return {
        "initial_capital": float(res.initial_capital),
        "final_equity": float(res.final_equity),
        "total_return_percent": float(res.total_return_percent),
        "max_drawdown_percent": res.max_drawdown_percent,
        "trades": list(res.trades or []),
        "equity_curve": list(res.equity_curve or []),
        "signals": list(res.signals or []),
        "daily_positions": list(res.daily_positions or []),
        "cancelled": bool(getattr(res, "cancelled", False)),
        "fee_summary": dict(getattr(res, "fee_summary", None) or {}),
        "margin_summary": dict(getattr(res, "margin_summary", None) or {}),
    }


def backtest_result_from_dict(data: Dict[str, Any]) -> BacktestResult:
    return BacktestResult(
        initial_capital=float(data.get("initial_capital") or 0),
        final_equity=float(data.get("final_equity") or 0),
        total_return_percent=float(data.get("total_return_percent") or 0),
        max_drawdown_percent=data.get("max_drawdown_percent"),
        trades=list(data.get("trades") or []),
        equity_curve=list(data.get("equity_curve") or []),
        signals=list(data.get("signals") or []),
        daily_positions=list(data.get("daily_positions") or []),
        cancelled=bool(data.get("cancelled")),
        fee_summary=dict(data.get("fee_summary") or {}),
        margin_summary=dict(data.get("margin_summary") or {}),
    )


def _dt_to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(value)


def build_persist_checkpoint_payload(
    *,
    run_id: int,
    run_started_at: datetime,
    robot_pk: Optional[int],
    bt_run_id: Optional[int],
    slippage_pct: float,
    is_crypto_backtest: bool,
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    skip_heavy_persist: bool,
    pipeline_user_cancelled: bool,
    td_total: int,
    config: Dict[str, Any],
    res: BacktestResult,
    decisions_rows: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "version": CHECKPOINT_VERSION,
        "run_id": int(run_id),
        "run_started_at": _dt_to_iso(run_started_at),
        "robot_pk": robot_pk,
        "bt_run_id": bt_run_id,
        "slippage_pct": float(slippage_pct),
        "is_crypto_backtest": bool(is_crypto_backtest),
        "requested_from_utc": _dt_to_iso(requested_from_utc),
        "requested_to_utc": _dt_to_iso(requested_to_utc),
        "skip_heavy_persist": bool(skip_heavy_persist),
        "pipeline_user_cancelled": bool(pipeline_user_cancelled),
        "td_total": int(td_total),
        "config": dict(config or {}),
        "res": backtest_result_to_dict(res),
        "decisions_rows": list(decisions_rows or []),
        "result": dict(result or {}),
    }


def _parse_iso_dt(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def checkpoint_run_started_at(checkpoint: Dict[str, Any]) -> datetime:
    return _parse_iso_dt(checkpoint.get("run_started_at"))


def write_persist_checkpoint(
    run_id: int,
    started_at: datetime,
    payload: Dict[str, Any],
) -> Path:
    run_dir = backtest_run_dir(run_id, started_at=started_at)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / CHECKPOINT_FILENAME
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("persist checkpoint written run_id=%s path=%s", run_id, path)
    return path


def read_persist_checkpoint(
    run_id: int,
    *,
    started_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    run_dir = backtest_run_dir(run_id, started_at=started_at) if started_at else find_backtest_run_dir(run_id)
    if run_dir is None:
        return None
    path = run_dir / CHECKPOINT_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        logger.warning("persist checkpoint read failed run_id=%s: %s", run_id, ex)
        return None
    return data if isinstance(data, dict) else None


def find_persist_checkpoint(run_id: int) -> Optional[Tuple[Dict[str, Any], datetime]]:
    cp = read_persist_checkpoint(run_id)
    if not cp:
        return None
    try:
        started = checkpoint_run_started_at(cp)
    except Exception:
        return None
    return cp, started


def persist_checkpoint_exists(run_id: int) -> bool:
    run_dir = find_backtest_run_dir(run_id)
    if run_dir is None:
        return False
    return (run_dir / CHECKPOINT_FILENAME).is_file()


def delete_persist_checkpoint(run_id: int, started_at: Optional[datetime] = None) -> None:
    run_dir = backtest_run_dir(run_id, started_at=started_at) if started_at else find_backtest_run_dir(run_id)
    if run_dir is None:
        return
    path = run_dir / CHECKPOINT_FILENAME
    try:
        path.unlink(missing_ok=True)
    except OSError as ex:
        logger.warning("persist checkpoint delete failed run_id=%s: %s", run_id, ex)
