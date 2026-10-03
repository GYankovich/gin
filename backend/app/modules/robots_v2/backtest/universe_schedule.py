"""Day-by-day universe schedule for V2 backtests (+ dividend exclusions)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.modules.corporate_actions.dividend_calendar_service import (
    DividendCalendarService,
    DividendExclusionPolicy,
    policy_from_robot_config,
)
from app.modules.robots_v2.config.v4_schema import ScheduleConfig, TradingRobotConfigV4
from app.modules.robots_v2.universe.service import universe_service

logger = logging.getLogger(__name__)


def list_trade_dates(
    from_d: date,
    to_d: date,
    schedule: ScheduleConfig,
) -> list[date]:
    """Inclusive calendar dates allowed by schedule.weekdays (Mon=0 … Sun=6)."""
    if to_d < from_d:
        return []
    out: list[date] = []
    cur = from_d
    while cur <= to_d:
        if schedule.weekdays[cur.weekday()]:
            out.append(cur)
        cur = cur.fromordinal(cur.toordinal() + 1)
    return out


def dividend_policy_for_config(config: TradingRobotConfigV4) -> DividendExclusionPolicy | None:
    """MOEX stocks/futures: apply dividend calendar. Crypto: skip."""
    if config.core.instrument_type in ("perpetual", "coin_futures"):
        return None
    raw = config.model_dump(by_alias=True)
    return policy_from_robot_config(raw)


def apply_dividend_exclusions(
    db: Session,
    tickers: list[str],
    *,
    trade_date: date,
    policy: DividendExclusionPolicy | None,
    ex_index: dict[str, list[date]] | None = None,
) -> list[str]:
    if policy is None or not tickers:
        return list(tickers)
    svc = DividendCalendarService(db)
    kept: list[str] = []
    for t in tickers:
        tk = str(t).upper()
        ex_dates = (ex_index or {}).get(tk)
        reason = svc.exclusion_reason_for_day_cached(
            ticker=tk,
            trade_date=trade_date,
            policy=policy,
            ex_dates=ex_dates,
        ) if ex_index is not None else svc.exclusion_reason_for_day(
            ticker=tk,
            trade_date=trade_date,
            policy=policy,
        )
        if reason is None:
            kept.append(tk)
    return kept


def _refresh_daily(config: TradingRobotConfigV4) -> bool:
    u = config.universe
    if u.mode == "fixed":
        return False
    if u.mode == "index":
        return True
    policy = (u.screener.refresh_policy if u.screener else "daily") or "daily"
    return policy in ("daily", "on_poll")


async def build_universe_by_day(
    db: Session,
    *,
    user_id: int,
    config: TradingRobotConfigV4,
    from_date: date,
    to_date: date,
    token_id: int | None,
    robot_id: int | None,
    is_cancelled: Any | None = None,
) -> tuple[list[str], dict[date, list[str]], dict[str, Any]]:
    """
    Returns (union_tickers, universe_by_day, stats).

    - fixed / on_session: resolve once (or take fixed list), then dividend-filter per day
    - index / screener daily|on_poll: resolve each trade date with as_of=day
    """
    days = list_trade_dates(from_date, to_date, config.core.schedule)
    if not days:
        return [], {}, {"trade_days": 0, "mode": config.universe.mode}

    policy = dividend_policy_for_config(config)
    u = config.universe
    excluded = {x.upper() for x in u.excluded}
    max_assets = int(u.max_assets)

    async def _resolve_once(as_of: date) -> list[str]:
        if u.mode == "fixed":
            tickers = [t.upper() for t in (u.fixed_list or []) if t]
        else:
            if token_id is None:
                raise ValueError("tokenId is required for index/screener universe in backtest")
            as_of_dt = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
            resolved = await universe_service.resolve(
                db,
                user_id,
                token_id=token_id,
                instrument_type=config.core.instrument_type,
                universe_raw=config.universe.model_dump(by_alias=True),
                robot_id=robot_id,
                as_of=as_of_dt,
            )
            tickers = [i.ticker.upper() for i in resolved.instruments if i.ticker]
        tickers = [t for t in tickers if t not in excluded]
        return tickers[:max_assets]

    universe_by_day: dict[date, list[str]] = {}
    union: set[str] = set()
    resolve_calls = 0
    cancelled = False

    if not _refresh_daily(config):
        base = await _resolve_once(days[0])
        resolve_calls = 1
        ex_index: dict[str, list[date]] | None = None
        if policy is not None and base:
            ex_index = DividendCalendarService(db).preload_exclusion_index(base, days[0], days[-1])
        for d in days:
            if is_cancelled and is_cancelled():
                cancelled = True
                break
            day_list = apply_dividend_exclusions(
                db, base, trade_date=d, policy=policy, ex_index=ex_index,
            )
            universe_by_day[d] = day_list
            union.update(day_list)
    else:
        # Resolve each day; dividend exclusions applied on top (idempotent if already in DMS).
        cache: dict[date, list[str]] = {}
        all_for_div: set[str] = set()
        for d in days:
            if is_cancelled and is_cancelled():
                cancelled = True
                break
            if d not in cache:
                cache[d] = await _resolve_once(d)
                resolve_calls += 1
                all_for_div.update(cache[d])
        ex_index = None
        if not cancelled and policy is not None and all_for_div:
            ex_index = DividendCalendarService(db).preload_exclusion_index(
                sorted(all_for_div), days[0], days[-1],
            )
        for d in days:
            if cancelled or (is_cancelled and is_cancelled()):
                cancelled = True
                break
            day_list = apply_dividend_exclusions(
                db, cache.get(d, []), trade_date=d, policy=policy, ex_index=ex_index,
            )
            universe_by_day[d] = day_list
            union.update(day_list)

    stats = {
        "trade_days": len(days),
        "mode": u.mode,
        "refresh_daily": _refresh_daily(config),
        "resolve_calls": resolve_calls,
        "union_tickers": len(union),
        "dividend_filter": policy is not None,
        "cancelled": cancelled,
    }
    logger.info(
        "backtest universe_by_day days=%s union=%s resolve_calls=%s mode=%s",
        len(days),
        len(union),
        resolve_calls,
        u.mode,
    )
    return sorted(union), universe_by_day, stats
