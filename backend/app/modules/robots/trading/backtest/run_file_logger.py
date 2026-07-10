"""
Per-run file logging for history-backtest.

Layout (default repo root):
  logs/backtest/DD.MM.YYYY/run_<id>/backtest.log
  logs/backtest/DD.MM.YYYY/run_<id>/meta.json
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings

_current_run_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "backtest_run_id",
    default=None,
)
_sessions: Dict[int, "_BacktestRunLogSession"] = {}
_lock = threading.Lock()

_MODULE_LOGGER = logging.getLogger(__name__)

_LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _resolve_run_dir(run_id: int, started_at: Optional[datetime] = None) -> Optional[Path]:
    run_dir = find_backtest_run_dir(run_id)
    if run_dir is not None:
        return run_dir
    if started_at is not None:
        return backtest_run_dir(run_id, started_at=started_at)
    return None


def append_backtest_run_log_line(
    run_id: int,
    level: int,
    msg: str,
    *args: Any,
    started_at: Optional[datetime] = None,
) -> None:
    """Append one line to backtest.log without an in-memory session (reconcile / recovery)."""
    run_dir = _resolve_run_dir(run_id, started_at=started_at)
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "backtest.log"
    try:
        text_msg = msg % args if args else msg
    except Exception:
        text_msg = str(msg)
    now = datetime.now()
    msecs = int(now.microsecond / 1000)
    level_name = logging.getLevelName(level)
    line = f"[{now.strftime(_LOG_DATE_FMT)}.{msecs:03d}] [{level_name}] {text_msg}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as ex:
        _MODULE_LOGGER.warning("backtest log append failed run_id=%s: %s", run_id, ex)


def _append_log_end_block(
    run_id: int,
    *,
    started_at: Optional[datetime],
    status: str,
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    append_backtest_run_log_line(
        run_id,
        logging.INFO,
        "=== BACKTEST RUN %s END status=%s ===",
        run_id,
        status,
        started_at=started_at,
    )
    if summary:
        for key, val in summary.items():
            append_backtest_run_log_line(
                run_id,
                logging.INFO,
                "RESULT %s=%s",
                key,
                val,
                started_at=started_at,
            )
    if error:
        append_backtest_run_log_line(
            run_id,
            logging.ERROR,
            "ERROR %s",
            error,
            started_at=started_at,
        )


def _repo_root() -> Path:
    # .../backend/app/modules/robots/trading/backtest/run_file_logger.py -> repo root
    return Path(__file__).resolve().parents[6]


def resolve_backtest_log_root() -> Path:
    raw = getattr(settings, "BACKTEST_LOG_DIR", None)
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return _repo_root() / "logs" / "backtest"


def backtest_run_dir(run_id: int, started_at: Optional[datetime] = None) -> Path:
    dt = started_at or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    date_folder = local.strftime("%d.%m.%Y")
    return resolve_backtest_log_root() / date_folder / f"run_{int(run_id)}"


def find_backtest_run_dir(run_id: int) -> Optional[Path]:
    """Locate run_<id> folder under any date subfolder (for reconcile after worker loss)."""
    root = resolve_backtest_log_root()
    if not root.is_dir():
        return None
    suffix = f"run_{int(run_id)}"
    try:
        for date_dir in sorted(root.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            candidate = date_dir / suffix
            if candidate.is_dir():
                return candidate
    except OSError as ex:
        _MODULE_LOGGER.warning("backtest run dir scan failed run_id=%s: %s", run_id, ex)
    return None


class _BacktestRunLogSession:
    def __init__(
        self,
        run_id: int,
        *,
        run_dir: Path,
        meta: Dict[str, Any],
    ) -> None:
        self.run_id = int(run_id)
        self.run_dir = run_dir
        self.meta = dict(meta)
        self._file_logger = logging.getLogger(f"robots.backtest.run.{self.run_id}")
        self._handler: Optional[logging.FileHandler] = None
        self._opened = False

    def open(self) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.run_dir / "backtest.log"
        formatter = logging.Formatter(
            "[%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self._file_logger.handlers.clear()
        self._file_logger.addHandler(handler)
        self._file_logger.setLevel(logging.DEBUG)
        self._file_logger.propagate = False
        self._handler = handler
        self._opened = True

        meta_path = self.run_dir / "meta.json"
        meta_path.write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        self.info("=== BACKTEST RUN %s START ===", self.run_id)
        self.info("log_dir=%s", str(self.run_dir))
        return log_path

    def _log(self, level: int, msg: str, *args: Any) -> None:
        if not self._opened:
            return
        self._file_logger.log(level, msg, *args)
        if level >= logging.WARNING:
            _MODULE_LOGGER.log(level, "[run_id=%s] " + msg, self.run_id, *args)

    def debug(self, msg: str, *args: Any) -> None:
        self._log(logging.DEBUG, msg, *args)

    def info(self, msg: str, *args: Any) -> None:
        self._log(logging.INFO, msg, *args)

    def warning(self, msg: str, *args: Any) -> None:
        self._log(logging.WARNING, msg, *args)

    def error(self, msg: str, *args: Any) -> None:
        self._log(logging.ERROR, msg, *args)

    def exception(self, msg: str, *args: Any) -> None:
        if not self._opened:
            return
        self._file_logger.exception(msg, *args)
        _MODULE_LOGGER.exception("[run_id=%s] " + msg, self.run_id, *args)

    def close(
        self,
        *,
        status: str,
        summary: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if not self._opened:
            return
        self.info("=== BACKTEST RUN %s END status=%s ===", self.run_id, status)
        if summary:
            for key, val in summary.items():
                self.info("RESULT %s=%s", key, val)
        if error:
            self.error("ERROR %s", error)
        if self._handler:
            self._handler.flush()
            self._handler.close()
            self._file_logger.removeHandler(self._handler)
            self._handler = None
        self._opened = False

        summary_path = self.run_dir / "summary.json"
        payload = {
            "run_id": self.run_id,
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary or {},
            "error": error,
        }
        try:
            summary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as ex:
            _MODULE_LOGGER.warning("backtest summary write failed run_id=%s: %s", self.run_id, ex)


def _session_for(run_id: Optional[int] = None) -> Optional[_BacktestRunLogSession]:
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is None:
        return None
    with _lock:
        return _sessions.get(int(rid))


def open_backtest_run_log(
    run_id: int,
    *,
    started_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    rid = int(run_id)
    run_dir = backtest_run_dir(rid, started_at=started_at)
    session = _BacktestRunLogSession(rid, run_dir=run_dir, meta=meta or {"run_id": rid})
    log_path = session.open()
    with _lock:
        old = _sessions.get(rid)
        if old is not None:
            old.close(status="replaced", summary=None)
        _sessions[rid] = session
    _current_run_id.set(rid)
    return log_path


def ensure_backtest_run_log(
    run_id: int,
    *,
    started_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Return existing session log path for run_id, or open a new one.

    Unlike open_backtest_run_log(), this avoids replacing an active session.
    """
    rid = int(run_id)
    with _lock:
        existing = _sessions.get(rid)
        if existing is not None:
            _current_run_id.set(rid)
            return existing.run_dir / "backtest.log"
    return open_backtest_run_log(rid, started_at=started_at, meta=meta)


