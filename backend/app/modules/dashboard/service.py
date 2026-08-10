from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDashboardService [1]
#/// Исходный модуль `backend/app/modules/dashboard/service.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from functools import cmp_to_key
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.dashboard.queries import (
    build_account_opened_query,
    build_assets_query,
    build_latest_snapshot_query,
    build_own_funds_query,
    build_previous_day_total_query,
    get_account_for_visibility,
    list_open_accounts,
)
from app.modules.dashboard.schemas import (
    DashboardAccountSummaryKpi,
    DashboardAssetItem,
    DashboardCurrencyTotals,
)


class DashboardService:
    """Сводка по открытым счетам: totals по валютам, assets из позиций, accounts."""

    _SORTABLE = frozenset({
        "account_name",
        "value",
        "own_funds",
        "day_over_day_delta",
        "last_account_sync",
        # legacy alias from older clients
        "total_value",
    })

    def _own_funds(self, db: Session, account_pk: int) -> float:
        # INPUT обычно > 0; OUTPUT в БД часто уже < 0 — вычитаем ABS(payment).
        query, params = build_own_funds_query(account_pk)
        row = db.execute(text(query), params).first()
        if not row or row[0] is None:
            return 0.0
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return 0.0

    def _latest_snapshot_row(self, db: Session, account_pk: int):
        query, params = build_latest_snapshot_query(account_pk)
        return db.execute(text(query), params).first()

    def _prev_day_total(self, db: Session, account_pk: int, latest_snapshot_date: datetime) -> Optional[float]:
        query, params = build_previous_day_total_query(account_pk, latest_snapshot_date)
        row = db.execute(text(query), params).first()
        if not row or row[0] is None:
            return None
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None

    def _resolve_account_opened(
        self,
        db: Session,
        account_pk: int,
        stored: Optional[datetime],
        created_at: Optional[datetime],
    ) -> Optional[datetime]:
        if stored is not None:
            return stored
        query, params = build_account_opened_query(account_pk)
        row = db.execute(text(query), params).first()
        if row and row[0] is not None:
            return row[0]
        return created_at

    @staticmethod
    def _gain_vs_deposits_percent(
        minus_own_funds: float,
        own_funds: float,
        value: float,
    ) -> Optional[float]:
        if abs(minus_own_funds) <= 1e-9:
            return None
        if abs(own_funds) > 1e-9:
            return (minus_own_funds / own_funds) * 100.0
        if abs(value) > 1e-9:
            return (minus_own_funds / value) * 100.0
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
                    value=0.0,
                    minus_own_funds=-own,
                    minus_own_funds_percent=self._gain_vs_deposits_percent(-own, own, 0.0),
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
        if day_delta is not None and abs(day_delta) > 1e-9 and prev_total is not None and abs(prev_total) > 1e-9:
            day_pct = (day_delta / prev_total) * 100.0

        last_account_sync: Optional[datetime] = None
        candidates = [x for x in (last_sync_pa, snap_date) if x is not None]
        if candidates:
            last_account_sync = max(candidates)

        minus = total - own
        return (
            DashboardAccountSummaryKpi(
                own_funds=own,
                value=total,
                minus_own_funds=minus,
                minus_own_funds_percent=self._gain_vs_deposits_percent(minus, own, total),
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
                    sort_col = "value" if col == "total_value" else col
                    if sort_col == "value":
                        va = float(sa.value) if sa else 0.0
                        vb = float(sb.value) if sb else 0.0
                    elif sort_col == "own_funds":
                        va = float(sa.own_funds) if sa else 0.0
                        vb = float(sb.own_funds) if sb else 0.0
                    elif sort_col == "day_over_day_delta":
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

    def _build_accounts(
        self,
        db: Session,
        user_id: int,
        sort_specs: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        rows = list_open_accounts(db, user_id)

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
                    "account_opened": self._resolve_account_opened(db, pa.id, pa.opened_date, pa.created_at),
                    "last_account_sync": last_sync,
                    "dashboard_hidden": bool(getattr(pa, "dashboard_hidden", 0) or 0),
                    "summary": summary,
                }
            )

        return self._sort_accounts(out, sort_specs)

    @staticmethod
    def _build_totals(accounts: List[Dict[str, Any]]) -> List[DashboardCurrencyTotals]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for item in accounts:
            if item.get("dashboard_hidden"):
                continue
            summary: DashboardAccountSummaryKpi = item["summary"]
            cur = (summary.currency or "RUB").upper()
            bucket = buckets.setdefault(
                cur,
                {
                    "total_own_funds": 0.0,
                    "total_value": 0.0,
                    "total_minus_own_funds": 0.0,
                    "total_day_over_day_delta": 0.0,
                    "has_day_delta": False,
                },
            )
            bucket["total_own_funds"] += float(summary.own_funds or 0.0)
            bucket["total_value"] += float(summary.value or 0.0)
            bucket["total_minus_own_funds"] += float(summary.minus_own_funds or 0.0)
            if summary.day_over_day_delta is not None:
                bucket["total_day_over_day_delta"] += float(summary.day_over_day_delta)
                bucket["has_day_delta"] = True

        result: List[DashboardCurrencyTotals] = []
        for currency in sorted(buckets.keys()):
            b = buckets[currency]
            own = b["total_own_funds"]
            value = b["total_value"]
            minus = b["total_minus_own_funds"]
            day_delta = b["total_day_over_day_delta"] if b["has_day_delta"] else None

            day_pct: Optional[float] = None
            if day_delta is not None and abs(day_delta) > 1e-9:
                prev_total = value - day_delta
                if abs(prev_total) > 1e-9:
                    day_pct = (day_delta / prev_total) * 100.0

            result.append(
                DashboardCurrencyTotals(
                    currency=currency,
                    total_own_funds=own,
                    total_value=value,
                    total_minus_own_funds=minus,
                    total_minus_own_funds_percent=DashboardService._gain_vs_deposits_percent(
                        minus, own, value
                    ),
                    total_day_over_day_delta=day_delta,
                    total_day_over_day_delta_percent=day_pct,
                )
            )
        return result

    def _build_assets(
        self,
        db: Session,
        user_id: int,
        included_account_ids: Optional[List[int]] = None,
    ) -> List[DashboardAssetItem]:
        """
        Структура портфеля по последним снимкам OPEN-счетов.

        value — из агрегатов снимка (total_amount_*), чтобы совпадало с «Текущая стоимость»;
        day_over_day_delta — SUM(daily_yield) по позициям того же типа;
        имена типов — из dictionary PORTFOLIO_POSITIONS / INSTRUMENT_TYPE.
        """
        if included_account_ids is not None and len(included_account_ids) == 0:
            return []

        query, params = build_assets_query(user_id, included_account_ids)
        rows = db.execute(text(query), params).mappings().all()

        out: List[DashboardAssetItem] = []
        for r in rows:
            value = float(r["value"] or 0.0)
            day_raw = r["day_over_day_delta"]
            day_delta: Optional[float] = float(day_raw) if day_raw is not None else None
            day_pct: Optional[float] = None
            if day_delta is not None and abs(day_delta) > 1e-9:
                prev = value - day_delta
                if abs(prev) > 1e-9:
                    day_pct = (day_delta / prev) * 100.0
            out.append(
                DashboardAssetItem(
                    type=str(r["type"]),
                    value=value,
                    percent=float(r["percent"] or 0),
                    currency=str(r["currency"] or "RUB"),
                    day_over_day_delta=day_delta,
                    day_over_day_delta_percent=day_pct,
                )
            )
        return out

    def update_visibility(
        self,
        db: Session,
        user_id: int,
        items: List[Tuple[int, bool]],
    ) -> int:
        if not items:
            return 0
        updated = 0
        for account_id, hidden in items:
            row = get_account_for_visibility(db, user_id, account_id)
            if not row:
                continue
            row.dashboard_hidden = 1 if hidden else 0
            updated += 1
        if updated:
            db.commit()
        return updated

    def build_dashboard(
        self,
        db: Session,
        user_id: int,
        sort_specs: List[Tuple[str, str]],
    ) -> Dict[str, Any]:
        accounts = self._build_accounts(db, user_id, sort_specs)
        included_ids = [int(a["account_id"]) for a in accounts if not a.get("dashboard_hidden")]
        return {
            "totals": self._build_totals(accounts),
            "assets": self._build_assets(db, user_id, included_ids),
            "accounts": accounts,
        }


dashboard_service = DashboardService()
