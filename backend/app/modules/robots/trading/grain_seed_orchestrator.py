"""
Оркестрация для стратегии «По зёрнышку, по семечке»: правила вне generate_signals
(резерв средств, окно принудительного сворачивания, серия убыточных дней, сверка БД/брокер).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.modules.tinvest.facade import TInvestFacade

MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class GrainSeedOrchestrationResult:
    block_new_entries: bool
    block_reason: str
    effective_free_funds: float
    allow_only_reduce: bool
    broker_non_currency_figis: frozenset
    db_open_figis: frozenset
    position_mismatch: bool


def parse_force_close_time(value: Optional[str]) -> time:
    raw = (value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return time(18, 45)


def compute_effective_free_funds(raw_free: float, reserve_pct: float) -> float:
    r = max(0.0, min(100.0, float(reserve_pct or 0.0)))
    return max(0.0, float(raw_free or 0.0) * (1.0 - r / 100.0))


def extract_broker_position_figis(portfolio: Optional[Dict[str, Any]]) -> Set[str]:
    if not portfolio:
        return set()
    out: Set[str] = set()
    for pos in portfolio.get("positions") or []:
        it = (pos.get("instrument_type") or "").upper()
        if "CURRENCY" in it:
            continue
        q = pos.get("quantity") or {}
        qty = float(q.get("decimal") or 0.0)
        if abs(qty) < 1e-9:
            continue
        figi = pos.get("figi")
        if figi:
            out.add(str(figi))
    return out


def extract_db_open_figis(positions: List[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for p in positions or []:
        if str(p.get("status", "")).lower() != "open":
            continue
        f = p.get("figi")
        if f:
            out.add(str(f))
    return out


def count_consecutive_loss_days_from_rows(
    rows: List[Tuple[Any, Any]],
) -> int:
    """
    rows: (trade_day, pnl) ordered DESC by trade_day.
    Считает подряд идущие дни с отрицательной суммой profit, начиная с самого свежего дня в выборке.
    """
    streak = 0
    for _, pnl in rows:
        p = float(pnl or 0.0)
        if p < 0:
            streak += 1
        else:
            break
    return streak


def fetch_consecutive_loss_days(
    db: Session,
    schema: str,
    robot_id: int,
) -> int:
    q = f"""
        SELECT
            ((closed_at AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Moscow')::date AS trade_day,
            COALESCE(SUM(CAST(profit AS DOUBLE PRECISION)), 0) AS pnl
        FROM {schema}.robot_trades
        WHERE robot_id = :robot_id
          AND status = 'closed'
          AND closed_at IS NOT NULL
          AND profit IS NOT NULL
        GROUP BY 1
        ORDER BY trade_day DESC
        LIMIT 120
    """
    try:
        res = db.execute(text(q), {"robot_id": robot_id}).fetchall()
        rows = [(r[0], r[1]) for r in res if r and r[0] is not None]
        return count_consecutive_loss_days_from_rows(rows)
    except Exception:
        return 0


def evaluate_grain_seed_orchestration(
    *,
    now_utc: datetime,
    portfolio: Optional[Dict[str, Any]],
    strategy_params: Dict[str, Any],
    open_positions: List[Dict[str, Any]],
    db: Optional[Session],
    schema: str,
    robot_id: int,
) -> GrainSeedOrchestrationResult:
    sp = strategy_params or {}
    reserve_pct = float(sp.get("free_funds_reserve_pct", 50.0))
    streak_limit = int(sp.get("day_loss_streak_limit", 3) or 3)
    force_t = parse_force_close_time(sp.get("force_close_time_msk"))

    raw = float(TInvestFacade.compute_free_funds_from_portfolio(portfolio) if portfolio else 0.0)
    effective = compute_effective_free_funds(raw, reserve_pct)

    now_msk = now_utc.astimezone(MSK)
    cur_t = now_msk.time()
    allow_only_reduce = cur_t >= force_t

    loss_streak = 0
    if db:
        loss_streak = fetch_consecutive_loss_days(db, schema, robot_id)

    block = False
    reason = ""
    if streak_limit > 0 and loss_streak >= streak_limit:
        block = True
        reason = f"loss_streak>={streak_limit} (days={loss_streak})"

    broker_figis = extract_broker_position_figis(portfolio)
    db_figis = extract_db_open_figis(open_positions)
    mismatch = broker_figis != db_figis

    return GrainSeedOrchestrationResult(
        block_new_entries=block,
        block_reason=reason,
        effective_free_funds=effective,
        allow_only_reduce=allow_only_reduce,
        broker_non_currency_figis=frozenset(broker_figis),
        db_open_figis=frozenset(db_figis),
        position_mismatch=mismatch,
    )


def filter_grain_seed_signals(
    signals: List[Dict[str, Any]],
    orch: GrainSeedOrchestrationResult,
) -> List[Dict[str, Any]]:
    if not signals:
        return signals
    out: List[Dict[str, Any]] = []
    for s in signals:
        sig = str(s.get("signal") or "").upper()
        if orch.block_new_entries or orch.allow_only_reduce:
            if sig == "BUY":
                continue
        out.append(s)
    return out
