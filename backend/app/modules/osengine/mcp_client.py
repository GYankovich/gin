"""Minimal OsEngine MCP JSON-RPC client (v1 /api/v1/mcp, legacy tools/call envelope)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def normalize_osengine_mcp_url(url: str) -> str:
    """OsEngine HttpListener often rejects Host: 127.0.0.1 → use localhost."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return raw
    # Prefer hostname localhost so the Host header matches OsEngine bindings.
    if "://127.0.0.1" in raw:
        return raw.replace("://127.0.0.1", "://localhost", 1)
    if raw.startswith("127.0.0.1"):
        return "localhost" + raw[len("127.0.0.1") :]
    return raw


class OsEngineMcpError(RuntimeError):
    def __init__(self, message: str, *, code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.code = code
        self.payload = payload


class OsEngineMcpClient:
    """POST JSON-RPC → tools/call → parse Content[0].Text JSON."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._url = normalize_osengine_mcp_url(base_url or "")
        if (base_url or "").strip() and self._url != (base_url or "").strip().rstrip("/"):
            logger.info("osengine MCP URL normalized %s → %s", base_url, self._url)
        self._api_key = (api_key or "").strip() or None
        self._timeout = float(timeout)
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        if not self._url:
            raise OsEngineMcpError("OSENGINE_MCP_URL is empty")
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {},
            },
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key

        http = await self._http()
        try:
            resp = await http.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise OsEngineMcpError(f"OsEngine MCP HTTP error: {exc}") from exc

        if resp.status_code == 401:
            raise OsEngineMcpError("OsEngine MCP unauthorized (check OSENGINE_MCP_API_KEY)", code=401)
        if resp.status_code >= 400:
            raise OsEngineMcpError(
                f"OsEngine MCP HTTP {resp.status_code}: {resp.text[:300]}",
                code=resp.status_code,
            )

        try:
            body = resp.json()
        except json.JSONDecodeError as exc:
            raise OsEngineMcpError(f"OsEngine MCP non-JSON response: {resp.text[:300]}") from exc

        if isinstance(body, dict) and body.get("error"):
            err = body["error"] or {}
            raise OsEngineMcpError(
                str(err.get("message") or err),
                code=err.get("code") if isinstance(err, dict) else None,
                payload=err,
            )

        result = body.get("result") if isinstance(body, dict) else None
        parsed = _unwrap_tools_call_result(result)
        _raise_if_tool_error_object(parsed)
        return parsed

    async def data_get_sets(self) -> List[Dict[str, Any]]:
        raw = await self.call_tool("data_get_sets")
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict) and isinstance(raw.get("sets"), list):
            return [x for x in raw["sets"] if isinstance(x, dict)]
        return []

    async def data_create_set(
        self,
        *,
        name: str,
        source: str,
        source_name: str,
        timeframes: List[str],
        date_from: str,
        date_to: str,
    ) -> Any:
        return await self.call_tool(
            "data_create_set",
            {
                "name": name,
                "source": source,
                "source_name": source_name,
                "timeframes": timeframes,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    async def data_set_settings_set(
        self,
        *,
        name: str,
        settings: Dict[str, Any],
    ) -> Any:
        return await self.call_tool(
            "data_set_settings_set",
            {"name": name, "settings": settings},
        )

    async def data_set_securities_get(self, *, name: str) -> Any:
        return await self.call_tool("data_set_securities_get", {"name": name})

    async def data_set_securities_add(
        self,
        *,
        name: str,
        securities: List[Dict[str, Any]],
    ) -> Any:
        return await self.call_tool(
            "data_set_securities_add",
            {"name": name, "securities": securities},
        )

    async def data_set_on(self, *, name: str) -> Any:
        return await self.call_tool("data_set_on", {"name": name})

    async def data_set_off(self, *, name: str) -> Any:
        return await self.call_tool("data_set_off", {"name": name})

    async def data_get_set_status(self, *, name: str) -> Dict[str, Any]:
        raw = await self.call_tool("data_get_set_status", {"name": name})
        return raw if isinstance(raw, dict) else {"raw": raw}

    async def data_get_security_status(
        self,
        *,
        name: str,
        security: str,
        timeframe: str,
    ) -> Dict[str, Any]:
        raw = await self.call_tool(
            "data_get_security_status",
            {"name": name, "security": security, "timeframe": timeframe},
        )
        return raw if isinstance(raw, dict) else {"raw": raw}


def _unwrap_tools_call_result(result: Any) -> Any:
    """Legacy v1: {Content:[{Type,Text}], IsError} or camelCase content/isError."""
    if result is None:
        return None
    if not isinstance(result, dict):
        return result

    is_error = result.get("IsError")
    if is_error is None:
        is_error = result.get("isError")
    content = result.get("Content")
    if content is None:
        content = result.get("content")

    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {}
        text = first.get("Text")
        if text is None:
            text = first.get("text")
        if is_error:
            raise OsEngineMcpError(str(text or "OsEngine tools/call error"), payload=result)
        if isinstance(text, str):
            text_s = text.strip()
            if not text_s or text_s == "null":
                return None
            try:
                return json.loads(text_s)
            except json.JSONDecodeError:
                return text_s
        return text
    return result


def _raise_if_tool_error_object(parsed: Any) -> None:
    """OsData sometimes returns McpJsonRpcError as result payload."""
    if not isinstance(parsed, dict):
        return
    if "code" in parsed and "message" in parsed and "name" not in parsed and "status" not in parsed:
        code = parsed.get("code")
        if isinstance(code, int) and code < 0:
            raise OsEngineMcpError(str(parsed.get("message") or parsed), code=code, payload=parsed)


__all__ = ["OsEngineMcpClient", "OsEngineMcpError", "normalize_osengine_mcp_url"]
