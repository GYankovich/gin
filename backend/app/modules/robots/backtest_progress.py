"""Progress % and ETA for history-backtest (phase weights + online rate)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

from app.core.config import settings

# Доли фаз в общем progress_percent (сумма = 100).
PHASE_WEIGHTS: Dict[str, float] = {
    "fetching_market_data": 4.0,
    "prefetching_market_snapshots": 12.0,
    "scoring": 36.0,
    "prefetching_candles": 10.0,
    "loading_candles": 8.0,
    "simulating": 28.0,
    "persisting": 2.0,
}

PHASE_ORDER: Tuple[str, ...] = (
    "fetching_market_data",
    "prefetching_market_snapshots",
    "scoring",
    "prefetching_candles",
    "loading_candles",
    "simulating",
    "persisting",
)

PHASE_LABELS_RU: Dict[str, str] = {
    "fetching_market_data": "Подготовка",
    "prefetching_market_snapshots": "Снимки MOEX",
    "prefetching_crypto_market": "Кэш ByBit (D1 + funding)",
    "scoring": "Отбор бумаг",
    "prefetching_candles": "Кэш свечей MOEX",
    "loading_candles": "Загрузка свечей",
    "simulating": "Симуляция",
    "persisting": "Сохранение",
    "persist_pending": "Ожидание БД (сохранение)",
    "cancelled": "Отмена",
}

# Оценка «хвоста» фаз без измерений (секунды).
_PHASE_PRIOR_SEC: Dict[str, float] = {
    "fetching_market_data": 3.0,
    "prefetching_market_snapshots": 4.0,
    "prefetching_crypto_market": 120.0,
    "scoring": 5.0,
    "prefetching_candles": 10.0,
    "loading_candles": 6.0,
    "simulating": 12.0,
    "persisting": 6.0,
}


@dataclass
class _Runtime:
    phase: str = ""
    phase_started_mono: float = field(default_factory=time.monotonic)
    ema_sec_per_unit: float = 0.0


_LOCK = threading.Lock()
_RUNTIME: Dict[int, _Runtime] = {}
# Время последнего успешного persist_backtest_progress (monotonic) — для scoring-timeout.
_LAST_PROGRESS_TOUCH: Dict[int, float] = {}


def clear_backtest_progress_runtime(run_id: int) -> None:
    with _LOCK:
        _RUNTIME.pop(int(run_id), None)
        _LAST_PROGRESS_TOUCH.pop(int(run_id), None)


def scoring_progress_idle_seconds(run_id: int) -> Optional[float]:
    """Секунды с последнего обновления прогресса в БД; None если ещё не было flush."""
    with _LOCK:
        t0 = _LAST_PROGRESS_TOUCH.get(int(run_id))
    if t0 is None:
        return None
    return max(0.0, time.monotonic() - t0)


def touch_backtest_progress_runtime(run_id: int) -> None:
    """Помечает активность воркера (без записи в БД)."""
    with _LOCK:
        _LAST_PROGRESS_TOUCH[int(run_id)] = time.monotonic()


def begin_backtest_phase(run_id: int, phase: str) -> None:
    with _LOCK:
        _RUNTIME[int(run_id)] = _Runtime(phase=str(phase), phase_started_mono=time.monotonic())
    try:
        from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_phase

        log_backtest_run_phase(int(run_id), str(phase))
    except Exception:
        pass


def _normalize_progress_phase(phase: str) -> str:
    """Map crypto prefetch to the same progress slot as MOEX market snapshots."""
    p = str(phase or "").strip().lower()
    if p == "prefetching_crypto_market":
        return "prefetching_market_snapshots"
    return p


def _phase_index(phase: str) -> int:
    p = _normalize_progress_phase(str(phase or "").strip().lower())
    try:
        return PHASE_ORDER.index(p)
    except ValueError:
        return -1


def _phase_fraction(
    phase: str,
    *,
    phase_units_done: int,
    phase_units_total: int,
    trade_dates_total: Optional[int],
    trade_dates_remaining: Optional[int],
) -> float:
    if phase_units_total > 0:
        return min(1.0, max(0.0, float(phase_units_done) / float(phase_units_total)))
    if trade_dates_total and trade_dates_total > 0 and trade_dates_remaining is not None:
        done = max(0, int(trade_dates_total) - int(trade_dates_remaining))
        return min(1.0, max(0.0, float(done) / float(trade_dates_total)))
    if phase in ("persisting",):
        return 0.5
    return 0.0


def compute_progress_percent(
    run_phase: Optional[str],
    *,
    phase_units_done: int = 0,
    phase_units_total: int = 0,
    trade_dates_total: Optional[int] = None,
    trade_dates_remaining: Optional[int] = None,
) -> float:
    raw_phase = str(run_phase or "").strip().lower() or "fetching_market_data"
    phase = _normalize_progress_phase(raw_phase)
    idx = _phase_index(phase)
    completed = sum(PHASE_WEIGHTS.get(p, 0.0) for p in PHASE_ORDER[: max(0, idx)])
    weight = PHASE_WEIGHTS.get(phase, 5.0)
    frac = _phase_fraction(
        phase,
        phase_units_done=phase_units_done,
        phase_units_total=phase_units_total,
        trade_dates_total=trade_dates_total,
        trade_dates_remaining=trade_dates_remaining,
    )
    pct = completed + weight * frac
    if phase in ("cancelled", "cancelled_simulation"):
        return min(99.9, pct)
    return round(min(99.9, max(0.0, pct)), 2)


def compute_eta_seconds(
    run_id: int,
    run_phase: Optional[str],
    *,
    progress_percent: float,
    phase_units_done: int,
    phase_units_total: int,
    trade_dates_total: Optional[int],
    trade_dates_remaining: Optional[int],
    started_at: Optional[datetime],
) -> Tuple[Optional[int], str]:
    phase = str(run_phase or "").strip().lower()
    if phase in ("cancelled", "cancelled_simulation", "persisting"):
        return 0 if progress_percent >= 99 else 5, "high"

    now = datetime.now(timezone.utc)
    if started_at is not None:
        sa = started_at
        if getattr(sa, "tzinfo", None) is None:
            sa = sa.replace(tzinfo=timezone.utc)
        elapsed_total = max(0.0, (now - sa.astimezone(timezone.utc)).total_seconds())
    else:
        elapsed_total = 0.0

    if progress_percent >= 8.0 and elapsed_total > 3.0:
        remaining = elapsed_total * (100.0 - progress_percent) / max(progress_percent, 1.0)
        conf = "high" if progress_percent >= 25.0 else "medium"
        return int(max(0.0, remaining)), conf

    with _LOCK:
        rt = _RUNTIME.get(int(run_id))

    units_done = phase_units_done
    units_total = phase_units_total
    if units_total <= 0 and trade_dates_total and trade_dates_remaining is not None:
        units_done = max(0, int(trade_dates_total) - int(trade_dates_remaining))
        units_total = int(trade_dates_total)

    if units_total > 0 and units_done > 0 and rt is not None:
        elapsed_phase = max(0.05, time.monotonic() - rt.phase_started_mono)
        alpha = 0.35
        rate = elapsed_phase / float(units_done)
        rt.ema_sec_per_unit = alpha * rate + (1.0 - alpha) * (rt.ema_sec_per_unit or rate)
        eta_phase = rt.ema_sec_per_unit * max(0, units_total - units_done)
        tail = 0.0
        idx = _phase_index(phase)
        for p in PHASE_ORDER[idx + 1 :]:
            tail += _PHASE_PRIOR_SEC.get(p, 5.0)
        conf = "medium" if units_done >= 3 else "low"
        return int(max(0.0, eta_phase + tail)), conf

    prior = sum(_PHASE_PRIOR_SEC.get(p, 5.0) for p in PHASE_ORDER[_phase_index(phase) :])
    if trade_dates_total:
        prior *= max(1.0, float(trade_dates_total) / 10.0)
    return int(max(30.0, prior)), "low"


def phase_label_ru(run_phase: Optional[str]) -> str:
    p = str(run_phase or "").strip().lower()
    return PHASE_LABELS_RU.get(p, str(run_phase or "—"))


def persist_backtest_progress(
    bind: Any,
    run_id: int,
    *,
    run_phase: str,
    phase_units_done: int = 0,
    phase_units_total: int = 0,
    trade_dates_total: Optional[int] = None,
    trade_dates_remaining: Optional[int] = None,
    current_trade_date: Optional[date] = None,
    started_at: Optional[datetime] = None,
) -> None:
    phase_key = str(run_phase or "").strip().lower()
    with _LOCK:
        rt = _RUNTIME.get(int(run_id))
        if rt is None or rt.phase != phase_key:
            _RUNTIME[int(run_id)] = _Runtime(phase=phase_key, phase_started_mono=time.monotonic())
    pct = compute_progress_percent(
        run_phase,
        phase_units_done=phase_units_done,
        phase_units_total=phase_units_total,
        trade_dates_total=trade_dates_total,
        trade_dates_remaining=trade_dates_remaining,
    )
    eta, conf = compute_eta_seconds(
        run_id,
        run_phase,
        progress_percent=pct,
        phase_units_done=phase_units_done,
        phase_units_total=phase_units_total,
        trade_dates_total=trade_dates_total,
        trade_dates_remaining=trade_dates_remaining,
        started_at=started_at,
    )
    params: Dict[str, Any] = {
        "rid": int(run_id),
        "rp": run_phase,
        "pp": pct,
        "eta": eta,
        "conf": conf,
        "ud": int(phase_units_done),
        "ut": int(phase_units_total),
        "cd": current_trade_date,
        "rem": trade_dates_remaining,
        "td": trade_dates_total,
    }
    with bind.connect() as conn:
        if current_trade_date is not None and trade_dates_remaining is not None:
            conn.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET run_phase = :rp,
                        progress_percent = :pp,
                        eta_seconds = :eta,
                        eta_confidence = :conf,
                        phase_units_done = :ud,
                        phase_units_total = :ut,
                        current_trade_date = :cd,
                        trade_dates_remaining = :rem
                    WHERE id = :rid
                    """
                ),
                params,
            )
        elif trade_dates_total is not None and trade_dates_remaining is not None:
            conn.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET run_phase = :rp,
                        progress_percent = :pp,
                        eta_seconds = :eta,
                        eta_confidence = :conf,
                        phase_units_done = :ud,
                        phase_units_total = :ut,
                        trade_dates_total = :td,
                        trade_dates_remaining = :rem
                    WHERE id = :rid
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    f"""
                    UPDATE backtest_runs
                    SET run_phase = :rp,
                        progress_percent = :pp,
                        eta_seconds = :eta,
                        eta_confidence = :conf,
                        phase_units_done = :ud,
                        phase_units_total = :ut
                    WHERE id = :rid
                    """
                ),
                params,
            )
        conn.commit()
    with _LOCK:
        _LAST_PROGRESS_TOUCH[int(run_id)] = time.monotonic()
    try:
        from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_phase

        log_backtest_run_phase(
            int(run_id),
            phase_key,
            phase_units_done=phase_units_done,
            phase_units_total=phase_units_total,
            progress_percent=pct,
            eta_seconds=eta,
        )
    except Exception:
        pass


def progress_snapshot_from_row(row: Any) -> Dict[str, Any]:
    """Собрать поля прогресса из строки SELECT (см. get_backtest_run_status)."""
    if row is None:
        return {}
    # Индексы согласованы с SELECT в service.get_backtest_run_status
    return {
        "progress_percent": float(row[0]) if row[0] is not None else None,
        "eta_seconds": int(row[1]) if row[1] is not None else None,
        "eta_confidence": str(row[2]) if row[2] is not None else None,
        "phase_units_done": int(row[3]) if row[3] is not None else None,
        "phase_units_total": int(row[4]) if row[4] is not None else None,
        "run_phase": str(row[5]) if row[5] is not None else None,
        "phase_label": phase_label_ru(row[5] if len(row) > 5 else None),
        "current_trade_date": row[6],
        "trade_dates_total": int(row[7]) if row[7] is not None else None,
        "trade_dates_remaining": int(row[8]) if row[8] is not None else None,
        "cancel_requested": bool(row[9]) if row[9] is not None else None,
    }
