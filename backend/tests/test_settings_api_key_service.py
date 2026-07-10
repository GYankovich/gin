from __future__ import annotations

import asyncio

from app.modules.settings.service import ApiKeyService


class _FakeBybitClient:
    def __init__(self, *args, **kwargs):
        self.testnet = kwargs.get("testnet", True)

    async def query_api(self):
        return {"retCode": 0, "result": {"apiKey": "api_key"}}

    async def close(self):
        return None


def test_test_key_bybit_requires_secret():
    service = ApiKeyService()

    async def _run():
        res = await service.test_key(token="key", key_type="bybit", token_secret=None)
        assert res["is_valid"] is False
        assert "secret" in str(res["message"]).lower()

    asyncio.run(_run())


def test_test_key_bybit_success(monkeypatch):
    import app.modules.settings.service as service_module

    monkeypatch.setattr(service_module, "BybitHttpClient", _FakeBybitClient)
    service = ApiKeyService()

    async def _run():
        res = await service.test_key(
            token="api_key",
            key_type="bybit",
            token_secret="api_secret",
            testnet=True,
            account_type="UNIFIED",
        )
        assert res["is_valid"] is True
        assert res["accounts_count"] == 1
        assert res["first_account"] == "mainnet"
        assert res["testnet"] is False

    asyncio.run(_run())