def read_backtest_run_summary_on_disk(
    run_id: int,
    *,
    started_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Read summary.json written by close_backtest_run_log (if present)."""
    run_dir = backtest_run_dir(run_id, started_at=started_at) if started_at else find_backtest_run_dir(run_id)
    if run_dir is None:
        return None
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        return None
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        _MODULE_LOGGER.warning("backtest summary read failed run_id=%s: %s", run_id, ex)
        return None
    return data if isinstance(data, dict) else None


def write_backtest_run_summary_on_disk(
    run_id: int,
    *,
    started_at: Optional[datetime] = None,
    status: str,
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Write summary.json without an active log session (e.g. after worker loss)."""
    run_dir = backtest_run_dir(run_id, started_at=started_at) if started_at else find_backtest_run_dir(run_id)
    if run_dir is None:
        run_dir = backtest_run_dir(run_id, started_at=started_at)
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"
    payload = {
        "run_id": int(run_id),
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary or {},
        "error": error,
    }
    try:
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as ex:
        _MODULE_LOGGER.warning("backtest summary write failed run_id=%s: %s", run_id, ex)


def close_backtest_run_log(
    run_id: int,
    *,
    status: str,
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> None:
    rid = int(run_id)
    with _lock:
        session = _sessions.pop(rid, None)
    if session is None:
        _append_log_end_block(
            rid,
            started_at=started_at,
            status=status,
            summary=summary,
            error=error,
        )
        write_backtest_run_summary_on_disk(
            rid,
            started_at=started_at,
            status=status,
            summary=summary,
            error=error,
        )
        if _current_run_id.get() == rid:
            _current_run_id.set(None)
        return
    session.close(status=status, summary=summary, error=error)
    if _current_run_id.get() == rid:
        _current_run_id.set(None)


def log_backtest_run_info(msg: str, *args: Any, run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if session:
        session.info(msg, *args)
        return
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is not None:
        append_backtest_run_log_line(rid, logging.INFO, msg, *args)


def log_backtest_run_debug(msg: str, *args: Any, run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if session:
        session.debug(msg, *args)
        return
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is not None:
        append_backtest_run_log_line(rid, logging.DEBUG, msg, *args)


def log_backtest_run_warning(msg: str, *args: Any, run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if session:
        session.warning(msg, *args)
        return
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is not None:
        append_backtest_run_log_line(rid, logging.WARNING, msg, *args)


def log_backtest_run_error(msg: str, *args: Any, run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if session:
        session.error(msg, *args)
        return
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is not None:
        append_backtest_run_log_line(rid, logging.ERROR, msg, *args)


def log_backtest_run_exception(msg: str, *args: Any, run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if session:
        session.exception(msg, *args)
        return
    rid = int(run_id) if run_id is not None else _current_run_id.get()
    if rid is not None:
        append_backtest_run_log_line(rid, logging.ERROR, msg, *args)
        append_backtest_run_log_line(rid, logging.ERROR, traceback.format_exc(), started_at=None)
    else:
        _MODULE_LOGGER.exception(msg, *args)


def log_backtest_run_phase(
    run_id: int,
    phase: str,
    *,
    phase_units_done: int = 0,
    phase_units_total: int = 0,
    progress_percent: Optional[float] = None,
    eta_seconds: Optional[int] = None,
) -> None:
    session = _session_for(run_id)
    parts = [f"PHASE {phase}"]
    if phase_units_total > 0:
        parts.append(f"units={phase_units_done}/{phase_units_total}")
    if progress_percent is not None:
        parts.append(f"progress={progress_percent:.2f}%")
    if eta_seconds is not None:
        parts.append(f"eta={eta_seconds}s")
    line = " | ".join(parts)
    if session:
        session.info(line)
        return
    append_backtest_run_log_line(run_id, logging.INFO, line)


def log_backtest_run_traceback(run_id: Optional[int] = None) -> None:
    session = _session_for(run_id)
    if not session:
        return
    session.error(traceback.format_exc())


__all__ = [
    "append_backtest_run_log_line",
    "backtest_run_dir",
    "close_backtest_run_log",
    "ensure_backtest_run_log",
    "find_backtest_run_dir",
    "log_backtest_run_debug",
    "log_backtest_run_error",
    "log_backtest_run_exception",
    "log_backtest_run_info",
    "log_backtest_run_phase",
    "log_backtest_run_warning",
    "open_backtest_run_log",
    "read_backtest_run_summary_on_disk",
    "resolve_backtest_log_root",
    "write_backtest_run_summary_on_disk",
]
