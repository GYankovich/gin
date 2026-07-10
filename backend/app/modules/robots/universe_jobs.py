"""
Плановые job'ы universe v2: П1 candidate_pool, П2 paper_selection → allowed_figis.

Вызываются из TradingSession и HTTP POST /api/robots/jobs/*.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.config.migration import (
    effective_pipeline_from_config,
    ensure_config_v2,
    historical_screening_from_config,
    paper_selection_from_config,
)
from app.modules.robots.config.v2_schema import HISTORICAL_FILTER_TYPES
from app.modules.robots.trading.intervals import resolve_strategy_interval
from app.modules.robots.universe import (
    UNIVERSE_MODE_FIXED,
    normalize_universe_mode,
    resolve_fixed_tickers,
    universe_min_tradable_row,
)

logger = logging.getLogger(__name__)

_JOB_STATE_KEY = "universe_jobs_state"


def _parse_hhmm_msk(raw: Optional[str]) -> Optional[tuple[int, int]]:
    if not raw:
        return None
    s = str(raw).strip().replace(" MSK", "").replace("MSK", "")
    parts = s.split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _msk_from_utc(dt: datetime) -> datetime:
    utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return utc.astimezone(ZoneInfo("Europe/Moscow"))
    except Exception:
        return utc + timedelta(hours=3)


def _now_msk() -> datetime:
    return _msk_from_utc(datetime.now(timezone.utc))


def _in_trading_hours_msk(start: str, end: str) -> bool:
    sh, sm = (int(start.split(":")[0]), int(start.split(":")[1])) if ":" in start else (10, 0)
    eh, em = (int(end.split(":")[0]), int(end.split(":")[1])) if ":" in end else (18, 45)
    now = _now_msk()
    cur = now.hour * 60 + now.minute
    return sh * 60 + sm <= cur <= eh * 60 + em


def _job_state(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = config.get(_JOB_STATE_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _parse_iso_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def should_run_historical_screening(
    config: Dict[str, Any],
    *,
    last_run_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> bool:
    """П1: daily_at_msk (раз в сутки после времени) или не запускался сегодня."""
    cfg = ensure_config_v2(config)
    hs = historical_screening_from_config(cfg)
    if not hs.enabled:
        return False
    now_utc = now or datetime.now(timezone.utc)
    last = last_run_at
    if last is None:
        last = _parse_iso_dt(_job_state(cfg).get("last_historical_screening_at"))

    daily = _parse_hhmm_msk(hs.refresh.daily_at_msk)
    if daily:
        h, m = daily
        msk = _msk_from_utc(now_utc)
        if msk.hour < h or (msk.hour == h and msk.minute < m):
            return False
        if last:
            last_msk = _msk_from_utc(last)
            if last_msk.date() >= msk.date():
                return False
        return True

    every = int(hs.refresh.every_minutes or 0)
    if every <= 0:
        return False
    if last is None:
        return True
    return (now_utc - last).total_seconds() >= every * 60


def should_run_paper_selection(
    config: Dict[str, Any],
    *,
    last_run_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
    trading_hours_start: str = "10:00",
    trading_hours_end: str = "18:45",
) -> bool:
    """П2: every_minutes в торговые часы (или всегда, если only_trading_hours=false)."""
    cfg = ensure_config_v2(config)
    ps = paper_selection_from_config(cfg)
    if not ps.enabled:
        return False
    if normalize_universe_mode(cfg) == UNIVERSE_MODE_FIXED:
        return False

    every = int(ps.refresh.every_minutes or 0)
    if every <= 0:
        return False

    if ps.refresh.only_trading_hours and not _in_trading_hours_msk(
        trading_hours_start, trading_hours_end
    ):
        return False

    now_utc = now or datetime.now(timezone.utc)
    last = last_run_at
    if last is None:
        last = _parse_iso_dt(_job_state(cfg).get("last_paper_selection_at"))
    if last is None:
        return True
    return (now_utc - last).total_seconds() >= every * 60


async def _list_tqbr_tickers(db: Session, board: str = "TQBR") -> List[str]:
    rows = db.execute(
        text(f"SELECT secid FROM {settings.DB_SCHEMA}.tqbr_securities ORDER BY secid")
    ).fetchall()
    if rows:
        return sorted({str(r[0]).strip().upper() for r in rows if r and r[0]})
    snap = db.execute(
        text(
            f"""
            SELECT DISTINCT UPPER(ticker) AS ticker
            FROM {settings.DB_SCHEMA}.market_snapshot_data_history
            WHERE board = :board
            ORDER BY ticker
            LIMIT 800
            """
        ),
        {"board": board},
    ).fetchall()
    return [str(r[0]) for r in snap if r and r[0]]


async def _snapshot_price_rows(db: Session, board: str, tickers: List[str]) -> List[Dict[str, Any]]:
    """Последние цены из свежего снапшота для ATR-скрининга."""
    if not tickers:
        return []
    sid = db.execute(
        text(
            f"""
            SELECT id FROM {settings.DB_SCHEMA}.market_snapshot_history
            WHERE board = :board
            ORDER BY trade_date DESC, id DESC
            LIMIT 1
            """
        ),
        {"board": board},
    ).scalar()
    if not sid:
        return [{"ticker": tk, "last_price": 1.0} for tk in tickers]
    from sqlalchemy import bindparam

    stmt = text(
        f"""
        SELECT UPPER(ticker), last_price, value_today, volume_lots,
               security_status, trading_status, num_trades
        FROM {settings.DB_SCHEMA}.market_snapshot_data_history
        WHERE snapshot_id = :sid AND UPPER(ticker) IN :tickers
        """
    ).bindparams(bindparam("tickers", expanding=True))
    rows = db.execute(stmt, {"sid": int(sid), "tickers": tickers}).fetchall()
    by_tk = {str(r[0]).upper(): r for r in rows}
    out: List[Dict[str, Any]] = []
    for tk in tickers:
        r = by_tk.get(tk)
        if r:
            out.append({
                "ticker": tk,
                "last_price": float(r[1] or 0) or None,
                "value_today": float(r[2] or 0),
                "volume_lots": float(r[3] or 0),
                "security_status": r[4],
                "trading_status": r[5],
                "num_trades": int(r[6] or 0),
            })
        else:
            out.append({"ticker": tk, "last_price": 1.0})
    return out


def _historical_filters_only(filters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("type") or "").lower() in HISTORICAL_FILTER_TYPES:
            out.append(dict(f))
    return out


def _evaluate_atr_screen(
    atr_map: Dict[str, float],
    filters: List[Dict[str, Any]],
) -> Set[str]:
    atr_f = next(
        (f for f in filters if str(f.get("type") or "").lower() == "atr"),
        None,
    )
    if not atr_f:
        return set(atr_map.keys())
    min_pct = float(atr_f.get("min_percent") or 0)
    passed = set()
    for tk, pct in atr_map.items():
        if pct is not None and float(pct) >= min_pct:
            passed.add(tk)
    return passed


async def rebuild_candidate_pool(
    db: Session,
    robot_service: Any,
    *,
    robot_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """
    П1: MOEX prefetch + исторические фильтры → config.candidate_pool.
    ATR в v1 считается по D1 (как DMS); intraday MOEX свечи префетчатся для follow-up.
    """
    from app.modules.dms.service import dms_service
    from app.modules.robots.trading.data import get_market_data_facade

    robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
    config = ensure_config_v2(dict(robot.get("config") or {}))
    hs = historical_screening_from_config(config)
    board = str(hs.board or "TQBR").upper()

    if not hs.enabled:
        config["candidate_pool"] = {"tickers": [], "as_of": None, "enabled": False}
        await _persist_robot_config(db, robot_id, user_id, config, historical_ran=False)
        return {"tickers": [], "message": "historical_screening disabled", "skipped": True}

    tickers = await _list_tqbr_tickers(db, board)
    if hs.universe == "fixed" and hs.fixed_tickers:
        tickers = sorted(set(hs.fixed_tickers))
    if not tickers:
        return {"tickers": [], "message": "no tickers for screening", "skipped": True}

    resolved = resolve_strategy_interval(hs.interval)
    till = datetime.now(timezone.utc).date()
    from_day = till - timedelta(days=max(1, int(hs.lookback_days)))

    if resolved.supports_moex_iss:
        market_data = get_market_data_facade()
        await market_data.ensure_candles(
            db,
            board=board,
            tickers=tickers[:400],
            resolved=resolved,
            from_date=from_day,
            till_date=till,
            user_id=user_id,
        )

    hist_filters = _historical_filters_only(hs.filters)
    rows = await _snapshot_price_rows(db, board, tickers[:400])
    rows = [r for r in rows if universe_min_tradable_row(r)] if hs.universe == "tqbr_all" else rows

    passed: Set[str] = set(tk for tk in tickers[:400])
    atr_stats: Dict[str, Any] = {}
    if hist_filters:
        atr_map, cache_stats = await dms_service._load_atr_percent_map(
            db,
            board=board,
            rows=rows,
            filters=hist_filters,
            user_id=user_id,
        )
        atr_stats = cache_stats
        passed = _evaluate_atr_screen(atr_map, hist_filters)
        if not passed and atr_map:
            passed = set(atr_map.keys())

    pool = {
        "tickers": sorted(passed),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "board": board,
        "interval": hs.interval,
        "lookback_days": hs.lookback_days,
        "source": "historical_screening",
        "stats": {
            "scanned": len(tickers),
            "passed": len(passed),
            "atr_prefetch": atr_stats,
        },
    }
    config["candidate_pool"] = pool
    await _persist_robot_config(
        db, robot_id, user_id, config, historical_ran=True,
    )
    logger.info(
        "candidate_pool robot_id=%s passed=%s/%s",
        robot_id,
        len(passed),
        len(tickers),
    )
    return {
        "tickers": pool["tickers"],
        "passed": len(passed),
        "scanned": len(tickers),
        "as_of": pool["as_of"],
        "message": None,
    }


async def rebuild_paper_selection(
    db: Session,
    robot_service: Any,
    *,
    robot_id: int,
    user_id: int,
    force_refresh_snapshot: bool = True,
    force_recompute_universe: bool = True,
) -> Dict[str, Any]:
    """П2: snapshot + paper_selection.filters → daily_universe → allowed_figis."""
    cfg = ensure_config_v2(
        dict((await robot_service.get_robot_by_id(db, robot_id, user_id)).get("config") or {})
    )
    ps = paper_selection_from_config(cfg)
    pool = cfg.get("candidate_pool") if isinstance(cfg.get("candidate_pool"), dict) else {}
    pool_tickers = list(pool.get("tickers") or [])

    if ps.input == "candidate_pool" and not pool_tickers:
        return {
            "allowed_figis": list(cfg.get("allowed_figis") or []),
            "message": "candidate_pool пуст — сначала выполните П1 (historical screening)",
            "skipped": True,
        }

    result = await robot_service.sync_live_universe_from_pipeline(
        db,
        robot_id,
        user_id,
        force_refresh_snapshot=force_refresh_snapshot,
        force_recompute_universe=force_recompute_universe,
    )
    await _touch_job_state(db, robot_id, user_id, paper_ran=True)
    result["candidate_pool_size"] = len(pool_tickers)
    return result


async def rebuild_crypto_screening(
    db: Session,
    robot_service: Any,
    *,
    robot_id: int,
    user_id: int,
    force: bool = False,
) -> Dict[str, Any]:
    """Crypto universe (ByBit): tickers filters -> config.allowed_symbols."""
    from app.modules.robots.crypto_universe import rebuild_crypto_universe

    robot = await robot_service.get_robot_by_id(db, robot_id, user_id)
    cfg = dict(robot.get("config") or {})
    return await rebuild_crypto_universe(
        db,
        robot_id=robot_id,
        user_id=user_id,
        config=cfg,
        force=force,
    )


async def _persist_robot_config(
    db: Session,
    robot_id: int,
    user_id: int,
    config: Dict[str, Any],
    *,
    historical_ran: bool = False,
    paper_ran: bool = False,
) -> None:
    await _touch_job_state(
        db,
        robot_id,
        user_id,
        config=config,
        historical_ran=historical_ran,
        paper_ran=paper_ran,
    )


async def _touch_job_state(
    db: Session,
    robot_id: int,
    user_id: int,
    *,
    config: Optional[Dict[str, Any]] = None,
    historical_ran: bool = False,
    paper_ran: bool = False,
) -> None:
    if config is None:
        row = db.execute(
            text(f"SELECT config FROM {settings.DB_SCHEMA}.robots WHERE id = :rid"),
            {"rid": robot_id},
        ).first()
        config = ensure_config_v2(dict(row[0] or {}) if row else {})
    else:
        config = ensure_config_v2(config)

    st = _job_state(config)
    now_iso = datetime.now(timezone.utc).isoformat()
    if historical_ran:
        st["last_historical_screening_at"] = now_iso
    if paper_ran:
        st["last_paper_selection_at"] = now_iso
    config[_JOB_STATE_KEY] = st

    db.execute(
        text(
            f"""
            UPDATE {settings.DB_SCHEMA}.robots
            SET config = CAST(:config AS jsonb),
                date_modification = :now,
                usermod = :uid
            WHERE id = :rid
            """
        ),
        {
            "rid": robot_id,
            "uid": user_id,
            "config": json.dumps(ensure_config_v2(config), ensure_ascii=False),
            "now": datetime.now(timezone.utc),
        },
    )
    db.commit()


async def run_scheduled_universe_jobs(
    db: Session,
    robot_service: Any,
    *,
    robot_id: int,
    user_id: int,
    config: Dict[str, Any],
    last_historical_at: Optional[datetime] = None,
    last_paper_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Проверить расписание v2 и выполнить due job'ы."""
    cfg = ensure_config_v2(config)
    risk = dict(cfg.get("risk") or {})
    th_start = str(risk.get("trading_hours_start") or "10:00 MSK").replace(" MSK", "")
    th_end = str(risk.get("trading_hours_end") or "18:45 MSK").replace(" MSK", "")

    out: Dict[str, Any] = {"historical": None, "paper": None}
    if should_run_historical_screening(cfg, last_run_at=last_historical_at):
        out["historical"] = await rebuild_candidate_pool(
            db, robot_service, robot_id=robot_id, user_id=user_id,
        )
        row = db.execute(
            text(f"SELECT config FROM {settings.DB_SCHEMA}.robots WHERE id = :rid"),
            {"rid": robot_id},
        ).first()
        cfg = ensure_config_v2(dict(row[0] or {}) if row else {})

    if should_run_paper_selection(
        cfg,
        last_run_at=last_paper_at,
        trading_hours_start=th_start,
        trading_hours_end=th_end,
    ):
        out["paper"] = await rebuild_paper_selection(
            db, robot_service, robot_id=robot_id, user_id=user_id,
        )
    return out


__all__ = [
    "rebuild_candidate_pool",
    "rebuild_crypto_screening",
    "rebuild_paper_selection",
    "run_scheduled_universe_jobs",
    "should_run_historical_screening",
    "should_run_paper_selection",
]
