"""Business logic for robots v2 (Stage 0: CRUD + validate)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots_v2 import queries
from app.modules.robots_v2.config.v4_schema import CONFIG_VERSION_V4
from app.modules.robots_v2.schemas import (
    RobotV2ChangeStatusRequest,
    RobotV2CreateRequest,
    RobotV2ListRequest,
    RobotV2Response,
    RobotV2StartRequest,
    RobotV2ValidateRequest,
    RobotV2ValidateResponse,
)
from app.modules.robots_v2.validator import (
    validate_portfolio_config,
    validate_trading_config,
)


class RobotsV2Service:
    schema = settings.DB_SCHEMA

    def _row_to_response(self, row: Any) -> RobotV2Response:
        return RobotV2Response(
            id=int(row.id),
            name=row.name,
            type=int(row.type),
            tokenId=row.token_id,
            status=int(row.status),
            configVersion=int(row.config_version),
            config=row.config if isinstance(row.config, dict) else json.loads(row.config or "{}"),
            metadata=row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or "{}"),
            createdAt=row.date_creation,
            updatedAt=row.date_modification,
        )

    def _validate_config(self, robot_type: int, config: dict[str, Any]) -> RobotV2ValidateResponse:
        if robot_type == 2:
            parsed, issues = validate_trading_config(config)
        elif robot_type == 1:
            parsed, issues = validate_portfolio_config(config)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported robot type")
        if parsed is None:
            return RobotV2ValidateResponse(valid=False, errors=issues)
        return RobotV2ValidateResponse(valid=True)

    def validate(self, request: RobotV2ValidateRequest) -> RobotV2ValidateResponse:
        return self._validate_config(request.type, request.config)

    def list_robots(self, db: Session, user_id: int, request: RobotV2ListRequest) -> list[RobotV2Response]:
        query, params = queries.build_list_robots_query(
            user_id=user_id,
            robot_status=request.robot_status,
            robot_type=request.robot_type,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        return [self._row_to_response(row) for row in rows]

    def get_robot(self, db: Session, user_id: int, robot_id: int) -> RobotV2Response:
        query, params = queries.build_get_robot_query(
            robot_id=robot_id,
            user_id=user_id,
            schema=self.schema,
        )
        row = db.execute(text(query), params).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found")
        return self._row_to_response(row)

    def _persist_config_history(
        self,
        db: Session,
        *,
        robot_id: int,
        config: dict[str, Any],
        user_id: int,
    ) -> None:
        version_query, version_params = queries.build_next_config_version_query(
            robot_id=robot_id,
            schema=self.schema,
        )
        version_row = db.execute(text(version_query), version_params).fetchone()
        next_version = int(version_row.next_version) if version_row else 1
        db.execute(
            text(queries.build_insert_config_history_query(schema=self.schema)),
            {
                "id": str(uuid.uuid4()),
                "robot_id": robot_id,
                "version": next_version,
                "config": json.dumps(config, ensure_ascii=False),
                "created_by": user_id,
            },
        )

    def create_or_update(self, db: Session, user_id: int, request: RobotV2CreateRequest) -> RobotV2Response:
        validation = self._validate_config(request.type, request.config)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Config validation failed", "errors": [e.model_dump() for e in validation.errors]},
            )

        metadata: dict[str, Any] = {}
        if request.id is not None:
            existing = self.get_robot(db, user_id, request.id)
            metadata = dict(existing.metadata or {})
            db.execute(
                text(queries.build_update_robot_query(schema=self.schema)),
                {
                    "robot_id": request.id,
                    "user_id": user_id,
                    "name": request.name,
                    "token_id": request.token_id,
                    "type": request.type,
                    "status": existing.status,
                    "config_version": CONFIG_VERSION_V4,
                    "config": json.dumps(request.config, ensure_ascii=False),
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "usermod": user_id,
                },
            )
            self._persist_config_history(db, robot_id=request.id, config=request.config, user_id=user_id)
            db.commit()
            return self.get_robot(db, user_id, request.id)

        insert_query = queries.build_insert_robot_query(schema=self.schema)
        row = db.execute(
            text(insert_query),
            {
                "name": request.name,
                "user_id": user_id,
                "token_id": request.token_id,
                "type": request.type,
                "status": 0,
                "config_version": CONFIG_VERSION_V4,
                "config": json.dumps(request.config, ensure_ascii=False),
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "usercre": user_id,
            },
        ).fetchone()
        db.commit()
        robot_id = int(row.id)
        self._persist_config_history(db, robot_id=robot_id, config=request.config, user_id=user_id)
        db.commit()
        return self.get_robot(db, user_id, robot_id)

    def delete_robot(self, db: Session, user_id: int, robot_id: int) -> dict[str, Any]:
        row = db.execute(
            text(queries.build_delete_robot_query(schema=self.schema)),
            {"robot_id": robot_id, "user_id": user_id},
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found")
        db.commit()
        return {"id": robot_id, "deleted": True}

    def clone_robot(self, db: Session, user_id: int, robot_id: int) -> RobotV2Response:
        src = self.get_robot(db, user_id, robot_id)
        if src.type != 2:
            raise HTTPException(status_code=400, detail="Only trading robots can be cloned")
        if not src.token_id:
            raise HTTPException(status_code=422, detail="Source robot has no tokenId")
        name = f"Копия {src.name}"[:50]
        return self.create_or_update(
            db,
            user_id,
            RobotV2CreateRequest(
                name=name,
                type=2,
                tokenId=int(src.token_id),
                config=dict(src.config or {}),
            ),
        )

    def change_status(
        self,
        db: Session,
        user_id: int,
        request: RobotV2ChangeStatusRequest,
    ) -> RobotV2Response:
        _ = self.get_robot(db, user_id, request.robot_id)
        row = db.execute(
            text(queries.build_update_status_query(schema=self.schema)),
            {
                "robot_id": request.robot_id,
                "user_id": user_id,
                "status": request.status,
                "usermod": user_id,
            },
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found")
        db.commit()
        return self.get_robot(db, user_id, request.robot_id)

    async def start_robot(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        request: RobotV2StartRequest,
    ) -> RobotV2Response:
        from app.modules.robots_v2.engine.session_manager import session_manager

        robot = self.get_robot(db, user_id, robot_id)
        if robot.type != 2:
            raise HTTPException(status_code=400, detail="Only trading robots (type=2) can be started")
        mode = (robot.config.get("core") or {}).get("mode")
        if mode == "paper" and request.virtual_capital is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="virtualCapital is required for paper mode",
            )
        virtual_capital = float(request.virtual_capital or (robot.metadata or {}).get("lastVirtualCapital") or 0)
        if virtual_capital <= 0:
            raise HTTPException(status_code=422, detail="virtualCapital must be positive")

        metadata = dict(robot.metadata or {})
        metadata["lastVirtualCapital"] = virtual_capital
        metadata["sessionStopMode"] = request.stop_mode or "soft"
        db.execute(
            text(f"""
                UPDATE {self.schema}.robots_v2
                SET metadata = :metadata, last_started = NOW(), usermod = :usermod, date_modification = NOW()
                WHERE id = :robot_id AND user_id = :user_id
            """),
            {
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "usermod": user_id,
                "robot_id": robot_id,
                "user_id": user_id,
            },
        )
        db.commit()

        await session_manager.start(
            robot_id=robot_id,
            user_id=user_id,
            token_id=int(robot.token_id or 0),
            config=robot.config,
            virtual_capital=virtual_capital,
            stop_mode=request.stop_mode or "soft",
        )
        return self.get_robot(db, user_id, robot_id)

    async def stop_robot(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        stop_mode: str | None,
    ) -> RobotV2Response:
        from app.modules.robots_v2.engine.session_manager import session_manager

        _ = self.get_robot(db, user_id, robot_id)
        await session_manager.stop(robot_id, stop_mode=stop_mode)
        return self.get_robot(db, user_id, robot_id)

    def get_status(self, db: Session, user_id: int, robot_id: int) -> dict[str, Any]:
        from app.modules.robots_v2.engine.session_manager import session_manager

        robot = self.get_robot(db, user_id, robot_id)
        snap = session_manager.status(robot_id)
        if snap is None:
            return {
                "robotId": robot.id,
                "status": robot.status,
                "sessionState": None,
                "message": "No active session",
            }
        return {
            "robotId": robot.id,
            "status": robot.status,
            "sessionState": snap.session_state.value,
            "mode": snap.mode,
            "cycleNumber": snap.cycle_number,
            "equity": snap.equity,
            "cash": snap.cash,
            "openPositions": snap.open_positions,
            "universe": snap.universe,
            "lastCycleAt": snap.last_cycle_at.isoformat() if snap.last_cycle_at else None,
            "wsHealthy": snap.ws_healthy,
            "decisions": snap.decisions,
            "equityCurve": snap.equity_curve,
        }


robots_v2_service = RobotsV2Service()
