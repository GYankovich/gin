from __future__ import annotations

import asyncio

from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade


class _FakeBybitHttp:
    async def get_wallet_balance(self, *, account_type: str = "UNIFIED", coin: str | None = None):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "totalEquity": "1250.5",
                        "totalAvailableBalance": "500",
                        "coin": [
                            {"coin": "USDT", "walletBalance": "500", "availableToWithdraw": "500"},
                            {"coin": "BTC", "walletBalance": "0.01"},
                        ],
                    }
                ]
            },
        }

    async def get_positions(self, **kwargs):
        return {"retCode": 0, "result": {"list": []}}

    async def get_asset_overview(self, **kwargs):
        return {"retCode": 0, "result": {"list": []}}

    async def close(self):
        return None


def test_bybit_facade_portfolio_snapshot_shape():
    async def _run():
        b = ByBitBrokerFacade("key", http_client=_FakeBybitHttp())
        out = await b.get_portfolio("BYBIT_UNIFIED")
        await b.close()
        assert out["total_amount_portfolio"]["decimal"] == 1250.5
        assert out["total_amount_portfolio"]["currency"] == "USDT"
        tickers = [p["ticker"] for p in out["positions"]]
        assert "USDT" in tickers
        assert all(p["class_code"] == "BYBIT" for p in out["positions"] if p["ticker"] == "USDT")

    asyncio.run(_run())
