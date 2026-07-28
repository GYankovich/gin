"""Live snapshot orders from portfolio_orders + Bybit sync helpers."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.portfolio import order_registry as preg
from app.modules.robots import service as svc
from app.modules.robots.service import _is_db_working_order, _split_db_orders
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_map_new_to_pending_not_open():
    assert Stage6Orders.map_execution_status_to_trade_status("EXECUTION_REPORT_STATUS_NEW") == "pending"
    assert Stage6Orders.map_execution_status_to_trade_status("EXECUTION_REPORT_STATUS_FILL") == "open"


def test_parse_broker_order_date_iso_and_ms():
    from datetime import datetime, timezone

    dt = preg.parse_broker_order_date("2026-07-17T17:46:00+00:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 7 and dt.day == 17
    ms = int(datetime(2026, 7, 17, 17, 46, tzinfo=timezone.utc).timestamp() * 1000)
    dt2 = preg.parse_broker_order_date(str(ms))
    assert dt2 is not None
    assert dt2.day == 17


def test_normalize_live_order_status():
    assert preg.normalize_live_order_status("New") == "pending"
    assert preg.normalize_live_order_status("PartiallyFilled") == "partial"
    assert preg.normalize_live_order_status("Filled") == "filled"
    assert preg.normalize_live_order_status("Cancelled") == "cancelled"
    assert preg.normalize_live_order_status("EXECUTION_REPORT_STATUS_FILL") == "filled"


def test_split_db_orders_active_vs_history():
    rows = [
        {"id": 1, "status": "pending", "order_id": "a", "filled_qty": None, "source": "manual"},
        {"id": 2, "status": "partial", "order_id": "b", "filled_qty": 1, "source": "robot"},
        {"id": 3, "status": "filled", "order_id": "c", "filled_qty": 10, "source": "external"},
        {"id": 4, "status": "cancelled", "order_id": "d", "filled_qty": 0},
        {"id": 5, "status": "rejected", "order_id": "pending:x", "filled_qty": None, "source": "manual"},
    ]
    open_orders, history = _split_db_orders(rows)
    assert [r["id"] for r in open_orders] == [1, 2]
    assert [r["id"] for r in history] == [3, 4, 5]
    assert _is_db_working_order(rows[0])
    assert not _is_db_working_order(rows[2])


def test_upsert_open_orders_inserts_missing():
    db = MagicMock()
    broker = MagicMock()
    broker.get_orders = AsyncMock(
        return_value=[
            {
                "order_id": "oid-new",
                "figi": "XLMUSDT",
                "side": "Buy",
                "quantity": 52,
                "price": 0.195,
                "status": "New",
                "filled_qty": 0,
            }
        ]
    )

    with patch(
        "app.modules.portfolio.order_registry.upsert_broker_order",
        return_value="inserted",
    ) as ups:
        res = asyncio.run(
            svc._upsert_broker_open_orders_into_db(
                db,
                robot_id=24,
                broker=broker,
                account_id="acct",
                portfolio_account_id=7,
            )
        )
    assert res["imported"] == 1
    assert res["upserted"] == 0
    assert "oid-new" in res["open_order_ids"]
    assert ups.called
    assert ups.call_args.kwargs.get("source") == "external"
    assert db.commit.called


def test_upsert_preserves_via_registry():
    db = MagicMock()
    broker = MagicMock()
    broker.get_orders = AsyncMock(
        return_value=[
            {
                "order_id": "oid-1",
                "figi": "XLMUSDT",
                "side": "Buy",
                "quantity": 52,
                "price": 0.195,
                "status": "PartiallyFilled",
                "filled_qty": 10,
            }
        ]
    )

    with patch(
        "app.modules.portfolio.order_registry.upsert_broker_order",
        return_value="updated",
    ) as ups:
        res = asyncio.run(
            svc._upsert_broker_open_orders_into_db(
                db,
                robot_id=24,
                broker=broker,
                account_id="acct",
                portfolio_account_id=7,
            )
        )
    assert res["upserted"] == 1
    assert ups.called


def test_upsert_requires_portfolio_account():
    db = MagicMock()
    broker = MagicMock()
    broker.get_orders = AsyncMock(return_value=[{"order_id": "x", "figi": "Y"}])

    res = asyncio.run(
        svc._upsert_broker_open_orders_into_db(
            db, robot_id=24, broker=broker, account_id="acct", portfolio_account_id=None
        )
    )
    assert res["imported"] == 0
    broker.get_orders.assert_not_called()


def test_sync_working_missing_marks_cancelled():
    db = MagicMock()
    broker = MagicMock()
    broker.get_order_state = AsyncMock(
        return_value={"orderId": "oid-gone", "stages": [], "symbol": None}
    )

    with patch(
        "app.modules.portfolio.order_registry.upsert_broker_order",
        return_value="updated",
    ) as ups:
        res = asyncio.run(
            svc._sync_working_trade_statuses_from_broker(
                db,
                robot_id=24,
                broker=broker,
                account_id="acct",
                working_rows=[{"order_id": "oid-gone", "status": "pending", "figi": "X", "side": "buy", "quantity": 1}],
                open_order_ids=set(),
                portfolio_account_id=7,
            )
        )
    assert res["updated"] == 1
    assert res["cancelled"] == 1
    assert ups.called


def test_history_insert_missing():
    db = MagicMock()
    broker = MagicMock()
    broker.get_order_history = AsyncMock(
        return_value=[
            {
                "order_id": "oid-new-hist",
                "figi": "TREEUSDT",
                "status": "Filled",
                "side": "Sell",
                "quantity": 10,
                "filled_qty": 10,
                "avg_price": 0.04,
            }
        ]
    )

    with patch(
        "app.modules.portfolio.order_registry.load_portfolio_orders",
        return_value=[],
    ), patch(
        "app.modules.portfolio.order_registry.upsert_broker_order",
        return_value="inserted",
    ) as ups:
        n = asyncio.run(
            svc._apply_broker_history_statuses_to_db(
                db,
                robot_id=24,
                broker=broker,
                account_id="acct",
                portfolio_account_id=7,
                insert_missing=True,
            )
        )
    assert n == 1
    assert ups.called


def test_history_update_only_skips_unknown():
    db = MagicMock()
    broker = MagicMock()
    broker.get_order_history = AsyncMock(
        return_value=[{"order_id": "unknown", "figi": "X", "status": "Filled"}]
    )

    with patch(
        "app.modules.portfolio.order_registry.load_portfolio_orders",
        return_value=[{"order_id": "known"}],
    ), patch(
        "app.modules.portfolio.order_registry.upsert_broker_order",
    ) as ups:
        n = asyncio.run(
            svc._apply_broker_history_statuses_to_db(
                db,
                robot_id=24,
                broker=broker,
                account_id="acct",
                portfolio_account_id=7,
                insert_missing=False,
            )
        )
    assert n == 0
    assert not ups.called


def test_reconcile_returns_full_stats(monkeypatch):
    async def fake_heal(*_a, **_k):
        return {"healed_open": 1, "healed_closed": 1}

    async def fake_upsert(*_a, **_k):
        return {
            "imported": 2,
            "upserted": 3,
            "skipped": 0,
            "open_order_ids": {"a"},
            "portfolio_account_id": 7,
        }

    async def fake_refresh(*_a, **_k):
        return {"updated": 1, "cancelled": 1}

    async def fake_hist(*_a, **_k):
        return 4

    monkeypatch.setattr(svc, "_heal_synthetic_broker_imports", fake_heal)
    monkeypatch.setattr(svc, "_upsert_broker_open_orders_into_db", fake_upsert)
    monkeypatch.setattr(svc, "_sync_working_trade_statuses_from_broker", fake_refresh)
    monkeypatch.setattr(svc, "_apply_broker_history_statuses_to_db", fake_hist)

    with patch(
        "app.modules.portfolio.order_registry.resolve_portfolio_account_pk",
        return_value=7,
    ), patch(
        "app.modules.portfolio.order_registry.load_portfolio_orders",
        return_value=[],
    ):
        stats = asyncio.run(
            svc._reconcile_robot_orders_with_broker(
                MagicMock(),
                robot_id=1,
                broker=MagicMock(),
                account_id="acct",
                user_id=9,
            )
        )
    assert stats["imported"] == 2
    assert stats["history_updated"] == 4
    assert stats["portfolio_account_id"] == 7


def test_sync_live_orders_inserts_history(monkeypatch):
    """Manual sync button must import missing broker history (not update-known-only)."""
    from app.modules.robots.service import RobotService

    robot_svc = RobotService()
    captured: dict = {}

    async def fake_reconcile(_db, **kwargs):
        captured.update(kwargs)
        return {
            "updated": 5,
            "imported": 0,
            "upserted": 0,
            "cancelled": 0,
            "history_updated": 5,
            "healed_open": 0,
            "healed_closed": 0,
        }

    robot = {
        "id": 24,
        "type": 2,
        "token": {"id": 1, "type": 3},
        "config": {"broker_type": "bybit", "account_id": "uid:UNIFIED"},
    }

    with patch.object(robot_svc, "get_robot_by_id", AsyncMock(return_value=robot)), patch(
        "app.modules.robots.service.token_service.get_token_by_id",
        AsyncMock(return_value={"token": "k", "extra_data": {}}),
    ), patch(
        "app.modules.robots.trading.brokers.create_broker_facade",
        return_value=MagicMock(),
    ), patch(
        "app.modules.robots.service._resolve_robot_account_id",
        AsyncMock(return_value="uid:UNIFIED"),
    ), patch(
        "app.modules.robots.trading.brokers.routing.enforce_broker_for_token",
        return_value="bybit",
    ), patch(
        "app.modules.robots.service._reconcile_robot_orders_with_broker",
        fake_reconcile,
    ), patch(
        "app.modules.robots.service._load_live_account_orders",
        return_value=[],
    ), patch(
        "app.modules.robots.service._split_db_orders",
        return_value=([], []),
    ):
        out = asyncio.run(robot_svc.sync_live_orders(MagicMock(), user_id=1, robot_id=24))

    assert captured.get("insert_history") is True
    assert out["history_updated"] == 5


def test_normalize_order_reason():
    assert preg.normalize_order_reason("stop_loss") == "stop_loss"
    assert preg.normalize_order_reason("Take Profit") == "take_profit"
    assert preg.normalize_order_reason(None, intent_source="entry") == "entry"
    assert preg.normalize_order_reason(None, intent_source="exit_sl_tp") == "exit_sl_tp"
    assert preg.normalize_order_reason("grain_seed_force_flatten") == "flatten"
    assert preg.normalize_order_reason(None, source=preg.SOURCE_MANUAL) == "manual"


def test_load_portfolio_orders_enriches_dictionary_names():
    from datetime import datetime, timezone

    db = MagicMock()
    order_row = (
        1,
        "XLMUSDT",
        "buy",
        10.0,
        0.2,
        "oid-1",
        "pending",
        datetime.now(timezone.utc),
        None,
        None,
        {"source": "manual"},
        "limit",
        "manual",
    )
    label_rows = [
        ("ORDER_DIRECTION", "buy", "Покупка"),
        ("ORDER_DIRECTION", "sell", "Продажа"),
        ("STATUS", "pending", "В работе"),
        ("STATUS", "filled", "Исполнена"),
        ("SOURCE", "manual", "Вручную"),
        ("SOURCE", "robot", "Робот"),
        ("SOURCE", "external", "Прочее"),
        ("REASON", "manual", "Вручную"),
        ("REASON", "stop_loss", "Стоп-лосс"),
    ]

    def _execute(query, _params=None):
        q = str(query)
        result = MagicMock()
        if "portfolio_orders" in q:
            result.fetchall.return_value = [order_row]
        elif "dictionary" in q:
            result.fetchall.return_value = label_rows
        else:
            result.fetchall.return_value = []
        return result

    db.execute.side_effect = _execute
    rows = preg.load_portfolio_orders(db, portfolio_account_id=7, limit=10)
    assert len(rows) == 1
    assert rows[0]["side"] == "buy"
    assert rows[0]["side_name"] == "Покупка"
    assert rows[0]["status"] == "pending"
    assert rows[0]["status_name"] == "В работе"
    assert rows[0]["source"] == "manual"
    assert rows[0]["source_name"] == "Вручную"
    assert rows[0]["reason"] == "manual"
    assert rows[0]["reason_name"] == "Вручную"


def test_manual_pending_insert_then_update():
    db = MagicMock()
    db.execute.return_value.first.return_value = (55,)
    rid = preg.insert_pending_order(
        db,
        portfolio_account_id=7,
        robot_id=24,
        figi="XLMUSDT",
        side="buy",
        quantity=10,
        price=0.2,
        source=preg.SOURCE_MANUAL,
        commit=True,
    )
    assert rid == 55
    assert db.execute.call_args[0][1]["status"] == "pending"

    db2 = MagicMock()
    assert preg.update_order_by_pk(
        db2, row_id=55, order_id="broker-1", status="pending", quantity=10, commit=True
    )
    assert db2.execute.call_args[0][1]["order_id"] == "broker-1"


def test_upsert_does_not_overwrite_manual_source():
    db = MagicMock()
    # find returns existing manual
    db.execute.return_value.first.return_value = (
        5,
        "pending",
        {"source": "manual", "robot_id": 24},
        "buy",
        "manual",
    )
    with patch.object(preg, "promote_filled_order_to_operation", return_value=True):
        result = preg.upsert_broker_order(
            db,
            portfolio_account_id=7,
            order_id="oid-1",
            figi="XLMUSDT",
            side="buy",
            quantity=10,
            status="PartiallyFilled",
            filled_qty=1,
            source=preg.SOURCE_EXTERNAL,
            commit=False,
            promote_filled=False,
        )
    assert result == "updated"
    extra = db.execute.call_args[0][1]["extra_data"]
    assert '"source": "manual"' in extra or '"source":"manual"' in extra.replace(" ", "")


def test_promote_filled_writes_order_operation():
    db = MagicMock()
    ok = preg.promote_filled_order_to_operation(
        db,
        portfolio_account_id=7,
        order_id="abc",
        figi="TREEUSDT",
        side="sell",
        quantity=197,
        price=0.04,
        order_date=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        broker_prefix="bybit",
        commit=True,
    )
    assert ok is True
    params = db.execute.call_args[0][1]
    assert params["operation_id"] == "bybit_order:abc"
    assert params["operation_type"] == "ORDER_SELL"
