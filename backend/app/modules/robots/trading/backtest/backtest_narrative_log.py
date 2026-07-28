"""Human-readable step-by-step narrative for backtest run logs (backtest.log)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import date
from typing import Iterable, Iterator, Optional

from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_info

_MAX_SYMBOLS_IN_RESULT = 25

_active: contextvars.ContextVar[Optional["_NarrativeState"]] = contextvars.ContextVar(
    "backtest_narrative",
    default=None,
)


def format_trade_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def format_symbol_list(symbols: Iterable[str], *, limit: int = _MAX_SYMBOLS_IN_RESULT) -> str:
    items = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not items:
        return "(пусто)"
    if len(items) <= limit:
        return ", ".join(items)
    head = ", ".join(items[:limit])
    return f"{head} … (+{len(items) - limit} ещё, всего {len(items)})"


def format_candle_prefetch_result(stats: object) -> str:
    """Readable summary for CandlePrefetchStats."""
    interval = str(getattr(stats, "interval_label", "") or "?")
    total = int(getattr(stats, "total_tickers", 0) or 0)
    hits = int(getattr(stats, "cache_full_hits", 0) or 0)
    fetched = int(getattr(stats, "fetched_tickers", 0) or 0)
    candles = int(getattr(stats, "fetched_candles", 0) or 0)
    errors = int(getattr(stats, "api_errors", 0) or 0)
    parts = [
        f"интервал {interval}",
        f"символов {total}",
        f"кэш полный у {hits}",
        f"догружено тикеров {fetched}",
        f"свечей upsert {candles}",
    ]
    if errors:
        parts.append(f"ошибок API {errors}")
    return "; ".join(parts)


def format_funding_prefetch_result(stats: object) -> str:
    total = int(getattr(stats, "total_symbols", 0) or 0)
    hits = int(getattr(stats, "cache_full_hits", 0) or 0)
    fetched = int(getattr(stats, "fetched_symbols", 0) or 0)
    rows = int(getattr(stats, "fetched_rows", 0) or 0)
    errors = int(getattr(stats, "api_errors", 0) or 0)
    parts = [
        f"символов {total}",
        f"кэш полный у {hits}",
        f"догружено {fetched}",
        f"строк funding {rows}",
    ]
    if errors:
        parts.append(f"ошибок API {errors}")
    return "; ".join(parts)


class _NarrativeState:
    __slots__ = ("run_id", "step", "sub")

    def __init__(self, run_id: Optional[int]) -> None:
        self.run_id = run_id
        self.step = 0
        self.sub = 0


def _state() -> Optional[_NarrativeState]:
    return _active.get()


@contextmanager
def backtest_narrative(run_id: Optional[int] = None) -> Iterator[None]:
    """Activate narrative logging for nested prefetch/scoring calls."""
    st = _NarrativeState(run_id)
    token = _active.set(st)
    try:
        yield
    finally:
        _active.reset(token)


def narrative_section(title: str, *, run_id: Optional[int] = None) -> None:
    rid = run_id if run_id is not None else (_state().run_id if _state() else None)
    log_backtest_run_info("── %s ──", title, run_id=rid)


def narrative_step(title: str, *, run_id: Optional[int] = None) -> int:
    st = _state()
    rid = run_id if run_id is not None else (st.run_id if st else None)
    if st is None:
        log_backtest_run_info("Шаг: %s", title, run_id=rid)
        return 0
    st.step += 1
    st.sub = 0
    log_backtest_run_info("Шаг %s: %s", st.step, title, run_id=rid)
    return st.step


def narrative_sub(text: str, *, run_id: Optional[int] = None) -> None:
    st = _state()
    rid = run_id if run_id is not None else (st.run_id if st else None)
    if st is None:
        log_backtest_run_info("  • %s", text, run_id=rid)
        return
    st.sub += 1
    log_backtest_run_info("  %s.%s. %s", st.step, st.sub, text, run_id=rid)


def narrative_result(text: str, *, run_id: Optional[int] = None) -> None:
    st = _state()
    rid = run_id if run_id is not None else (st.run_id if st else None)
    log_backtest_run_info("  Результат: %s", text, run_id=rid)


__all__ = [
    "backtest_narrative",
    "format_candle_prefetch_result",
    "format_funding_prefetch_result",
    "format_symbol_list",
    "format_trade_date",
    "narrative_result",
    "narrative_section",
    "narrative_step",
    "narrative_sub",
]
