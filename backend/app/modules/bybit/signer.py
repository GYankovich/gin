"""ByBit v5 request signing helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode


class BybitSigner:
    """HMAC signer for private ByBit REST v5 endpoints."""

    def __init__(self, api_key: str, api_secret: str, *, recv_window: int = 10000) -> None:
        self.api_key = str(api_key or "").strip()
        self.api_secret = str(api_secret or "").strip()
        self.recv_window = int(recv_window)

    @staticmethod
    def canonical_query(params: dict[str, object] | None) -> str:
        """Build query string in dict insertion order (must match the URL on the wire).

        ByBit v5 HMAC uses the raw queryString from the request. Do not alphabetically
        re-sort here — that desyncs sign vs httpx/params and yields retCode=10004.
        """
        if not params:
            return ""
        items: list[tuple[str, str]] = []
        for k, v in params.items():
            if v is None:
                continue
            items.append((str(k), str(v)))
        return urlencode(items)

    @staticmethod
    def canonical_body(payload: dict[str, object] | None) -> str:
        # ByBit v5 expects compact JSON string when signing POST payload.
        if not payload:
            return ""
        clean = {k: v for k, v in payload.items() if v is not None}
        return json.dumps(clean, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def sign(self, *, timestamp_ms: int, query_string: str = "", body_string: str = "") -> str:
        payload = f"{timestamp_ms}{self.api_key}{self.recv_window}{query_string}{body_string}"
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest

    def build_headers(
        self,
        *,
        timestamp_ms: int,
        signature: str,
    ) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(int(timestamp_ms)),
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
        }
