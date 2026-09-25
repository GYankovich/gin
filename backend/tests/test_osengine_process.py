"""OsEngine local process auto-start helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.osengine.process import (
    resolve_osengine_exe_path,
    resolve_osengine_workdir,
    reset_osengine_process_for_tests,
    start_osengine_process,
)


def test_resolve_exe_from_data_root(tmp_path: Path):
    debug = tmp_path / "bin" / "Debug"
    debug.mkdir(parents=True)
    exe = debug / "OsEngine.exe"
    exe.write_bytes(b"MZ")
    data = debug / "Data"
    data.mkdir()
    found = resolve_osengine_exe_path(exe_path="", data_root=str(data))
    assert found == exe
    assert resolve_osengine_workdir(exe) == debug


def test_resolve_exe_explicit(tmp_path: Path):
    exe = tmp_path / "OsEngine.exe"
    exe.write_bytes(b"MZ")
    assert resolve_osengine_exe_path(exe_path=str(exe), data_root=None) == exe


def test_start_skips_when_mcp_already_up():
    reset_osengine_process_for_tests()

    async def _run():
        with patch("app.modules.osengine.process.settings") as st, patch(
            "app.modules.osengine.process.mcp_endpoint_reachable",
            new=AsyncMock(return_value=True),
        ), patch("app.modules.osengine.process.subprocess.Popen") as popen:
            st.OSENGINE_ENABLED = True
            st.OSENGINE_AUTO_START = True
            ok = await start_osengine_process()
            assert ok is True
            popen.assert_not_called()

    asyncio.run(_run())


def test_start_spawns_when_mcp_down(tmp_path: Path):
    reset_osengine_process_for_tests()
    debug = tmp_path / "Debug"
    debug.mkdir()
    exe = debug / "OsEngine.exe"
    exe.write_bytes(b"MZ")
    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = 4242

    async def _run():
        with patch("app.modules.osengine.process.settings") as st, patch(
            "app.modules.osengine.process.mcp_endpoint_reachable",
            new=AsyncMock(return_value=False),
        ), patch(
            "app.modules.osengine.process.subprocess.Popen",
            return_value=proc,
        ) as popen, patch(
            "app.modules.osengine.process.resolve_osengine_exe_path",
            return_value=exe,
        ), patch(
            "app.modules.osengine.process._schedule_mcp_wait",
        ) as sched:
            st.OSENGINE_ENABLED = True
            st.OSENGINE_AUTO_START = True
            st.OSENGINE_WORKDIR = str(debug)
            st.OSENGINE_STARTUP_TIMEOUT_SECONDS = 5.0
            ok = await start_osengine_process(wait_for_mcp=False)
            assert ok is True
            popen.assert_called_once()
            assert popen.call_args.kwargs.get("cwd") == str(debug)
            sched.assert_called_once()

    asyncio.run(_run())
    reset_osengine_process_for_tests()
