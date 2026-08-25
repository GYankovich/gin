"""Session manager — one RUNNING session per robot."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, status

from app.modules.robots_v2.engine.session import TradingSessionV2
from app.modules.robots_v2.engine.types import SessionState, SessionStatus


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int, TradingSessionV2] = {}

    def get(self, robot_id: int) -> TradingSessionV2 | None:
        return self._sessions.get(robot_id)

    def is_running(self, robot_id: int) -> bool:
        s = self._sessions.get(robot_id)
        return s is not None and s.state in (SessionState.BOOTSTRAP, SessionState.RUNNING, SessionState.STOPPING)

    async def start(
        self,
        *,
        robot_id: int,
        user_id: int,
        token_id: int,
        config: dict[str, Any],
        virtual_capital: float,
        stop_mode: str = "soft",
    ) -> SessionStatus:
        if self.is_running(robot_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already running")
        # Replace previous ERROR/TERMINATED snapshot if any
        self._sessions.pop(robot_id, None)
        session = TradingSessionV2(
            robot_id=robot_id,
            user_id=user_id,
            token_id=token_id,
            config=config,
            virtual_capital=virtual_capital,
            stop_mode=stop_mode,
        )
        self._sessions[robot_id] = session
        await session.start()
        return session.status()

    async def stop(self, robot_id: int, *, stop_mode: str | None = None) -> SessionStatus:
        session = self._sessions.get(robot_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active session")
        hard = str(stop_mode or "soft").lower() == "hard"
        await session.stop(hard=hard)
        return session.status()

    def status(self, robot_id: int) -> SessionStatus | None:
        session = self._sessions.get(robot_id)
        if session is None:
            return None
        return session.status()

    def on_session_ended(self, robot_id: int) -> None:
        session = self._sessions.get(robot_id)
        # Keep ERROR sessions so monitor can show why start failed
        if session is not None and session.state == SessionState.ERROR:
            return
        self._sessions.pop(robot_id, None)


session_manager = SessionManager()
