from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade


class _FakeBybitHttp:
    def __init__(self):
        self._orders = {}
        self._seq = 0

    async def get_wallet_balance(self, *, account_type: str = "UNIFIED", coin: str | None = None):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "totalEquity": "0",
                        "totalAvailableBalance": "777.7",
                        "coin": [{"coin": "USDT", "availableToWithdraw": "123.45", "walletBalance": "123.45"}],
                    }
                ]
            },
        }

    async def get_asset_overview(self, **kwargs):
        return {"retCode": 0, "result": {"list": [{"accountType": "UNIFIED", "totalEquity": "0", "categories": []}]}}

    async def get_all_coins_balance(self, **kwargs):
        return {"retCode": 0, "result": {"balance": []}}

    async def get_transaction_log(self, **kwargs):
        return {"retCode": 0, "result": {"list": [], "nextPageCursor": ""}}

    async def get_inter_transfer_list(self, **kwargs):
        self.last_inter_transfer_kwargs = dict(kwargs)
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "transferId": "selfTransfer_fund_in",
                        "coin": "USDT",
                        "amount": "100",
                        "fromAccountType": "UNIFIED",
                        "toAccountType": "FUND",
                        "timestamp": "1700000000000",
                        "status": "SUCCESS",
                    },
                    {
                        "transferId": "selfTransfer_spot_only",
                        "coin": "USDT",
                        "amount": "50",
                        "fromAccountType": "SPOT",
                        "toAccountType": "UNIFIED",
                        "timestamp": "1700000001000",
                        "status": "SUCCESS",
                    },
                    {
                        "transferId": "selfTransfer_fund_out",
                        "coin": "USDT",
                        "amount": "25",
                        "fromAccountType": "FUND",
                        "toAccountType": "UNIFIED",
                        "timestamp": "1700000002000",
                        "status": "SUCCESS",
                    },
                ],
                "nextPageCursor": "",
            },
        }

    async def get_asset_funding_history(self, **kwargs):
        self.last_funding_history_kwargs = dict(kwargs)
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "memberId": "290118",
                        "currency": "BTC",
                        "ioDirection": "I",
                        "txnAmt": "0.001",
                        "afterAmt": "1.0",
                        "createTime": "1700000100",
                        "showBusiTypeEn": "Earn",
                        "descriptionEn": "Easy Earn",
                    },
                    {
                        "memberId": "290118",
                        "currency": "USDT",
                        "ioDirection": "O",
                        "txnAmt": "10",
                        "afterAmt": "90",
                        "createTime": "1700000200",
                        "showBusiTypeEn": "Transfer",
                        "descriptionEn": "Internal Transfer",
                    },
                ],
                "nextPageCursor": "",
            },
        }

    async def get_positions(self, **kwargs):
        return {"retCode": 0, "result": {"list": []}}

    async def get_kline(self, *, category: str, symbol: str, interval: str, start_ms: int | None, end_ms: int | None, limit: int):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    [str(start_ms or 0), "10", "12", "9", "11", "100", "1100"],
                    [str((start_ms or 0) + 60_000), "11", "13", "10", "12", "120", "1400"],
                ]
            },
        }

    async def close(self):
        return None

    async def create_order(
        self,
        *,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
    ):
        _ = (category, time_in_force, reduce_only)
        self._seq += 1
        oid = f"oid-{self._seq}"
        self._orders[oid] = {
            "orderId": oid,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "orderStatus": "New",
            "cumExecQty": "0",
            "avgPrice": price or "0",
            "cumExecFee": "0",
            "reduceOnly": bool(reduce_only),
        }
        return {"retCode": 0, "result": {"orderId": oid}}

    async def get_open_orders(self, *, category: str, symbol: str | None = None, order_id: str | None = None, settle_coin: str | None = None):
        _ = (category, settle_coin)
        rows = [r for r in self._orders.values() if r.get("orderStatus") in {"New", "PartiallyFilled"}]
        if order_id:
            rows = [r for r in rows if r.get("orderId") == order_id]
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        return {"retCode": 0, "result": {"list": rows}}

    async def get_order_history(self, *, category: str, symbol: str | None = None, order_id: str | None = None, limit: int = 50):
        _ = (category, limit)
        rows = list(self._orders.values())
        if order_id:
            rows = [r for r in rows if r.get("orderId") == order_id]
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        return {"retCode": 0, "result": {"list": rows}}

    async def get_instruments_info(self, *, category: str, symbol: str | None = None, limit: int = 200, cursor: str | None = None):
        _ = (category, limit, cursor)
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": symbol or "BTCUSDT",
                        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"},
                    }
                ]
            },
        }

    async def cancel_order(self, *, category: str, symbol: str, order_id: str):
        _ = (category, symbol)
        row = self._orders.get(order_id)
        if row:
            row["orderStatus"] = "Cancelled"
        return {"retCode": 0, "result": {"orderId": order_id}}

    def mark_filled(self, order_id: str, *, cum_qty: str | None = None):
        row = self._orders.get(order_id)
        if not row:
            return
        row["orderStatus"] = "Filled"
        row["cumExecQty"] = cum_qty or row.get("qty") or "0"
        row["avgPrice"] = row.get("avgPrice") or "1"


