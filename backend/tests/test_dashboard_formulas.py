"""Дашборд: день считается от вчерашнего снимка, не от любого предыдущего."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.dashboard.queries import build_assets_query, build_own_funds_query, build_yesterday_total_query
from app.modules.dashboard.schemas import DashboardAccountSummaryKpi
from app.modules.dashboard.service import (
    DashboardService,
    gain_vs_deposits_percent,
    resolve_day_change,
    shape_asset_allocation,
)

MOSCOW = ZoneInfo("Europe/Moscow")


def _at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MOSCOW)


def test_day_change_is_today_minus_yesterday_not_an_older_snapshot():
    now = _at(2026, 10, 12, 15)
    latest = _at(2026, 10, 12, 10)
    delta, base = resolve_day_change(latest, 100.0, 110.0, now=now)
    assert delta == 10.0
    assert base == 100.0
    # Пятничный снимок в понедельник — не «за день», даже если базу передали.
    friday = _at(2026, 10, 9, 18)
    assert resolve_day_change(friday, 90.0, 100.0, now=now) == (None, None)
    assert resolve_day_change(latest, None, 110.0, now=now) == (None, None)


def test_day_change_uses_moscow_calendar_not_utc_date():
    # 00:30 МСК понедельника = ещё воскресенье по UTC.
    now = _at(2026, 10, 12, 0, 30)
    latest = datetime(2026, 10, 11, 21, 40, tzinfo=timezone.utc)  # 00:40 МСК 12 октября
    delta, base = resolve_day_change(latest, 50.0, 55.0, now=now)
    assert delta == 5.0
    assert base == 50.0
    # Снимка за новые сутки ещё нет: последний закрытый день против предыдущего.
    sunday_evening = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)  # 23:00 МСК 11 октября
    delta, base = resolve_day_change(sunday_evening, 50.0, 55.0, now=now)
    assert delta == 5.0
    assert base == 50.0
    saturday = _at(2026, 10, 10, 23)
    assert resolve_day_change(saturday, 40.0, 50.0, now=now) == (None, None)


def test_yesterday_query_matches_exact_moscow_date():
    sql, params = build_yesterday_total_query(7, date(2026, 10, 11))
    assert "Europe/Moscow" in sql
    assert "= :yesterday" in sql
    assert "date_trunc" not in sql
    assert params == {"account_id": 7, "yesterday": date(2026, 10, 11)}


def test_own_funds_unknown_without_cashflows_and_no_fake_percent():
    sql, params = build_own_funds_query(3, "usdt")
    assert "SUM(signed_payment)" in sql
    assert "COALESCE" not in sql
    assert "OPERATION_TYPE_INP_MULTI" in sql
    assert "BYBIT_FUND_IN" in sql
    assert "BYBIT_TRANSFER_OUT" in sql
    assert "ABS(quantity)" in sql
    assert params["currency"] == "USDT"
    assert gain_vs_deposits_percent(1000.0, None) is None
    assert gain_vs_deposits_percent(1000.0, 0.0) is None
    assert gain_vs_deposits_percent(10.0, 100.0) == 10.0


def test_currency_day_percent_uses_yesterday_totals():
    accounts = [
        {
            "dashboard_hidden": False,
            "summary": DashboardAccountSummaryKpi(
                own_funds=100.0,
                value=160.0,
                minus_own_funds=60.0,
                currency="RUB",
                day_over_day_delta=10.0,
            ),
            "_yesterday_value": 100.0,
        }
    ]
    totals = DashboardService._build_totals(accounts)
    assert totals[0].total_day_over_day_delta == 10.0
    # 10 / 100, а не 10 / (160 - 10).
    assert totals[0].total_day_over_day_delta_percent == 10.0
    assert "_yesterday_value" not in accounts[0]


def test_currency_day_is_empty_when_any_account_has_no_yesterday():
    accounts = [
        {
            "dashboard_hidden": False,
            "summary": DashboardAccountSummaryKpi(
                own_funds=100.0,
                value=110.0,
                minus_own_funds=10.0,
                currency="RUB",
                day_over_day_delta=10.0,
            ),
            "_yesterday_value": 100.0,
        },
        {
            "dashboard_hidden": False,
            "summary": DashboardAccountSummaryKpi(
                own_funds=None,
                value=50.0,
                minus_own_funds=None,
                currency="RUB",
                day_over_day_delta=None,
            ),
            "_yesterday_value": None,
        },
    ]
    totals = DashboardService._build_totals(accounts)
    assert totals[0].total_value == 160.0
    assert totals[0].total_day_over_day_delta is None
    assert totals[0].total_day_over_day_delta_percent is None
    assert totals[0].total_own_funds is None
    assert totals[0].total_minus_own_funds is None


def test_account_without_currency_is_left_out_of_totals():
    accounts = [
        {
            "dashboard_hidden": False,
            "summary": DashboardAccountSummaryKpi(value=None, currency=None),
            "_yesterday_value": None,
        }
    ]
    assert DashboardService._build_totals(accounts) == []


def test_asset_buckets_follow_portfolio_value():
    rows = [
        {
            "type": "Акции РФ",
            "instrument_type": "share",
            "value": 70.0,
            "day_over_day_delta": 7.0,
            "currency": "RUB",
            "portfolio_total": 100.0,
        },
        {
            "type": "Деньги (кеш)",
            "instrument_type": "currency",
            "value": 30.0,
            "day_over_day_delta": None,
            "currency": "RUB",
            "portfolio_total": 100.0,
        },
    ]
    assets = shape_asset_allocation(rows)
    assert [a.type for a in assets] == ["Акции РФ", "Деньги (кеш)"]
    assert assets[0].percent == 70.0
    assert round(assets[0].day_over_day_delta_percent or 0, 4) == round(7 / 63 * 100, 4)


def test_asset_notional_collapses_to_cash_and_positions():
    rows = [
        {
            "type": "Деньги (кеш)",
            "instrument_type": "currency",
            "value": 800.0,
            "day_over_day_delta": 0.0,
            "currency": "USDT",
            "portfolio_total": 1000.0,
        },
        {
            "type": "Фьючерсы",
            "instrument_type": "future",
            "value": 5000.0,
            "day_over_day_delta": None,
            "currency": "USDT",
            "portfolio_total": 1000.0,
        },
    ]
    assets = shape_asset_allocation(rows)
    assert [(a.type, a.value, a.percent) for a in assets] == [
        ("Деньги", 800.0, 80.0),
        ("Позиции", 200.0, 20.0),
    ]
    assert all(a.day_over_day_delta is None for a in assets)


def test_assets_query_normalizes_futures_and_includes_sp():
    sql, _ = build_assets_query(1, [1])
    assert "WHEN 'futures' THEN 'future'" in sql
    assert "total_amount_sp" in sql
    assert "portfolio_total" in sql
    assert "::int" not in sql


def test_settings_accounts_sort_included_then_name():
    ordered = DashboardService()._sort_accounts(
        [
            {"account_name": "Бета", "dashboard_hidden": True, "summary": None},
            {"account_name": "альфа", "dashboard_hidden": False, "summary": None},
            {"account_name": "Гамма", "dashboard_hidden": False, "summary": None},
            {"account_name": "Альфа скрытая", "dashboard_hidden": True, "summary": None},
        ],
        [("dashboard_hidden", "asc"), ("account_name", "asc")],
    )
    assert [row["account_name"] for row in ordered] == ["альфа", "Гамма", "Альфа скрытая", "Бета"]


def test_settings_accounts_filter_by_broker_and_currency():
    from app.modules.dashboard.service import filter_settings_accounts, resolve_account_broker

    assert resolve_account_broker("bybit:UNIFIED", "1") == "bybit"
    assert resolve_account_broker("2000123456", "1") == "tinvest"
    assert resolve_account_broker("2000123456", "2") == "bybit"
    assert resolve_account_broker("2000123456", None) == "tinvest"

    items = [
        {"account_id": 1, "external_account_id": "2000123456", "summary": {"currency": "RUB"}},
        {"account_id": 2, "external_account_id": "bybit:UNIFIED", "summary": {"currency": "USDT"}},
        {"account_id": 3, "external_account_id": "2000999", "summary": {"currency": "USDT"}},
    ]
    types = {1: "1", 2: "2", 3: "2"}
    assert [row["account_id"] for row in filter_settings_accounts(items)] == [1, 2, 3]
    assert [row["account_id"] for row in filter_settings_accounts(items, currency="usdt")] == [2, 3]
    assert [row["account_id"] for row in filter_settings_accounts(items, broker="t-bank", token_types=types)] == [1]
    assert [row["account_id"] for row in filter_settings_accounts(items, broker="bybit", token_types=types)] == [2, 3]
    both = filter_settings_accounts(items, broker="bybit", currency="USDT", token_types=types)
    assert [row["account_id"] for row in both] == [2, 3]


def test_hidden_accounts_stay_out_of_cabinet_lists():
    from app.modules.analytics.queries import (
        build_account_ownership_check_query,
        build_accounts_summary_query,
    )
    from app.modules.tinvest.queries import build_get_accounts_list_query
    from app.modules.tinvest.service import TInvestService

    summary_sql, _ = build_accounts_summary_query(1)
    ownership_sql, _ = build_account_ownership_check_query(7, 1)
    assert "dashboard_hidden" in summary_sql
    assert "dashboard_hidden" in ownership_sql
    assert "dashboard_hidden" in build_get_accounts_list_query()
    empty = TInvestService._empty_portfolio()
    assert empty["account"] is None
    assert empty["portfolio"]["positions"] == []
