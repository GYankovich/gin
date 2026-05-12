from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDashboardService [1]
#/// Исходный модуль `backend/app/modules/dashboard/service.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from functools import cmp_to_key
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.dashboard.schemas import DashboardAccountSummaryKpi
from app.modules.tinvest.models import PortfolioAccount


class DashboardService:
    """Сводка по открытым счетам: данные из БД без ограничения по датам (операции и снимки целиком)."""

    _SORTABLE = frozenset({
        "account_name",
        "total_value",
        "own_funds",
        "day_over_day_delta",
        "last_account_sync",
    })

    def _own_funds(self, db: Session, account_pk: int) -> float:
        row = db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
                    -
                    COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN payment ELSE 0 END), 0)
                FROM ganaly.portfolio_operations
                WHERE account_id = :account_id
                """
            ),
            {"account_id": account_pk},
        ).first()
        if not row or row[0] is None:
            return 0.0
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return 0.0

    def _latest_snapshot_row(self, db: Session, account_pk: int):
        return db.execute(
            text(
                """
                SELECT total_amount_portfolio, snapshot_date, daily_yield, currency
                FROM ganaly.portfolio_snapshots
                WHERE account_id = :account_id
                ORDER BY snapshot_date DESC
                LIMIT 1
                """
            ),
            {"account_id": account_pk},
        ).first()

    def _prev_day_total(self, db: Session, account_pk: int, latest_snapshot_date: datetime) -> Optional[float]:
        row = db.execute(
            text(
                """
                SELECT total_amount_portfolio
                FROM ganaly.portfolio_snapshots
                WHERE account_id = :account_id
                  AND snapshot_date < date_trunc('day', CAST(:latest_ts AS timestamptz))
                ORDER BY snapshot_date DESC
                LIMIT 1
                """
            ),
            {"account_id": account_pk, "latest_ts": latest_snapshot_date},
        ).first()
        if not row or row[0] is None:
            return None
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None

    def _build_summary_kpi(
        self,
        db: Session,
        account_pk: int,
        last_sync_pa: Optional[datetime],
    ) -> Tuple[DashboardAccountSummaryKpi, Optional[datetime]]:
        own = self._own_funds(db, account_pk)
        latest = self._latest_snapshot_row(db, account_pk)
        if not latest:
            last_sync = last_sync_pa
            return (
                DashboardAccountSummaryKpi(
                    own_funds=own,
                    total_value=0.0,
                    total_minus_own_funds=-own,
                    day_over_day_delta=None,
                    day_over_day_delta_percent=None,
                    currency="RUB",
                ),
                last_sync,
            )

        total = float(latest[0] or 0.0)
        snap_date = latest[1]
        daily_yield = float(latest[2]) if latest[2] is not None else None
        currency = str(latest[3] or "RUB")

        prev_total = self._prev_day_total(db, account_pk, snap_date)

        day_delta: Optional[float] = None
        if daily_yield is not None:
            day_delta = daily_yield
        elif prev_total is not None:
            day_delta = total - prev_total

        day_pct: Optional[float] = None
        if day_delta is not None and prev_total is not None and abs(prev_total) > 1e-9:
            day_pct = (day_delta / prev_total) * 100.0

        last_account_sync: Optional[datetime] = None
        candidates = [x for x in (last_sync_pa, snap_date) if x is not None]
        if candidates:
            last_account_sync = max(candidates)

        return (
            DashboardAccountSummaryKpi(
                own_funds=own,
                total_value=total,
                total_minus_own_funds=total - own,
                day_over_day_delta=day_delta,
                day_over_day_delta_percent=day_pct,
                currency=currency,
            ),
            last_account_sync,
        )

    def _sort_accounts(
        self,
        items: List[Dict[str, Any]],
        sort_specs: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        normalized = [(c, d.lower()) for c, d in sort_specs if c in self._SORTABLE]
        if not normalized:
            return items

        def compare(a: Dict[str, Any], b: Dict[str, Any]) -> int:
            for col, direction in normalized:
                desc = direction == "desc"
                if col == "account_name":
                    va = (a.get("account_name") or "").lower()
                    vb = (b.get("account_name") or "").lower()
                elif col == "last_account_sync":
                    ta = a.get("last_account_sync")
                    tb = b.get("last_account_sync")
                    if ta is None and tb is None:
                        continue
                    if ta is None:
                        return 1
                    if tb is None:
                        return -1
                    va = ta.timestamp()
                    vb = tb.timestamp()
                else:
                    sa = a.get("summary")
                    sb = b.get("summary")
                    if col == "total_value":
                        va = float(sa.total_value) if sa else 0.0
                        vb = float(sb.total_value) if sb else 0.0
                    elif col == "own_funds":
                        va = float(sa.own_funds) if sa else 0.0
                        vb = float(sb.own_funds) if sb else 0.0
                    elif col == "day_over_day_delta":
                        da = sa.day_over_day_delta if sa else None
                        dbv = sb.day_over_day_delta if sb else None
                        if da is None and dbv is None:
                            continue
                        if da is None:
                            return 1
                        if dbv is None:
                            return -1
                        va = float(da)
                        vb = float(dbv)
                    else:
                        continue

                if va == vb:
                    continue
                if va < vb:
                    return 1 if desc else -1
                return -1 if desc else 1
            return 0

        return sorted(items, key=cmp_to_key(compare))

    def build_dashboard(
        self,
        db: Session,
        user_id: int,
        sort_specs: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        rows = (
            db.query(PortfolioAccount)
            .filter(
                PortfolioAccount.user_id == user_id,
                PortfolioAccount.account_status == "OPEN",
            )
            .all()
        )

        out: List[Dict[str, Any]] = []
        for pa in rows:
            summary, last_sync = self._build_summary_kpi(db, pa.id, pa.last_sync_at)
            out.append(
                {
                    "account_id": pa.id,
                    "external_account_id": pa.account_id,
                    "account_name": pa.account_name,
                    "account_type": pa.account_type or "unknown",
                    "account_status": pa.account_status,
                    "last_account_sync": last_sync,
                    "summary": summary,
                }
            )

        return self._sort_accounts(out, sort_specs)


dashboard_service = DashboardService()
