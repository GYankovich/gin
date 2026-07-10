"""Async ByBit REST v5 client (Phase R4.1 foundation)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from .environment import bybit_use_testnet
from .signer import BybitSigner

BYBIT_API_MAINNET = "https://api.bybit.com"


class BybitApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, ret_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.ret_code = ret_code


class BybitHttpClient:
    """Thin HTTP client for ByBit public/private REST endpoints."""

    def __init__(
        self,
        *,
        testnet: bool = False,
        api_key: str | None = None,
        api_secret: str | None = None,
        user_id: int | None = None,
        token_id: int | None = None,
        context_type: str | None = "bybit_http",
        context_ref: str | None = None,
        recv_window: int = 5000,
        timeout_seconds: float = 20.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        del testnet  # mainnet-only; kept for call-site compatibility
        self.testnet = bybit_use_testnet()
        self.base_url = BYBIT_API_MAINNET
        self.timeout_seconds = float(timeout_seconds)
        self._http = http_client
        self._own_http = http_client is None
        self._user_id = int(user_id) if user_id is not None else None
        self._token_id = int(token_id) if token_id is not None else None
        self._context_type = str(context_type or "").strip() or None
        self._context_ref = str(context_ref or "").strip() or None
        self._signer: BybitSigner | None = None
        if api_key and api_secret:
            self._signer = BybitSigner(api_key, api_secret, recv_window=recv_window)

    async def close(self) -> None:
        if self._http is not None and self._own_http:
            await self._http.aclose()

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                verify=False,
            )
            self._own_http = True
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        auth: bool = False,
    ) -> dict[str, Any]:
        method_u = str(method or "GET").upper()
        # Preserve insertion order for GET: ByBit verifies HMAC against the wire
        # query string (see retCode=10004 origin_string). Sorting for sign while
        # httpx sends dict order caused 10004 on multi-param GETs (transaction-log).
        request_params = {str(k): v for k, v in (params or {}).items() if v is not None}
        request_payload = {str(k): v for k, v in (payload or {}).items() if v is not None}
        headers: dict[str, str] = {"Accept": "application/json"}
        body_string = BybitSigner.canonical_body(request_payload if method_u != "GET" else None)
        query_string = ""
        if method_u == "GET" and request_params:
            query_string = BybitSigner.canonical_query(request_params)

        if auth:
            if self._signer is None:
                raise BybitApiError("ByBit private endpoint requires api_key/api_secret")
            ts = int(time.time() * 1000)
            sign = self._signer.sign(
                timestamp_ms=ts,
                query_string=query_string if method_u == "GET" else "",
                body_string=body_string,
            )
            headers.update(self._signer.build_headers(timestamp_ms=ts, signature=sign))

        url = f"{self.base_url}{path}"
        # Auth GET: append the exact query we signed so wire == HMAC payload.
        if method_u == "GET" and auth and query_string:
            url = f"{url}?{query_string}"
        http = await self._ensure_http()
        max_retries = 6
        last_error: BybitApiError | None = None
        body_bytes: bytes | None = None
        if method_u != "GET" and request_payload and auth:
            body_bytes = body_string.encode("utf-8")
        for attempt in range(max_retries):
            started_at = datetime.now(timezone.utc)
            resp = await http.request(
                method_u,
                url,
                params=(request_params if request_params and not (method_u == "GET" and auth) else None),
                content=body_bytes,
                json=request_payload if (method_u != "GET" and request_payload and body_bytes is None) else None,
                headers=headers,
            )
            finished_at = datetime.now(timezone.utc)
            if resp.status_code >= 400:
                detail = (resp.text or "").strip()
                if resp.status_code == 401 and not detail:
                    detail = "неверный API Key/Secret ByBit mainnet"
                self._log_external_api_call(
                    endpoint=path,
                    request_data={"method": method_u, "params": request_params, "payload": request_payload},
                    response_status=int(resp.status_code),
                    response_data={"body": detail[:2000]},
                    started_at=started_at,
                    finished_at=finished_at,
                    success=False,
                    error_message=f"HTTP {resp.status_code}: {detail[:500]}",
                )
                raise BybitApiError(
                    f"ByBit HTTP error {resp.status_code}: {detail[:300]}",
                    status_code=resp.status_code,
                )
            data = resp.json() if resp.text else {}
            ret_code = int(data.get("retCode", 0) or 0)
            if ret_code == 0:
                self._log_external_api_call(
                    endpoint=path,
                    request_data={"method": method_u, "params": request_params, "payload": request_payload},
                    response_status=int(resp.status_code),
                    response_data={"retCode": ret_code, "retMsg": data.get("retMsg")},
                    started_at=started_at,
                    finished_at=finished_at,
                    success=True,
                    error_message=None,
                )
                return data
            last_error = BybitApiError(
                f"ByBit API error retCode={ret_code}: {data.get('retMsg')}",
                status_code=resp.status_code,
                ret_code=ret_code,
            )
            self._log_external_api_call(
                endpoint=path,
                request_data={"method": method_u, "params": request_params, "payload": request_payload},
                response_status=int(resp.status_code),
                response_data={"retCode": ret_code, "retMsg": data.get("retMsg")},
                started_at=started_at,
                finished_at=finished_at,
                success=False,
                error_message=str(last_error)[:500],
            )
            if ret_code == 10006 and attempt < max_retries - 1:
                await asyncio.sleep(min(60.0, 2.0 ** attempt + 0.5))
                continue
            raise last_error
        if last_error is not None:
            raise last_error
        return {}

    def _log_external_api_call(
        self,
        *,
        endpoint: str,
        request_data: dict[str, Any],
        response_status: int | None,
        response_data: dict[str, Any] | None,
        started_at: datetime,
        finished_at: datetime,
        success: bool,
        error_message: str | None,
    ) -> None:
        duration_ms = int(max(0.0, (finished_at - started_at).total_seconds() * 1000.0))
        db = SessionLocal()
        try:
            db.execute(
                text(
                    f"""
                    INSERT INTO {settings.DB_SCHEMA}.external_api_logs (
                        user_id, token_id, broker, context_type, context_ref,
                        endpoint, request_data, response_status, response_data,
                        started_at, finished_at, duration_ms, success, error_message
                    ) VALUES (
                        :user_id, :token_id, 'bybit', :context_type, :context_ref,
                        :endpoint, CAST(:request_data AS jsonb), :response_status, CAST(:response_data AS jsonb),
                        :started_at, :finished_at, :duration_ms, :success, :error_message
                    )
                    """
                ),
                {
                    "user_id": self._user_id,
                    "token_id": self._token_id,
                    "context_type": self._context_type,
                    "context_ref": self._context_ref,
                    "endpoint": f"{self.base_url}{endpoint}",
                    "request_data": json.dumps(request_data, ensure_ascii=False, default=str),
                    "response_status": response_status,
                    "response_data": json.dumps(response_data or {}, ensure_ascii=False, default=str),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "success": 1 if success else 0,
                    "error_message": (error_message or "")[:2000] or None,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def get_server_time(self) -> dict[str, Any]:
        return await self._request("GET", "/v5/market/time")

    async def query_api(self) -> dict[str, Any]:
        """Validate API key credentials (any permission level)."""
        return await self._request("GET", "/v5/user/query-api", auth=True)

    async def get_kline(
        self,
        *,
        category: str,
        symbol: str,
        interval: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/market/kline",
            params={
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "start": start_ms,
                "end": end_ms,
                "limit": int(limit),
            },
            auth=False,
        )

    async def get_wallet_balance(
        self,
        *,
        account_type: str = "UNIFIED",
        coin: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/account/wallet-balance",
            params={"accountType": account_type, "coin": coin},
            auth=True,
        )

    async def get_asset_overview(
        self,
        *,
        account_type: str | None = None,
        member_id: str | None = None,
        valuation_currency: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/asset/asset-overview",
            params={
                "accountType": account_type,
                "memberId": member_id,
                "valuationCurrency": valuation_currency,
            },
            auth=True,
        )

    async def get_all_coins_balance(
        self,
        *,
        account_type: str,
        coin: str | None = None,
        member_id: str | None = None,
        with_bonus: int = 0,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/asset/transfer/query-account-coins-balance",
            params={
                "accountType": account_type,
                "coin": coin,
                "memberId": member_id,
                "withBonus": int(with_bonus),
            },
            auth=True,
        )

    async def get_transaction_log(
        self,
        *,
        account_type: str = "UNIFIED",
        category: str | None = None,
        currency: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
        type: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/account/transaction-log",
            params={
                "accountType": account_type,
                "category": category,
                "currency": currency,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": int(limit),
                "cursor": cursor,
                "type": type,
            },
            auth=True,
        )

    async def get_inter_transfer_list(
        self,
        *,
        transfer_id: str | None = None,
        coin: str | None = None,
        status: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Internal transfers between account types under the same UID."""
        return await self._request(
            "GET",
            "/v5/asset/transfer/query-inter-transfer-list",
            params={
                "transferId": transfer_id,
                "coin": coin,
                "status": status,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": int(limit),
                "cursor": cursor,
            },
            auth=True,
        )

    async def get_asset_funding_history(
        self,
        *,
        create_time_from_s: int | None = None,
        create_time_to_s: int | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Funding account transaction ledger (window ≤ 7 days; times in seconds)."""
        return await self._request(
            "GET",
            "/v5/asset/fundinghistory",
            params={
                "createTimeFrom": str(create_time_from_s) if create_time_from_s is not None else None,
                "createTimeTo": str(create_time_to_s) if create_time_to_s is not None else None,
                "limit": str(int(limit)),
                "cursor": cursor,
            },
            auth=True,
        )

    async def get_positions(
        self,
        *,
        category: str = "linear",
        symbol: str | None = None,
        settle_coin: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if settle_coin:
            params["settleCoin"] = settle_coin
        return await self._request(
            "GET",
            "/v5/position/list",
            params=params,
            auth=True,
        )

    async def get_instruments_info(
        self,
        *,
        category: str,
        symbol: str | None = None,
        limit: int = 200,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/market/instruments-info",
            params={
                "category": category,
                "symbol": symbol,
                "limit": int(limit),
                "cursor": cursor,
            },
        )

    async def get_tickers(
        self,
        *,
        category: str,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/market/tickers",
            params={
                "category": category,
                "symbol": symbol,
            },
        )

    async def get_funding_history(
        self,
        *,
        category: str,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/market/funding/history",
            params={
                "category": category,
                "symbol": symbol,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": int(limit),
            },
            auth=False,
        )

    async def get_open_interest(
        self,
        *,
        category: str,
        symbol: str,
        interval_time: str = "5min",
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 1,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/market/open-interest",
            params={
                "category": category,
                "symbol": symbol,
                "intervalTime": interval_time,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": int(limit),
            },
            auth=False,
        )

    async def get_account_ratio(
        self,
        *,
        category: str,
        symbol: str,
        period: str = "5min",
        limit: int = 1,
    ) -> dict[str, Any]:
        """Top trader long/short account ratio (buyRatio / sellRatio)."""
        return await self._request(
            "GET",
            "/v5/market/account-ratio",
            params={
                "category": category,
                "symbol": symbol,
                "period": period,
                "limit": int(limit),
            },
            auth=False,
        )

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
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v5/order/create",
            payload={
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": qty,
                "price": price,
                "timeInForce": time_in_force,
            },
            auth=True,
        )

    async def cancel_order(
        self,
        *,
        category: str,
        symbol: str,
        order_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v5/order/cancel",
            payload={
                "category": category,
                "symbol": symbol,
                "orderId": order_id,
            },
            auth=True,
        )

    async def get_open_orders(
        self,
        *,
        category: str,
        symbol: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v5/order/realtime",
            params={
                "category": category,
                "symbol": symbol,
                "orderId": order_id,
            },
            auth=True,
        )

    async def get_order_history(
        self,
        *,
        category: str,
        symbol: str | None = None,
        order_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Closed/filled orders (realtime list drops them after fill)."""
        return await self._request(
            "GET",
            "/v5/order/history",
            params={
                "category": category,
                "symbol": symbol,
                "orderId": order_id,
                "limit": int(limit),
            },
            auth=True,
        )
