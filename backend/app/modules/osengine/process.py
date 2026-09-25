"""Spawn / stop local OsEngine.exe alongside the GIN API process."""

from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_owned_proc: Optional[subprocess.Popen] = None
_mcp_wait_task: Optional[asyncio.Task] = None


def resolve_osengine_exe_path(
    *,
    exe_path: Optional[str] = None,
    data_root: Optional[str] = None,
) -> Optional[Path]:
    raw = (exe_path if exe_path is not None else settings.OSENGINE_EXE_PATH) or ""
    raw = str(raw).strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None

    root = (data_root if data_root is not None else settings.OSENGINE_DATA_ROOT) or ""
    root = str(root).strip()
    if not root:
        return None
    data = Path(root)
    # …/bin/Debug/Data → …/bin/Debug/OsEngine.exe
    candidate = data.parent / "OsEngine.exe"
    if candidate.is_file():
        return candidate
    # …/Data next to exe
    sibling = data / "OsEngine.exe"
    if sibling.is_file():
        return sibling
    return None


def resolve_osengine_workdir(exe: Path, *, workdir: Optional[str] = None) -> Path:
    raw = (workdir if workdir is not None else settings.OSENGINE_WORKDIR) or ""
    raw = str(raw).strip()
    if raw:
        return Path(raw)
    return exe.parent


async def mcp_endpoint_reachable(
    *,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 0.75,
) -> bool:
    """True if something answers on OSENGINE_MCP_URL (TCP/HTTP up)."""
    target = (url if url is not None else settings.OSENGINE_MCP_URL) or ""
    target = str(target).strip()
    if not target:
        return False
    from app.modules.osengine.mcp_client import normalize_osengine_mcp_url

    target = normalize_osengine_mcp_url(target)
    headers = {"Content-Type": "application/json"}
    key = (api_key if api_key is not None else settings.OSENGINE_MCP_API_KEY) or ""
    key = str(key).strip()
    if key:
        headers["X-Api-Key"] = key
    # Minimal JSON-RPC ping; any HTTP response (incl. 4xx JSON) means listener is up.
    payload = {
        "jsonrpc": "2.0",
        "id": "gin-mcp-ping",
        "method": "tools/list",
        "params": {},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(target, json=payload, headers=headers)
            # HttpListener "Invalid Hostname" HTML 400 must not count as ready.
            if resp.status_code >= 400:
                body = (resp.text or "")[:80].lower()
                if "invalid hostname" in body or "bad request" in body:
                    return False
            return resp.status_code < 500
    except Exception:
        # Fallback: TCP connect to host:port from URL
        try:
            parsed = urlparse(target if "://" in target else f"http://{target}")
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False


def _proc_alive(proc: Optional[subprocess.Popen]) -> bool:
    return proc is not None and proc.poll() is None


async def _wait_until_mcp_ready(*, timeout: Optional[float] = None) -> bool:
    """Poll MCP until ready or timeout. Does not block API if run as a background task."""
    limit = float(timeout if timeout is not None else settings.OSENGINE_STARTUP_TIMEOUT_SECONDS)
    deadline = time.monotonic() + max(1.0, limit)
    while time.monotonic() < deadline:
        if _owned_proc is not None and not _proc_alive(_owned_proc):
            code = _owned_proc.returncode
            logger.error("osengine process exited while waiting for MCP code=%s", code)
            return False
        if await mcp_endpoint_reachable():
            logger.info(
                "osengine MCP ready (pid=%s)",
                _owned_proc.pid if _proc_alive(_owned_proc) else None,
            )
            return True
        await asyncio.sleep(1.0)
    logger.warning(
        "osengine MCP not ready within %.0fs (pid=%s). "
        "Включите MCP API в OsEngine (порт из OSENGINE_MCP_URL) — API уже работает",
        limit,
        _owned_proc.pid if _proc_alive(_owned_proc) else None,
    )
    return False


def _schedule_mcp_wait() -> None:
    global _mcp_wait_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _mcp_wait_task is not None and not _mcp_wait_task.done():
        return

    async def _runner() -> None:
        try:
            await _wait_until_mcp_ready()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("osengine background MCP wait failed")

    _mcp_wait_task = loop.create_task(_runner(), name="osengine_mcp_ready")


async def start_osengine_process(*, wait_for_mcp: bool = False) -> bool:
    """Start OsEngine if enabled/auto-start and MCP is not already up.

    By default does **not** block on MCP readiness (so FastAPI lifespan can finish).
    A background task logs when MCP becomes ready (or times out).

    Returns True if MCP is already up, or the process was spawned / already owned.
    """
    global _owned_proc

    if not settings.OSENGINE_ENABLED:
        logger.info("osengine auto-start skipped (OSENGINE_ENABLED=false)")
        return False
    if not settings.OSENGINE_AUTO_START:
        logger.info("osengine auto-start skipped (OSENGINE_AUTO_START=false)")
        return False

    if await mcp_endpoint_reachable():
        logger.info("osengine MCP already reachable — skip spawn")
        return True

    exe = resolve_osengine_exe_path()
    if exe is None:
        logger.error(
            "osengine auto-start: OsEngine.exe not found "
            "(set OSENGINE_EXE_PATH or OSENGINE_DATA_ROOT=…/bin/Debug/Data)"
        )
        return False

    cwd = resolve_osengine_workdir(exe)
    if not cwd.is_dir():
        logger.error("osengine auto-start: workdir missing %s", cwd)
        return False

    if _proc_alive(_owned_proc):
        logger.info("osengine auto-start: already spawned pid=%s", _owned_proc.pid)
    else:
        creationflags = 0
        if sys.platform == "win32":
            # Keep GUI window; new process group for clean terminate.
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            _owned_proc = subprocess.Popen(
                [str(exe)],
                cwd=str(cwd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            logger.info(
                "osengine spawned pid=%s exe=%s cwd=%s (MCP wait is non-blocking)",
                _owned_proc.pid,
                exe,
                cwd,
            )
        except OSError as exc:
            logger.error("osengine spawn failed exe=%s: %s", exe, exc)
            _owned_proc = None
            return False

    if wait_for_mcp:
        return await _wait_until_mcp_ready()

    _schedule_mcp_wait()
    return True


async def stop_osengine_process() -> None:
    """Terminate only the OsEngine process spawned by GIN."""
    global _owned_proc, _mcp_wait_task

    if _mcp_wait_task is not None and not _mcp_wait_task.done():
        _mcp_wait_task.cancel()
        try:
            await _mcp_wait_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    _mcp_wait_task = None

    if not settings.OSENGINE_STOP_ON_SHUTDOWN:
        logger.info("osengine stop on shutdown disabled")
        return
    proc = _owned_proc
    _owned_proc = None
    if not _proc_alive(proc):
        return
    assert proc is not None
    pid = proc.pid
    logger.info("osengine stopping owned pid=%s", pid)
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
    except OSError as exc:
        logger.warning("osengine terminate failed pid=%s: %s", pid, exc)
        return

    try:
        await asyncio.to_thread(proc.wait, 15)
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            await asyncio.to_thread(proc.wait, 5)
        except Exception:
            pass
    logger.info("osengine stopped pid=%s", pid)


def reset_osengine_process_for_tests() -> None:
    global _owned_proc, _mcp_wait_task
    _owned_proc = None
    _mcp_wait_task = None


__all__ = [
    "mcp_endpoint_reachable",
    "reset_osengine_process_for_tests",
    "resolve_osengine_exe_path",
    "resolve_osengine_workdir",
    "start_osengine_process",
    "stop_osengine_process",
]
