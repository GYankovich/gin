"""
Middleware для подробного логирования всех REST-запросов/ответов.

Реализован как чистый ASGI middleware (без BaseHTTPMiddleware),
чтобы избежать deadlock при чтении body.

Логирует в rest_YYYY-MM-DD_HH1-HH2.log:
  - метод, путь, query-params, client IP
  - заголовки запроса (Authorization маскируется)
  - тело запроса (до 2 КБ, POST/PUT/PATCH)
  - все SQL-запросы в контексте REST-вызова (через contextvars → database.py)
  - статус ответа, длительность
  - тело ответа (до 2 КБ) при ошибках (4xx/5xx)
"""
import contextvars
import time
import json
from typing import List

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.logging_config import get_rest_logger

_MAX_BODY_LOG = 2048

rest_log = get_rest_logger()

rest_request_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "rest_request_ctx", default=False,
)
rest_request_path_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "rest_request_path_ctx", default="",
)


def _safe_truncate(text: str, max_len: int = _MAX_BODY_LOG) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... (truncated, total {len(text)})"


def _mask_headers(raw_headers: List[tuple]) -> dict:
    headers: dict = {}
    for k, v in raw_headers:
        name = k.decode("latin-1") if isinstance(k, bytes) else k
        val = v.decode("latin-1") if isinstance(v, bytes) else v
        headers[name.lower()] = val

    if "authorization" in headers:
        tok = headers["authorization"]
        headers["authorization"] = tok[:20] + "***" if len(tok) > 20 else "***"
    return headers


class RestLoggingMiddleware:
    """Pure-ASGI middleware: no BaseHTTPMiddleware, no deadlocks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method: str = scope.get("method", "")
        path: str = scope.get("path", "")
        qs = (scope.get("query_string") or b"").decode("latin-1")
        client = scope.get("client")
        client_ip = client[0] if client else "-"

        headers = _mask_headers(scope.get("headers", []))

        rest_log.info(
            ">>> %s %s%s client=%s",
            method, path, f"?{qs}" if qs else "", client_ip,
        )
        rest_log.debug("    headers=%s", json.dumps(headers, ensure_ascii=False, default=str))

        # --- буферизация request body (POST/PUT/PATCH) ---
        body_buffer: bytes = b""
        body_done = False

        if method in ("POST", "PUT", "PATCH"):
            chunks: list[bytes] = []
            while True:
                message = await receive()
                chunk = message.get("body", b"")
                if chunk:
                    chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body_buffer = b"".join(chunks)
            if body_buffer:
                rest_log.debug(
                    "    body=%s",
                    _safe_truncate(body_buffer.decode("utf-8", errors="replace")),
                )
            body_done = True

        async def receive_replay() -> dict:
            nonlocal body_done
            if body_done:
                body_done = False
                return {"type": "http.request", "body": body_buffer, "more_body": False}
            return await receive()

        actual_receive = receive_replay if method in ("POST", "PUT", "PATCH") else receive

        # --- contextvars для SQL-логирования ---
        tok_ctx = rest_request_ctx.set(True)
        tok_path = rest_request_path_ctx.set(f"{method} {path}")

        # --- перехват response ---
        status_code = 0
        resp_body_parts: list[bytes] = []

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            elif message["type"] == "http.response.body" and status_code >= 400:
                resp_body_parts.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, actual_receive, send_wrapper)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            rest_log.error(
                "<<< %s %s => EXCEPTION [%.1fms] %s",
                method, path, elapsed_ms, exc, exc_info=True,
            )
            raise
        finally:
            rest_request_ctx.reset(tok_ctx)
            rest_request_path_ctx.reset(tok_path)

        elapsed_ms = (time.perf_counter() - start) * 1000

        level = "error" if status_code >= 500 else ("warning" if status_code >= 400 else "info")
        getattr(rest_log, level)(
            "<<< %s %s => %s [%.1fms]",
            method, path, status_code, elapsed_ms,
        )

        if status_code >= 400 and resp_body_parts:
            error_text = _safe_truncate(
                b"".join(resp_body_parts).decode("utf-8", errors="replace"),
            )
            rest_log.debug("    response_body=%s", error_text)
