from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDashboardService [1]
#/// Исходный модуль `backend/app/modules/dashboard/service.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import date, datetime, timedelta, timezone
from functools import cmp_to_key
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.dashboard.schemas import (
    DashboardAccountSummaryKpi,
    DashboardAssetItem,
    DashboardCurrencyTotals,
)
from app.modules.dashboard.queries import (
    build_account_opened_query,
    build_assets_query,
    build_latest_snapshot_query,
    build_own_funds_query,
    build_yesterday_total_query,
    get_account_for_visibility,
    list_open_account_token_types,
    list_open_accounts,
)
from app.modules.trading_core.brokers.routing import broker_from_token_type, normalize_broker_type

MOSCOW = ZoneInfo("Europe/Moscow")
_ASSET_GAP = 0.01


def resolve_account_broker(external_account_id: Optional[str], token_type: Optional[str]) -> str:
    """Брокер счёта: префикс bybit: важнее типа токена, иначе tinvest."""
    ext = str(external_account_id or "").strip().lower()
    if ext.startswith("bybit:"):
        return "bybit"
    raw = str(token_type or "").strip()
    if not raw:
        return "tinvest"
    if raw.isdigit():
        return broker_from_token_type(int(raw))
    return normalize_broker_type(raw)


def account_currency_code(item: Dict[str, Any]) -> Optional[str]:
    summary = item.get("summary")
    raw = summary.get("currency") if isinstance(summary, dict) else getattr(summary, "currency", None)
    code = str(raw or "").strip().upper()
    return code or None


