"""Tests for OsEngine MCP history pull (gaps → OsData → files)."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.modules.osengine.history_mcp import McpHistoryProvider
from app.modules.osengine.mcp_client import OsEngineMcpClient, OsEngineMcpError, _unwrap_tools_call_result
from app.modules.osengine.types import InstrumentKey, TimeRange


def test_unwrap_legacy_tools_call_result():
    raw = {
        "Content": [{"Type": "text", "Text": json.dumps({"name": "Set_Gin", "status": "Load", "percent_load": 100})}],
        "IsError": False,
    }
    parsed = _unwrap_tools_call_result(raw)
    assert parsed["name"] == "Set_Gin"
    assert parsed["status"] == "Load"


def test_unwrap_tools_call_error_raises():
    with pytest.raises(OsEngineMcpError):
        _unwrap_tools_call_result(
            {"Content": [{"Type": "text", "Text": "OsData mode is not open"}], "IsError": True}
        )


class _FakeMcp:
    def __init__(self) -> None:
        self.calls: List[tuple[str, Dict[str, Any]]] = []
        self.sets: List[Dict[str, Any]] = []
        self.securities: List[str] = []
        self.status_queue: List[Dict[str, Any]] = [
            {"status": "Loading", "percent_load": 10},
            {"status": "Load", "percent_load": 100},
        ]
        self.settings: Dict[str, Any] = {
            "name": "Set_GinHistory",
            "date_from": "2024-01-01",
            "date_to": "2024-01-05",
            "timeframes": ["Min1"],
        }

    async def data_get_sets(self) -> List[Dict[str, Any]]:
        self.calls.append(("data_get_sets", {}))
        return list(self.sets)

    async def data_create_set(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_create_set", kwargs))
        self.sets.append({"name": f"Set_{kwargs['name']}"})
        return {"name": f"Set_{kwargs['name']}"}

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append((name, arguments or {}))
        if name == "data_set_settings_get":
            return dict(self.settings)
        raise OsEngineMcpError(f"unexpected tool {name}")

    async def data_set_settings_set(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_set_settings_set", kwargs))
        return {"ok": True}

    async def data_set_securities_get(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_set_securities_get", kwargs))
        return {"securities": [{"name": n} for n in self.securities]}

    async def data_set_securities_add(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_set_securities_add", kwargs))
        for s in kwargs.get("securities") or []:
            self.securities.append(str(s.get("name") or "").upper())
        return {"ok": True}

    async def data_set_on(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_set_on", kwargs))
        return {"ok": True}

    async def data_get_security_status(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_get_security_status", kwargs))
        if self.status_queue:
            return self.status_queue.pop(0)
        return {"status": "Load", "percent_load": 100}

    async def data_get_set_status(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("data_get_set_status", kwargs))
        return {"status": "Load", "percent_load": 100}


class _FakeFiles:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def fetch_candle_gaps(self, db, *, instrument, interval, gaps) -> int:
        self.calls.append(
            {
                "instrument": instrument.cache_id,
                "interval": interval,
                "gaps": [(g.start, g.end) for g in gaps],
            }
        )
        return 7


def test_mcp_history_create_set_wait_and_import():
    mcp = _FakeMcp()
    files = _FakeFiles()
    provider = McpHistoryProvider(
        mcp=mcp,  # type: ignore[arg-type]
        files=files,  # type: ignore[arg-type]
        set_name="GinHistory",
        source="TInvest",
        source_name="TInvest",
        poll_interval=0.01,
        timeout=5.0,
    )

    n = asyncio.run(
        provider.fetch_candle_gaps(
            MagicMock(),
            instrument=InstrumentKey("SBER"),
            interval="I1",
            gaps=[TimeRange(date(2024, 1, 10), date(2024, 1, 12))],
        )
    )
    assert n == 7
    assert any(c[0] == "data_create_set" for c in mcp.calls)
    assert any(c[0] == "data_set_on" for c in mcp.calls)
    assert any(c[0] == "data_set_securities_add" for c in mcp.calls)
    assert files.calls and files.calls[0]["instrument"] == "SBER"


def test_mcp_history_reuses_set_and_expands_window():
    mcp = _FakeMcp()
    mcp.sets = [{"name": "Set_GinHistory"}]
    mcp.securities = ["SBER"]
    files = _FakeFiles()
    provider = McpHistoryProvider(
        mcp=mcp,  # type: ignore[arg-type]
        files=files,  # type: ignore[arg-type]
        set_name="GinHistory",
        poll_interval=0.01,
        timeout=5.0,
    )

    asyncio.run(
        provider.fetch_candle_gaps(
            MagicMock(),
            instrument=InstrumentKey("SBER"),
            interval="I1",
            gaps=[TimeRange(date(2024, 1, 8), date(2024, 1, 15))],
        )
    )
    assert not any(c[0] == "data_create_set" for c in mcp.calls)
    assert any(c[0] == "data_set_settings_set" for c in mcp.calls)
    assert not any(c[0] == "data_set_securities_add" for c in mcp.calls)


def test_mcp_history_still_imports_if_mcp_fails():
    mcp = _FakeMcp()

    async def _boom(**_kwargs):
        raise OsEngineMcpError("OsData mode is not open", code=-32001)

    mcp.data_get_sets = _boom  # type: ignore[method-assign]
    files = _FakeFiles()
    provider = McpHistoryProvider(
        mcp=mcp,  # type: ignore[arg-type]
        files=files,  # type: ignore[arg-type]
        poll_interval=0.01,
        timeout=1.0,
    )
    n = asyncio.run(
        provider.fetch_candle_gaps(
            MagicMock(),
            instrument=InstrumentKey("GAZP"),
            interval="D1",
            gaps=[TimeRange(date(2024, 2, 1), date(2024, 2, 5))],
        )
    )
    assert n == 7
    assert files.calls[0]["instrument"] == "GAZP"


def test_mcp_history_reports_download_percent():
    mcp = _FakeMcp()
    files = _FakeFiles()
    seen: list[float] = []
    provider = McpHistoryProvider(
        mcp=mcp,  # type: ignore[arg-type]
        files=files,  # type: ignore[arg-type]
        set_name="GinHistory",
        poll_interval=0.01,
        timeout=5.0,
    )
    asyncio.run(
        provider.fetch_candle_gaps(
            MagicMock(),
            instrument=InstrumentKey("SBER"),
            interval="I1",
            gaps=[TimeRange(date(2024, 1, 10), date(2024, 1, 12))],
            progress_callback=seen.append,
        )
    )
    assert 10.0 in seen
    assert 100.0 in seen


def test_mcp_client_posts_tools_call():
    captured: Dict[str, Any] = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "Content": [{"Type": "text", "Text": '{"ok": true}'}],
                    "IsError": False,
                },
            }

    class _Client:
        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

        async def aclose(self):
            return None

    client = OsEngineMcpClient(
        base_url="http://127.0.0.1:6500/api/v1/mcp",
        api_key="test-key",
        client=_Client(),  # type: ignore[arg-type]
    )
    out = asyncio.run(client.call_tool("data_get_sets", {}))
    assert out == {"ok": True}
    assert captured["headers"]["X-Api-Key"] == "test-key"
    assert captured["json"]["method"] == "tools/call"
    assert captured["json"]["params"]["name"] == "data_get_sets"
