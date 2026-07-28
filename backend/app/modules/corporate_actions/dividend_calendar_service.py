"""Read-only dividend calendar for robots and backtests (DB only)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings


@dataclass(frozen=True)
class DividendExclusionPolicy:
    """Mirrors pipeline / strategy UI: strict ex-day + optional pre-ex window (weekdays)."""

    strict_exclude_on_ex_date: bool = True
    exclude_weekdays_before_ex: int = 0


def policy_from_robot_config(config: dict) -> DividendExclusionPolicy:
    raw = (
        (config.get("pipeline") or {}).get("dividend_calendar")
        or config.get("dividend_calendar")
        or {}
    )
    n = int(raw.get("exclude_sessions_before_ex", 0) or 0)
    strict = bool(raw.get("strict_ex_day_exclude", True))
    return DividendExclusionPolicy(strict_exclude_on_ex_date=strict, exclude_weekdays_before_ex=max(0, n))


def _weekday_sessions_strictly_before(trade_date: date, ex_date: date) -> int:
    """Count Mon–Fri days d with trade_date < d < ex_date."""
    n = 0
    cur = trade_date
    while True:
        cur = cur.fromordinal(cur.toordinal() + 1)
        if cur >= ex_date:
            break
        if cur.weekday() < 5:
            n += 1
    return n


class DividendCalendarService:
    def __init__(self, db: Session):
        self._db = db
        self._schema = settings.DB_SCHEMA

    def exclusion_reason_for_day(
            self,
            *,
            ticker: str,
            trade_date: date,
            policy: DividendExclusionPolicy,
    ) -> Optional[str]:
        """
        Returns a stable machine reason if the ticker must be excluded on trade_date, else None.
        Reads only equity_dividend_events.
        """
        tk = ticker.strip().upper()
        if not tk:
            return None
        lo = date.fromordinal(trade_date.toordinal() - 450)
        hi = date.fromordinal(trade_date.toordinal() + 450)
        rows = self._db.execute(
            text(f"""
                SELECT ex_date
                FROM {self._schema}.equity_dividend_events
                WHERE ticker = :ticker
                  AND ex_date > :lo
                  AND ex_date <= :hi
            """),
            {"ticker": tk, "lo": lo, "hi": hi},
        ).fetchall()
        for (ex_d,) in rows:
            if not isinstance(ex_d, date):
                continue
            if policy.strict_exclude_on_ex_date and trade_date == ex_d:
                return "dividend_ex_date"
            if policy.exclude_weekdays_before_ex > 0 and trade_date < ex_d:
                gap = _weekday_sessions_strictly_before(trade_date, ex_d)
                if 0 < gap <= policy.exclude_weekdays_before_ex:
                    return "dividend_pre_ex_window"
        return None

    def preload_exclusion_index(
            self,
            tickers: List[str],
            from_d: date,
            to_d: date,
    ) -> Dict[str, List[date]]:
        """Один запрос на все тикеры диапазона — вместо N×M запросов в цикле scoring."""
        uniq = sorted({str(t).strip().upper() for t in tickers if t})
        if not uniq:
            return {}
        lo = date.fromordinal(min(from_d, to_d).toordinal() - 450)
        hi = date.fromordinal(max(from_d, to_d).toordinal() + 450)
        rows = self._db.execute(
            text(f"""
                SELECT ticker, ex_date
                FROM {self._schema}.equity_dividend_events
                WHERE ticker = ANY(:tickers)
                  AND ex_date > :lo
                  AND ex_date <= :hi
                ORDER BY ticker, ex_date
            """),
            {"tickers": uniq, "lo": lo, "hi": hi},
        ).fetchall()
        out: Dict[str, List[date]] = {t: [] for t in uniq}
        for tk, ex_d in rows:
            if isinstance(ex_d, date):
                out.setdefault(str(tk).upper(), []).append(ex_d)
        return out

    def exclusion_reason_for_day_cached(
            self,
            *,
            ticker: str,
            trade_date: date,
            policy: DividendExclusionPolicy,
            ex_dates: Optional[List[date]] = None,
    ) -> Optional[str]:
        tk = ticker.strip().upper()
        if not tk:
            return None
        dates = ex_dates if ex_dates is not None else []
        for ex_d in dates:
            if policy.strict_exclude_on_ex_date and trade_date == ex_d:
                return "dividend_ex_date"
            if policy.exclude_weekdays_before_ex > 0 and trade_date < ex_d:
                gap = _weekday_sessions_strictly_before(trade_date, ex_d)
                if 0 < gap <= policy.exclude_weekdays_before_ex:
                    return "dividend_pre_ex_window"
        return None

    def list_upcoming(self, ticker: str, from_d: date, to_d: date) -> List[Tuple[date, Optional[float]]]:
        tk = ticker.strip().upper()
        rows = self._db.execute(
            text(f"""
                SELECT ex_date, amount_per_share
                FROM {self._schema}.equity_dividend_events
                WHERE ticker = :ticker AND ex_date >= :f AND ex_date <= :t
                ORDER BY ex_date ASC
            """),
            {"ticker": tk, "f": from_d, "t": to_d},
        ).fetchall()
        out: List[Tuple[date, Optional[float]]] = []
        for ex_d, amt in rows:
            if isinstance(ex_d, date):
                out.append((ex_d, float(amt) if amt is not None else None))
        return out