class _FakeBybitWs:
    def __init__(self, recv_payloads: list[dict] | None = None):
        self.subscribed: list[tuple[list[str], str]] = []
        self._recv_payloads = list(recv_payloads or [])

    async def connect(self):
        return None

    async def subscribe_klines(self, *, symbols, interval):
        self.subscribed.append((list(symbols), str(interval)))

    async def recv_json(self, timeout_seconds: float = 1.0):
        _ = timeout_seconds
        await asyncio.sleep(0)
        if self._recv_payloads:
            return self._recv_payloads.pop(0)
        return None

    async def close(self):
        return None


def _real_bybit_kline_payload() -> dict:
    return {
        "topic": "kline.5.BTCUSDT",
        "type": "snapshot",
        "ts": 1672324988882,
        "data": [
            {
                "start": 1672324800000,
                "end": 1672325099999,
                "interval": "5",
                "open": "100",
                "close": "105",
                "high": "110",
                "low": "90",
                "volume": "1",
                "turnover": "100",
                "confirm": False,
                "timestamp": 1672324988882,
            }
        ],
    }


def test_bybit_account_id_stable_without_token_prefix():
    b = ByBitBrokerFacade("rXr4Mn4MbynYKEYREST")
    assert b.make_account_id("UNIFIED") == "bybit:UNIFIED"
    assert b.make_account_id("fund") == "bybit:FUND"
    assert b.make_account_id("COPY") == "bybit:COPY"
    assert b.parse_account_kind("bybit:UNIFIED") == "UNIFIED"
    assert b.parse_account_kind("bybit:rXr4Mn4MbynY:FUND") == "FUND"  # legacy still parses
    assert b.parse_account_kind("BYBIT_UNIFIED") == "UNIFIED"


def test_bybit_get_orders_only_for_unified_account():
    async def _run():
        http = _FakeBybitHttp()
        b = ByBitBrokerFacade("key", http_client=http, ws_client=_FakeBybitWs())
        await b.post_order(
            figi="BTCUSDT",
            quantity=1,
            price=65000.0,
            direction="ORDER_DIRECTION_BUY",
            account_id="bybit:UNIFIED",
        )
        unified = await b.get_orders("bybit:UNIFIED")
        fund = await b.get_orders("bybit:FUND")
        copy = await b.get_orders("bybit:COPY")
        hist_fund = await b.get_order_history("bybit:FUND", limit=10)
        hist_unified = await b.get_order_history("bybit:UNIFIED", limit=10)
        await b.close()
        assert len(unified) == 1
        assert fund == []
        assert copy == []
        assert hist_fund == []
        assert len(hist_unified) == 1

    asyncio.run(_run())


def test_bybit_broker_get_accounts_and_funds():
    async def _run():
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp())
        acc = await b.get_accounts()
        unified = next(a for a in acc if a["type"] == "UNIFIED")
        portfolio = await b.get_portfolio(unified["id"])
        free = await b.get_free_funds(unified["id"])
        await b.close()
        assert unified["id"] == "bybit:UNIFIED"
        assert {a["id"] for a in acc} >= {"bybit:UNIFIED", "bybit:FUND", "bybit:COPY"}
        assert {a["type"] for a in acc} >= {"UNIFIED", "FUND", "COPY"}
        assert portfolio["total_amount_portfolio"]["decimal"] == 0.0
        assert isinstance(portfolio["positions"], list)
        assert free == 123.45

    asyncio.run(_run())


def test_bybit_broker_get_candles_mapping():
    async def _run():
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp())
        from_dt = datetime.now(timezone.utc) - timedelta(hours=1)
        to_dt = datetime.now(timezone.utc)
        candles = await b.get_candles("BTCUSDT", from_dt, to_dt, "CANDLE_INTERVAL_1_MIN")
        await b.close()
        assert len(candles) == 2
        assert candles[0]["open"] == 10.0
        assert candles[1]["close"] == 12.0

    asyncio.run(_run())


def test_bybit_broker_fund_get_operations():
    async def _run():
        http = _FakeBybitHttp()
        b = ByBitBrokerFacade("key", http_client=http)
        from_dt = datetime(2023, 11, 1, tzinfo=timezone.utc)
        to_dt = datetime(2023, 11, 20, tzinfo=timezone.utc)
        ops = await b.get_operations("bybit:FUND", from_dt, to_dt, max_pages=4)
        await b.close()

        assert len(ops) == 3  # 2 FUND transfers + 1 Earn (Transfer fundinghistory skipped)
        by_id = {o["id"]: o for o in ops}
        assert by_id["bybit:xfer:selfTransfer_fund_in"]["payment"]["decimal"] == 100.0
        assert by_id["bybit:xfer:selfTransfer_fund_out"]["payment"]["decimal"] == -25.0
        earn = next(o for o in ops if o["type"].startswith("FUND_IN_EARN"))
        assert earn["payment"]["decimal"] == 0.001
        assert earn["currency"] == "BTC"
        assert not any(o["type"].startswith("FUND_OUT_TRANSFER") for o in ops)

    asyncio.run(_run())