def filter_settings_accounts(
    items: List[Dict[str, Any]],
    *,
    broker: Optional[str] = None,
    currency: Optional[str] = None,
    token_types: Optional[Dict[int, Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    """Опциональные фильтры списка настройки. Оба заданы — пересечение."""
    broker_raw = str(broker or "").strip()
    broker_code = normalize_broker_type(broker_raw) if broker_raw else None
    currency_code = str(currency or "").strip().upper() or None
    if broker_code is None and currency_code is None:
        return items
    types = token_types or {}
    out: List[Dict[str, Any]] = []
    for item in items:
        if currency_code and account_currency_code(item) != currency_code:
            continue
        if broker_code:
            token_type = types.get(int(item["account_id"]))
            if resolve_account_broker(item.get("external_account_id"), token_type) != broker_code:
                continue
        out.append(item)
    return out


def moscow_date(value: datetime) -> date:
    """Calendar date of a timestamp in Europe/Moscow. Naive values are UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW).date()


def resolve_day_change(
    latest_at: Optional[datetime],
    yesterday_total: Optional[float],
    latest_total: float,
    now: Optional[datetime] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Change versus the previous Moscow day's close.

    yesterday_total is the last snapshot on the Moscow day before the latest
    snapshot. The latest snapshot must be from today or from yesterday (no
    snapshot has arrived today yet). Anything older is not a day change.
    Returns (delta, yesterday_total).
    """
    if latest_at is None or yesterday_total is None:
        return None, None
    current = now or datetime.now(MOSCOW)
    latest_day = moscow_date(latest_at)
    today = moscow_date(current)
    if latest_day != today and latest_day != today - timedelta(days=1):
        return None, None
    return latest_total - float(yesterday_total), float(yesterday_total)


def percent_vs_base(delta: Optional[float], base: Optional[float]) -> Optional[float]:
    if delta is None or base is None or abs(base) <= 1e-9:
        return None
    return (delta / base) * 100.0


def gain_vs_deposits_percent(
    minus_own_funds: Optional[float],
    own_funds: Optional[float],
) -> Optional[float]:
    if minus_own_funds is None or own_funds is None or abs(own_funds) <= 1e-9:
        return None
    return (minus_own_funds / own_funds) * 100.0


def _asset_day_percent(value: float, day_delta: Optional[float]) -> Optional[float]:
    if day_delta is None:
        return None
    if abs(day_delta) <= 1e-9:
        return 0.0
    prev = value - day_delta
    if abs(prev) <= 1e-9:
        return None
    return (day_delta / prev) * 100.0


def shape_asset_allocation(rows: List[Dict[str, Any]]) -> List[DashboardAssetItem]:
    """
    Percents are shares of portfolio value. If type buckets diverge from that
    value by more than 1% (notional stuffed into a bucket), collapse to cash
    and the residual position value.
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        currency = str(row.get("currency") or "RUB").upper()
        bucket = grouped.setdefault(currency, {"total": float(row.get("portfolio_total") or 0.0), "rows": []})
        bucket["total"] = float(row.get("portfolio_total") or 0.0)
        if row.get("type") is None or row.get("value") is None:
            continue
        bucket["rows"].append(row)

    out: List[DashboardAssetItem] = []
    for currency in sorted(grouped):
        total = float(grouped[currency]["total"])
        items: List[Dict[str, Any]] = grouped[currency]["rows"]
        if abs(total) <= 1e-9:
            continue
        bucket_sum = sum(float(item["value"] or 0.0) for item in items)
        gap = abs(bucket_sum - total) / abs(total)
        if gap > _ASSET_GAP:
            cash = sum(
                float(item["value"] or 0.0)
                for item in items
                if item.get("instrument_type") == "currency"
            )
            if cash * total > 0 and abs(cash) > abs(total):
                money = total
            else:
                money = cash
            positions = total - money
            if abs(money) > 1e-9:
                out.append(_asset_item("Деньги", money, total, currency, None))
            if abs(positions) > 1e-9:
                out.append(_asset_item("Позиции", positions, total, currency, None))
            continue

        for item in items:
            value = float(item["value"] or 0.0)
            day_raw = item.get("day_over_day_delta")
            day_delta = float(day_raw) if day_raw is not None else None
            out.append(_asset_item(str(item["type"]), value, total, currency, day_delta))
        residual = total - bucket_sum
        if abs(residual) >= 1.0:
            out.append(_asset_item("Прочее", residual, total, currency, None))
    return out


def _asset_item(
    asset_type: str,
    value: float,
    total: float,
    currency: str,
    day_delta: Optional[float],
) -> DashboardAssetItem:
    return DashboardAssetItem(
        type=asset_type,
        value=value,
        percent=(value / total) * 100.0,
        currency=currency,
        day_over_day_delta=day_delta,
        day_over_day_delta_percent=_asset_day_percent(value, day_delta),
    )


class DashboardService:
    """Сводка по открытым счетам: totals по валютам, assets из позиций, accounts."""

    _SORTABLE = frozenset({
        "account_name",
        "value",
        "own_funds",
        "day_over_day_delta",
        "last_account_sync",
        "dashboard_hidden",
        # legacy alias from older clients
        "total_value",
    })

    def _own_funds(self, db: Session, account_pk: int, currency: str) -> Optional[float]:
        query, params = build_own_funds_query(account_pk, currency)
        row = db.execute(text(query), params).first()
        if not row or row[0] is None:
            return None
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None

    def _latest_snapshot_row(self, db: Session, account_pk: int):
        query, params = build_latest_snapshot_query(account_pk)
        return db.execute(text(query), params).first()

    def _yesterday_total(self, db: Session, account_pk: int, yesterday: date) -> Optional[float]:
        query, params = build_yesterday_total_query(account_pk, yesterday)
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

    def _build_summary_kpi(
        self,
        db: Session,
        account_pk: int,
        last_sync_pa: Optional[datetime],
    ) -> Tuple[DashboardAccountSummaryKpi, Optional[datetime], Optional[float]]:
        latest = self._latest_snapshot_row(db, account_pk)
        if not latest:
            return (
                DashboardAccountSummaryKpi(
                    own_funds=None,
                    value=None,
                    minus_own_funds=None,
                    minus_own_funds_percent=None,
                    day_over_day_delta=None,
                    day_over_day_delta_percent=None,
                    currency=None,
                ),
                last_sync_pa,
                None,
            )

        total = float(latest[0] or 0.0)
        snap_date = latest[1]
        currency = str(latest[2] or "").strip().upper() or None
        own = self._own_funds(db, account_pk, currency) if currency else None
        minus = None if own is None else total - own

        yesterday_total: Optional[float] = None
        day_delta: Optional[float] = None
        if snap_date is not None:
            latest_day = moscow_date(snap_date)
            today = moscow_date(datetime.now(MOSCOW))
            if latest_day == today or latest_day == today - timedelta(days=1):
                yesterday_total = self._yesterday_total(db, account_pk, latest_day - timedelta(days=1))
                day_delta, yesterday_total = resolve_day_change(snap_date, yesterday_total, total)

        last_account_sync: Optional[datetime] = None
        candidates = [x for x in (last_sync_pa, snap_date) if x is not None]
        if candidates:
            last_account_sync = max(candidates)

        return (
            DashboardAccountSummaryKpi(
                own_funds=own,
                value=total,
                minus_own_funds=minus,
                minus_own_funds_percent=gain_vs_deposits_percent(minus, own),
                day_over_day_delta=day_delta,
                day_over_day_delta_percent=percent_vs_base(day_delta, yesterday_total),
                currency=currency,
            ),
            last_account_sync,
            yesterday_total if day_delta is not None else None,
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
                elif col == "dashboard_hidden":
                    va = 1 if a.get("dashboard_hidden") else 0
                    vb = 1 if b.get("dashboard_hidden") else 0
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
                        va = float(sa.value) if sa and sa.value is not None else 0.0
                        vb = float(sb.value) if sb and sb.value is not None else 0.0
                    elif sort_col == "own_funds":
                        va = float(sa.own_funds) if sa and sa.own_funds is not None else 0.0
                        vb = float(sb.own_funds) if sb and sb.own_funds is not None else 0.0
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
            summary, last_sync, yesterday_value = self._build_summary_kpi(db, pa.id, pa.last_sync_at)
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
                    "last_token_id": (
                        int(pa.last_token_id)
                        if getattr(pa, "last_token_id", None) is not None
                        else None
                    ),
                    "summary": summary,
                    "_yesterday_value": yesterday_value,
                }
            )

        return self._sort_accounts(out, sort_specs)

    @staticmethod
    def _build_totals(accounts: List[Dict[str, Any]]) -> List[DashboardCurrencyTotals]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for item in accounts:
            yesterday = item.pop("_yesterday_value", None)
            if item.get("dashboard_hidden"):
                continue
            summary: DashboardAccountSummaryKpi = item["summary"]
            if not summary.currency or summary.value is None:
                continue
            cur = summary.currency.upper()
            bucket = buckets.setdefault(
                cur,
                {
                    "total_value": 0.0,
                    "own_parts": [],
                    "minus_parts": [],
                    "own_complete": True,
                    "day_deltas": [],
                    "yesterday_values": [],
                    "valued_accounts": 0,
                },
            )
            bucket["total_value"] += float(summary.value)
            bucket["valued_accounts"] += 1
            if summary.own_funds is None or summary.minus_own_funds is None:
                if abs(float(summary.value)) > 1e-9:
                    bucket["own_complete"] = False
            else:
                bucket["own_parts"].append(float(summary.own_funds))
                bucket["minus_parts"].append(float(summary.minus_own_funds))
            if summary.day_over_day_delta is not None and yesterday is not None:
                bucket["day_deltas"].append(float(summary.day_over_day_delta))
                bucket["yesterday_values"].append(float(yesterday))

        result: List[DashboardCurrencyTotals] = []
        for currency in sorted(buckets.keys()):
            b = buckets[currency]
            own = sum(b["own_parts"]) if b["own_complete"] else None
            minus = sum(b["minus_parts"]) if b["own_complete"] else None
            day_ready = len(b["day_deltas"]) == b["valued_accounts"] and b["valued_accounts"] > 0
            day_delta = sum(b["day_deltas"]) if day_ready else None
            day_base = sum(b["yesterday_values"]) if day_ready else None
            result.append(
                DashboardCurrencyTotals(
                    currency=currency,
                    total_own_funds=own,
                    total_value=b["total_value"],
                    total_minus_own_funds=minus,
                    total_minus_own_funds_percent=gain_vs_deposits_percent(minus, own),
                    total_day_over_day_delta=day_delta,
                    total_day_over_day_delta_percent=percent_vs_base(day_delta, day_base),
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

        Доли считаются от total_amount_portfolio. Если сумма бакетов расходится
        со стоимостью больше чем на 1%, вместо них отдаются «Деньги» и «Позиции».
        """
        if included_account_ids is not None and len(included_account_ids) == 0:
            return []

        query, params = build_assets_query(user_id, included_account_ids)
        rows = db.execute(text(query), params).mappings().all()
        return shape_asset_allocation([dict(r) for r in rows])

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

    def list_settings_accounts(
        self,
        db: Session,
        user_id: int,
        *,
        broker: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """OPEN-счета с флагом скрытия. Сначала включённые, внутри группы по имени."""
        accounts = self._build_accounts(
            db,
            user_id,
            [("dashboard_hidden", "asc"), ("account_name", "asc")],
        )
        for item in accounts:
            item.pop("_yesterday_value", None)
        token_types = list_open_account_token_types(db, user_id)
        for item in accounts:
            item["broker"] = resolve_account_broker(
                item.get("external_account_id"),
                token_types.get(int(item["account_id"])),
            )
        return filter_settings_accounts(
            accounts,
            broker=broker,
            currency=currency,
            token_types=token_types,
        )

    def build_dashboard(
        self,
        db: Session,
        user_id: int,
        sort_specs: List[Tuple[str, str]],
    ) -> Dict[str, Any]:
        visible = [
            item for item in self._build_accounts(db, user_id, sort_specs)
            if not item.get("dashboard_hidden")
        ]
        included_ids = [int(item["account_id"]) for item in visible]
        return {
            "totals": self._build_totals(visible),
            "assets": self._build_assets(db, user_id, included_ids),
            "accounts": visible,
        }


dashboard_service = DashboardService()