def test_bybit_broker_copy_get_operations_empty():
    async def _run():
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp())
        ops = await b.get_operations(
            "bybit:COPY",
            datetime.now(timezone.utc) - timedelta(days=1),
            datetime.now(timezone.utc),
        )
        await b.close()
        assert ops == []

    asyncio.run(_run())


def test_bybit_broker_subscribe_prices_uses_crypto_interval():
    async def _run():
        ws = _FakeBybitWs()
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp(), ws_client=ws)
        q = asyncio.Queue(maxsize=10)
        res = await b.subscribe_prices(user_id=1, figis=["BTCUSDT"], queue=q, candle_interval="15m")
        await b.close()
        assert res["BTCUSDT"] in {"SUBSCRIBE_SENT", "ALREADY_SUBSCRIBED"}
        assert ws.subscribed
        assert ws.subscribed[0][1] == "15"

    asyncio.run(_run())


def test_bybit_broker_ws_kline_routes_symbol_from_topic():
    async def _run():
        ws = _FakeBybitWs(recv_payloads=[_real_bybit_kline_payload()])
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp(), ws_client=ws)
        q = asyncio.Queue(maxsize=10)
        await b.subscribe_prices(user_id=1, figis=["BTCUSDT"], queue=q)
        for _ in range(30):
            if not q.empty():
                break
            await asyncio.sleep(0.05)
        assert not q.empty()
        event = q.get_nowait()
        assert event["figi"] == "BTCUSDT"
        assert event["price"] == 105.0
        await b.close()

    asyncio.run(_run())


def test_bybit_broker_execution_mapping_market_limit_and_status():
    async def _run():
        http = _FakeBybitHttp()
        b = ByBitBrokerFacade("key", http_client=http, ws_client=_FakeBybitWs())
        limit_order = await b.post_order(
            figi="BTCUSDT",
            quantity=2,
            price=65000.0,
            direction="ORDER_DIRECTION_BUY",
            account_id="BYBIT_UNIFIED",
        )
        market_order = await b.post_market_order(
            figi="ETHUSDT",
            quantity=1,
            direction="ORDER_DIRECTION_SELL",
            account_id="BYBIT_UNIFIED",
        )
        state = await b.get_order_state("BYBIT_UNIFIED", str(limit_order["orderId"]))
        orders = await b.get_orders("BYBIT_UNIFIED")
        cancelled = await b.cancel_order("BYBIT_UNIFIED", str(limit_order["orderId"]))
        await b.close()

        assert limit_order["executionReportStatus"] == "EXECUTION_REPORT_STATUS_NEW"
        assert market_order["executionReportStatus"] == "EXECUTION_REPORT_STATUS_NEW"
        assert state["executionReportStatus"] == "EXECUTION_REPORT_STATUS_NEW"
        assert cancelled["executionReportStatus"] == "EXECUTION_REPORT_STATUS_CANCELLED"
        assert any(o.get("order_id") == limit_order["orderId"] for o in orders)

    asyncio.run(_run())


def test_bybit_fractional_qty_and_fill_from_history():
    async def _run():
        http = _FakeBybitHttp()
        b = ByBitBrokerFacade("key", http_client=http, ws_client=_FakeBybitWs())
        order = await b.post_order(
            figi="BTCUSDT",
            quantity=0.0035,  # floors to 0.003 with qtyStep 0.001
            price=65000.0,
            direction="ORDER_DIRECTION_BUY",
            account_id="bybit:UNIFIED",
        )
        oid = str(order["orderId"])
        assert http._orders[oid]["qty"] == "0.003"

        http.mark_filled(oid)
        state = await b.get_order_state("bybit:UNIFIED", oid)
        assert state["executionReportStatus"] == "EXECUTION_REPORT_STATUS_FILL"
        assert state["lotsExecuted"] == 0.003
        assert state["symbol"] == "BTCUSDT"

        # Cancel without cached symbol still resolves via history.
        b2 = ByBitBrokerFacade("key", http_client=http, ws_client=_FakeBybitWs())
        cancelled = await b2.cancel_order("bybit:UNIFIED", oid)
        assert cancelled["executionReportStatus"] == "EXECUTION_REPORT_STATUS_CANCELLED"
        await b.close()
        await b2.close()

    asyncio.run(_run())


def test_bybit_cancel_refuses_unknown_symbol_fallback():
    async def _run():
        http = _FakeBybitHttp()
        b = ByBitBrokerFacade("key", http_client=http, ws_client=_FakeBybitWs())
        try:
            await b.cancel_order("bybit:UNIFIED", "missing-oid")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "BTCUSDT fallback" in str(exc)
        await b.close()

    asyncio.run(_run())
