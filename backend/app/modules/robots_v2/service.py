"""Business logic for robots v2 (Stage 0: CRUD + validate)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots_v2 import queries
from app.modules.robots_v2 import audit_queries
from app.modules.robots_v2.audit_pnl import build_round_trips, enrich_fills_realized_pnl
from app.modules.robots_v2.config.v4_schema import CONFIG_VERSION_V4
from app.modules.robots_v2.schemas import (
    RobotV2AuditRequest,
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

from app.modules.robots_v2.engine.session_resume import DELETED_AT_KEY, SESSION_DESIRED_KEY

_IDLE_BROKER_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_IDLE_BROKER_CACHE_TTL_SEC = 20.0
_IDLE_BROKER_FETCH_TIMEOUT_SEC = 6.0


def _idle_broker_cache_get(robot_id: int) -> dict[str, Any] | None:
    entry = _IDLE_BROKER_CACHE.get(robot_id)
    if entry is None:
        return None
    ts, payload = entry
    if (time.monotonic() - ts) > _IDLE_BROKER_CACHE_TTL_SEC:
        _IDLE_BROKER_CACHE.pop(robot_id, None)
        return None
    return payload


def _idle_broker_cache_set(robot_id: int, payload: dict[str, Any]) -> None:
    _IDLE_BROKER_CACHE[robot_id] = (time.monotonic(), payload)


def _light_universe_tickers(config: dict[str, Any], open_hints: dict[str, Any]) -> list[str]:
    """Config + audit hints only — no MOEX/screener resolve (status must stay fast)."""
    tickers: set[str] = {str(t).upper() for t in open_hints if t}
    uni = config.get("universe")
    if isinstance(uni, dict):
        fl = uni.get("fixedList") or uni.get("fixed_list")
        if isinstance(fl, list):
            tickers.update(str(t).upper() for t in fl if t)
    meta = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    snap = meta.get("universeSnapshot") or meta.get("universe_snapshot")
    if isinstance(snap, list):
        for item in snap:
            if isinstance(item, dict) and item.get("ticker"):
                tickers.add(str(item["ticker"]).upper())
            elif isinstance(item, str) and item.strip():
                tickers.add(item.strip().upper())
    return sorted(tickers)


def _instrument_map_light(config: dict[str, Any], tickers: list[str]) -> dict[str, str]:
    from app.modules.robots_v2.engine.broker_factory import _figi_map_from_db

    out = _figi_map_from_db(tickers)
    meta = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    imap = meta.get("instrumentMap")
    if isinstance(imap, dict):
        for k, v in imap.items():
            if k and v:
                out[str(k).upper()] = str(v)
    im = config.get("instrument_map")
    if isinstance(im, dict):
        fbt = im.get("figi_by_ticker")
        if isinstance(fbt, dict):
            for k, v in fbt.items():
                if k and v:
                    out[str(k).upper()] = str(v)
        else:
            for k, v in im.items():
                if k != "ticker_by_figi" and k and v:
                    out[str(k).upper()] = str(v)
    return {str(k).upper(): str(v) for k, v in out.items()}


class RobotsV2Service:
    schema = settings.DB_SCHEMA

    @staticmethod
    def _v4_weekdays_to_mask(weekdays: list[bool] | None) -> int:
        bits = weekdays or []
        mask = 0
        for i, on in enumerate(list(bits)[:7]):
            if on:
                mask |= 1 << i
        return mask or 31

    @staticmethod
    def _v4_poll_interval_seconds(poll: str | None) -> int:
        mapping = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
        return mapping.get(str(poll or "5m"), 300)

    def _row_to_response(self, row: Any) -> RobotV2Response:
        return RobotV2Response(
            id=int(row.id),
            name=row.name,
            type=int(row.type),
            typeName=getattr(row, "type_name", None),
            tokenId=row.token_id,
            status=int(row.status),
            statusName=getattr(row, "status_name", None),
            configVersion=int(row.config_version),
            config=row.config if isinstance(row.config, dict) else json.loads(row.config or "{}"),
            metadata=row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or "{}"),
            createdAt=row.date_creation,
            updatedAt=row.date_modification,
            lastStarted=getattr(row, "last_started", None),
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
        from app.modules.robots_v2.engine.session_manager import session_manager

        query, params = queries.build_list_robots_query(
            user_id=user_id,
            robot_status=request.robot_status,
            robot_type=request.robot_type,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        items = [self._row_to_response(row) for row in rows]
        for robot in items:
            if robot.type != 2:
                continue
            snap = session_manager.status(robot.id)
            if snap is not None:
                robot.session_state = snap.session_state.value
        return items

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
            persist_status = int(existing.status)
            if request.type == 1 and request.status in (1, 2):
                persist_status = int(request.status)
            db.execute(
                text(queries.build_update_robot_query(schema=self.schema)),
                {
                    "robot_id": request.id,
                    "user_id": user_id,
                    "name": request.name,
                    "token_id": request.token_id,
                    "type": request.type,
                    "status": persist_status,
                    "config_version": CONFIG_VERSION_V4,
                    "config": json.dumps(request.config, ensure_ascii=False),
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "usermod": user_id,
                },
            )
            self._persist_config_history(db, robot_id=request.id, config=request.config, user_id=user_id)
            db.commit()
            updated = self.get_robot(db, user_id, request.id)
            return updated

        insert_status = 1
        if request.status in (1, 2):
            insert_status = int(request.status)
        insert_query = queries.build_insert_robot_query(schema=self.schema)
        row = db.execute(
            text(insert_query),
            {
                "name": request.name,
                "user_id": user_id,
                "token_id": request.token_id,
                "type": request.type,
                "status": insert_status,
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
        created = self.get_robot(db, user_id, robot_id)
        return created

    async def delete_robot(self, db: Session, user_id: int, robot_id: int) -> dict[str, Any]:
        from app.modules.robots_v2.engine.session_manager import session_manager

        robot = self.get_robot(db, user_id, robot_id)
        if robot.type == 2:
            _IDLE_BROKER_CACHE.pop(robot_id, None)
            if session_manager.get(robot_id) is not None:
                await session_manager.stop(robot_id, stop_mode="hard")
        metadata = dict(robot.metadata or {})
        metadata[DELETED_AT_KEY] = datetime.now(timezone.utc).isoformat()
        metadata[SESSION_DESIRED_KEY] = "stopped"
        soft_status = 0 if robot.type == 1 else int(robot.status)
        row = db.execute(
            text(queries.build_soft_delete_robot_query(schema=self.schema)),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "status": soft_status,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "usermod": user_id,
            },
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

    async def change_status(
        self,
        db: Session,
        user_id: int,
        request: RobotV2ChangeStatusRequest,
    ) -> RobotV2Response:
        from app.modules.robots_v2.engine.session_manager import session_manager

        robot = self.get_robot(db, user_id, request.robot_id)
        if robot.type == 2 and int(request.status) != 1 and session_manager.get(request.robot_id) is not None:
            stop_mode = request.stop_mode or (robot.metadata or {}).get("sessionStopMode") or "soft"
            metadata = dict(robot.metadata or {})
            metadata[SESSION_DESIRED_KEY] = "stopped"
            metadata["sessionStopMode"] = stop_mode
            _IDLE_BROKER_CACHE.pop(request.robot_id, None)
            db.execute(
                text(f"""
                    UPDATE {self.schema}.robots_v2
                    SET metadata = :metadata, usermod = :usermod, date_modification = NOW()
                    WHERE id = :robot_id AND user_id = :user_id
                """),
                {
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "usermod": user_id,
                    "robot_id": request.robot_id,
                    "user_id": user_id,
                },
            )
            db.commit()
            await session_manager.stop(request.robot_id, stop_mode=stop_mode)
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

    def _resolve_virtual_capital(
        self,
        robot: RobotV2Response,
        *,
        request_capital: float | None = None,
    ) -> float:
        mode = (robot.config.get("core") or {}).get("mode")
        if mode == "live":
            return 0.0
        virtual_capital = float(
            request_capital
            or (robot.metadata or {}).get("lastVirtualCapital")
            or 0
        )
        if virtual_capital <= 0:
            raise HTTPException(status_code=422, detail="virtualCapital must be positive")
        return virtual_capital

    def _persist_session_metadata(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        metadata: dict[str, Any],
        session_desired: str,
    ) -> None:
        metadata[SESSION_DESIRED_KEY] = session_desired
        db.execute(
            text(f"""
                UPDATE {self.schema}.robots_v2
                SET metadata = :metadata, last_started = NOW(),
                    usermod = :usermod, date_modification = NOW()
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

    async def launch_trading_session(
        self,
        db: Session,
        robot: RobotV2Response,
        *,
        user_id: int,
        virtual_capital: float | None = None,
        stop_mode: str = "soft",
        mark_desired_running: bool = True,
    ) -> None:
        from app.modules.robots_v2.engine.session_manager import session_manager

        mode = (robot.config.get("core") or {}).get("mode")
        if mode == "paper" and virtual_capital is None:
            virtual_capital = self._resolve_virtual_capital(robot)
        elif virtual_capital is None:
            virtual_capital = self._resolve_virtual_capital(robot)

        metadata = dict(robot.metadata or {})
        if mode == "paper":
            metadata["lastVirtualCapital"] = float(virtual_capital)
        metadata["sessionStopMode"] = stop_mode or "soft"
        if mark_desired_running:
            self._persist_session_metadata(
                db,
                user_id=user_id,
                robot_id=int(robot.id),
                metadata=metadata,
                session_desired="running",
            )
        else:
            db.execute(
                text(f"""
                    UPDATE {self.schema}.robots_v2
                    SET metadata = :metadata, usermod = :usermod, date_modification = NOW()
                    WHERE id = :robot_id AND user_id = :user_id
                """),
                {
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "usermod": user_id,
                    "robot_id": int(robot.id),
                    "user_id": user_id,
                },
            )
            db.commit()

        _IDLE_BROKER_CACHE.pop(int(robot.id), None)
        await session_manager.start(
            robot_id=int(robot.id),
            user_id=user_id,
            token_id=int(robot.token_id or 0),
            config=robot.config,
            virtual_capital=float(virtual_capital),
            stop_mode=stop_mode or "soft",
        )

    async def start_robot(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        request: RobotV2StartRequest,
    ) -> RobotV2Response:
        robot = self.get_robot(db, user_id, robot_id)
        if robot.type != 2:
            raise HTTPException(status_code=400, detail="Only trading robots (type=2) can be started")
        mode = (robot.config.get("core") or {}).get("mode")
        if mode == "paper" and request.virtual_capital is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="virtualCapital is required for paper mode",
            )
        virtual_capital = self._resolve_virtual_capital(
            robot,
            request_capital=request.virtual_capital,
        )
        await self.launch_trading_session(
            db,
            robot,
            user_id=user_id,
            virtual_capital=virtual_capital,
            stop_mode=request.stop_mode or "soft",
            mark_desired_running=True,
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

        robot = self.get_robot(db, user_id, robot_id)
        _IDLE_BROKER_CACHE.pop(robot_id, None)

        metadata = dict(robot.metadata or {})
        metadata[SESSION_DESIRED_KEY] = "stopped"
        metadata["sessionStopMode"] = stop_mode or metadata.get("sessionStopMode") or "soft"
        db.execute(
            text(f"""
                UPDATE {self.schema}.robots_v2
                SET metadata = :metadata, usermod = :usermod, date_modification = NOW()
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

        if session_manager.get(robot_id) is not None:
            await session_manager.stop(robot_id, stop_mode=stop_mode)
        return self.get_robot(db, user_id, robot_id)

    async def refresh_universe(self, db: Session, user_id: int, robot_id: int) -> dict[str, Any]:
        from app.modules.robots_v2.engine.session_manager import session_manager

        self.get_robot(db, user_id, robot_id)
        session = session_manager.get(robot_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нет активной сессии",
            )
        try:
            return await session.refresh_universe(reason="force")
        except ValueError as exc:
            code = str(exc)
            if code == "UNIVERSE_REFRESH_UNSUPPORTED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Обновление пула только для скринера или индекса",
                ) from exc
            if code == "UNIVERSE_REFRESH_NO_SESSION":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Нет активной сессии",
                ) from exc
            if code == "UNIVERSE_REFRESH_RATE_LIMITED":
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Подождите несколько секунд перед повторным обновлением",
                ) from exc
            raise

    async def get_status(self, db: Session, user_id: int, robot_id: int) -> dict[str, Any]:
        from app.modules.robots_v2.engine.broker_positions import open_tickers_from_audit_fills
        from app.modules.robots_v2.engine.session_manager import session_manager
        from app.modules.robots_v2.risk.adapter import enrich_positions_with_exit_prices

        robot = self.get_robot(db, user_id, robot_id)
        snap = session_manager.status(robot_id)
        if snap is not None:
            return {
                "robotId": robot.id,
                "status": robot.status,
                "sessionState": snap.session_state.value,
                "mode": snap.mode,
                "cycleNumber": snap.cycle_number,
                "equity": snap.equity,
                "cash": snap.cash,
                "openPositions": snap.open_positions,
                "positionsSource": "session",
                "universe": snap.universe,
                "lastCycleAt": snap.last_cycle_at.isoformat() if snap.last_cycle_at else None,
                "positionsUpdatedAt": snap.last_prices_at.isoformat() if snap.last_prices_at else None,
                "wsHealthy": snap.ws_healthy,
                "message": snap.message,
                "decisions": snap.decisions,
                "equityCurve": snap.equity_curve,
                "cycleStage": snap.cycle_stage,
                "cycleProgress": snap.cycle_progress,
                "cycleDetail": snap.cycle_detail,
                "cycleSkipReason": snap.cycle_skip_reason,
                "lastTriggeredBy": snap.last_triggered_by,
                "tickerScan": snap.last_ticker_scan,
                "tickerScanAt": snap.last_ticker_scan_at.isoformat() if snap.last_ticker_scan_at else None,
                "openOrders": list(getattr(snap, "open_orders", None) or []),
                "bootstrapReady": bool(getattr(snap, "bootstrap_ready", False)),
                "universeRefreshedAt": (
                    snap.universe_refreshed_at.isoformat()
                    if getattr(snap, "universe_refreshed_at", None)
                    else None
                ),
            }

        # No live session — for live robots, surface broker positions so Monitor
        # stays useful after soft stop / process restart.
        base: dict[str, Any] = {
            "robotId": robot.id,
            "status": robot.status,
            "sessionState": None,
            "message": "No active session",
            "openPositions": [],
            "positionsSource": None,
        }
        cfg = robot.config if isinstance(robot.config, dict) else {}
        core = cfg.get("core") if isinstance(cfg.get("core"), dict) else {}
        mode = str(core.get("mode") or "paper")
        base["mode"] = mode
        if mode != "live" or not robot.token_id:
            return base

        rid = int(robot.id)
        open_hints = open_tickers_from_audit_fills(
            db, robot_id=rid, schema=self.schema,
        )
        cfg_copy = dict(cfg)

        broker_snap = _idle_broker_cache_get(rid)
        if broker_snap is None:
            stale = _IDLE_BROKER_CACHE.get(rid)
            stale_payload = stale[1] if stale else None
            try:
                broker_snap = await asyncio.wait_for(
                    self._fetch_idle_broker_positions(
                        user_id=user_id,
                        robot_id=rid,
                        token_id=int(robot.token_id),
                        config=cfg_copy,
                        open_hints=open_hints,
                    ),
                    timeout=_IDLE_BROKER_FETCH_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "idle broker positions timed out robot_id=%s timeout=%ss",
                    rid,
                    _IDLE_BROKER_FETCH_TIMEOUT_SEC,
                )
                broker_snap = stale_payload
            except Exception:
                logger.exception("idle broker positions failed robot_id=%s", rid)
                broker_snap = stale_payload
            if broker_snap is not None:
                _idle_broker_cache_set(rid, broker_snap)
        if broker_snap is None:
            return base
        positions = broker_snap.get("positions") or []
        risk_raw = cfg.get("risk") if isinstance(cfg.get("risk"), dict) else None
        if risk_raw and positions:
            try:
                from app.modules.robots_v2.config.v4_schema import RiskConfig

                risk = RiskConfig.model_validate(risk_raw)
                positions = enrich_positions_with_exit_prices(positions, risk)
            except Exception:
                pass
        base.update({
            "openPositions": positions,
            "positionsSource": "broker",
            "positionsUpdatedAt": broker_snap.get("updatedAt"),
            "cash": broker_snap.get("cash"),
            "equity": broker_snap.get("equity"),
            "universe": broker_snap.get("universe"),
            "message": (
                f"No active session · broker positions={len(positions)}"
                if positions
                else "No active session · no open broker positions in universe"
            ),
        })
        return base

    async def _fetch_idle_broker_positions(
        self,
        *,
        user_id: int,
        robot_id: int,
        token_id: int,
        config: dict[str, Any],
        open_hints: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Best-effort broker portfolio snapshot when session is stopped (lightweight)."""
        from app.modules.robots_v2.engine.broker_factory import (
            create_broker_from_token,
            resolve_account_id,
        )
        from app.modules.robots_v2.engine.broker_positions import fetch_broker_positions_snapshot
        from app.modules.robots_v2.universe.token_context import load_token_context

        core = config.get("core") if isinstance(config.get("core"), dict) else {}
        instrument_type = str(core.get("instrumentType") or core.get("instrument_type") or "stock")
        db = SessionLocal()
        try:
            token_ctx = load_token_context(
                db,
                user_id=user_id,
                token_id=token_id,
                instrument_type=instrument_type,
                schema=self.schema,
            )
        except Exception:
            return None
        finally:
            db.close()

        universe = _light_universe_tickers(config, open_hints)
        extra = {str(t).upper() for t in open_hints if t}
        tickers_for_map = sorted(set(universe) | extra)
        instrument_map = _instrument_map_light(config, tickers_for_map)

        try:
            broker = create_broker_from_token(
                token_ctx,
                instrument_type=instrument_type,
                robot_config=config,
                robot_id=robot_id,
            )
            if broker is None:
                return None
            preferred = str(core.get("accountId") or core.get("account_id") or "").strip() or None
            account_id = await resolve_account_id(broker, preferred)
            if not account_id:
                return None
            snap = await fetch_broker_positions_snapshot(
                broker=broker,
                account_id=account_id,
                instrument_map=instrument_map,
                universe=universe or None,
                extra_tickers=extra or None,
            )
            if not snap.ok:
                return None
            equity = float(snap.cash or 0)
            for row in snap.positions:
                qty = float(row.get("quantity") or 0)
                px = float(row.get("current_price") or row.get("entry_price") or 0)
                side = str(row.get("side") or "").lower()
                if side in ("long", "buy"):
                    equity += qty * px
                elif side in ("short", "sell"):
                    equity -= qty * px
            return {
                "positions": snap.positions,
                "cash": snap.cash,
                "equity": equity,
                "universe": universe,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("idle broker snapshot failed robot_id=%s", robot_id)
            return None

    def _audit_sessions(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_sessions_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_sessions_query(
            robot_id=robot_id,
            user_id=user_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items = [
            {
                "id": str(row.id),
                "robotId": int(row.robot_id),
                "mode": row.mode,
                "virtualCapital": float(row.virtual_capital) if row.virtual_capital is not None else None,
                "accountId": row.account_id,
                "startedAt": row.started_at,
                "endedAt": row.ended_at,
                "stopReason": row.stop_reason,
            }
            for row in rows
        ]
        return items, total

    def _audit_fills(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_fills_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            session_id=session_id,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_fills_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items = [
            {
                "id": str(row.id),
                "orderId": str(row.order_id),
                "robotId": int(row.robot_id),
                "ticker": row.ticker,
                "side": row.side,
                "quantity": float(row.quantity),
                "price": float(row.price),
                "pnl": float(row.pnl) if row.pnl is not None else None,
                "commission": float(row.commission) if row.commission is not None else None,
                "kind": row.kind,
                "filledAt": row.filled_at,
                "sessionId": str(row.session_id) if row.session_id is not None else None,
            }
            for row in rows
        ]
        return items, total

    def _audit_fills_all_chronological(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        session_id: UUID | None,
    ) -> list[dict[str, Any]]:
        query, params = audit_queries.build_list_fills_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=10_000,
            offset=0,
            session_id=session_id,
            schema=self.schema,
        )
        query = query.replace("ORDER BY f.filled_at DESC", "ORDER BY f.filled_at ASC")
        rows = db.execute(text(query), params).fetchall()
        return [
            {
                "id": str(row.id),
                "orderId": str(row.order_id),
                "ticker": row.ticker,
                "side": row.side,
                "quantity": float(row.quantity),
                "price": float(row.price),
                "kind": row.kind,
                "filledAt": row.filled_at,
                "sessionId": str(row.session_id) if row.session_id is not None else None,
            }
            for row in rows
        ]

    def _risk_rates_for_robot(
        self, db: Session, user_id: int, robot_id: int,
    ) -> tuple[float, float]:
        row = self.get_robot(db, user_id, robot_id)
        cfg = row.config if isinstance(row.config, dict) else {}
        risk = cfg.get("risk") if isinstance(cfg.get("risk"), dict) else {}
        comm_pct = float(risk.get("brokerCommissionPct") or risk.get("broker_commission_pct") or 0.05)
        tax_pct = float(risk.get("taxPct") or risk.get("tax_pct") or 13.0)
        return comm_pct / 100.0, tax_pct / 100.0

    def _audit_cycles(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_cycles_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            session_id=session_id,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_cycles_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items: list[dict[str, Any]] = []
        for row in rows:
            stats = row.stats if isinstance(row.stats, dict) else json.loads(row.stats or "{}")
            items.append({
                "id": str(row.id),
                "sessionId": str(row.session_id),
                "robotId": int(row.robot_id),
                "cycleNumber": int(row.cycle_number),
                "triggeredBy": row.triggered_by,
                "startedAt": row.started_at,
                "finishedAt": row.finished_at,
                "status": row.status,
                "skipReason": row.skip_reason,
                "equity": float(row.equity) if row.equity is not None else None,
                "stats": stats,
            })
        return items, total

    def _audit_decisions(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_decisions_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            session_id=session_id,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_decisions_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items: list[dict[str, Any]] = []
        for row in rows:
            ctx = row.context if isinstance(row.context, dict) else json.loads(row.context or "{}")
            items.append({
                "id": str(row.id),
                "cycleId": str(row.cycle_id),
                "robotId": int(row.robot_id),
                "stage": row.stage,
                "outcome": row.outcome,
                "code": row.code,
                "message": row.message,
                "ticker": row.ticker,
                "context": ctx,
                "createdAt": row.created_at,
            })
        return items, total

    def _audit_signals(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_signals_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            session_id=session_id,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_signals_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items = [
            {
                "id": str(row.id),
                "cycleId": str(row.cycle_id),
                "robotId": int(row.robot_id),
                "ticker": row.ticker,
                "side": row.side,
                "kind": row.kind,
                "reason": row.reason,
                "price": float(row.price) if row.price is not None else None,
                "entryPrice": float(row.entry_price) if row.entry_price is not None else None,
                "deltaPct": float(row.delta_pct) if row.delta_pct is not None else None,
                "createdAt": row.created_at,
            }
            for row in rows
        ]
        return items, total

    def _audit_orders(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        query, params = audit_queries.build_list_orders_query(
            robot_id=robot_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            session_id=session_id,
            schema=self.schema,
        )
        count_q, count_p = audit_queries.build_count_orders_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        total = int(db.execute(text(count_q), count_p).scalar_one())
        items = [
            {
                "id": str(row.id),
                "cycleId": str(row.cycle_id),
                "robotId": int(row.robot_id),
                "ticker": row.ticker,
                "side": row.side,
                "kind": row.kind,
                "quantity": float(row.quantity),
                "price": float(row.price) if row.price is not None else None,
                "status": row.status,
                "mode": row.mode,
                "orderType": str(getattr(row, "order_type", None) or "MARKET"),
                "brokerOrderId": row.broker_order_id,
                "rejectReason": row.reject_reason,
                "submittedAt": row.submitted_at,
            }
            for row in rows
        ]
        return items, total

    def _audit_exit_reasons_map(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        session_id: UUID | None,
    ) -> dict[tuple[str, str], str]:
        query, params = audit_queries.build_exit_reasons_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        out: dict[tuple[str, str], str] = {}
        for row in rows:
            key = (str(row.cycle_id), str(row.ticker).upper())
            out[key] = str(row.code)
        return out

    def _audit_orders_by_id(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        session_id: UUID | None,
    ) -> dict[str, dict[str, Any]]:
        query, params = audit_queries.build_list_orders_all_query(
            robot_id=robot_id,
            user_id=user_id,
            session_id=session_id,
            schema=self.schema,
        )
        rows = db.execute(text(query), params).fetchall()
        return {
            str(row.id): {
                "id": str(row.id),
                "cycleId": str(row.cycle_id),
                "ticker": row.ticker,
                "side": row.side,
                "kind": row.kind,
                "quantity": float(row.quantity),
                "price": float(row.price) if row.price is not None else None,
                "status": row.status,
                "orderType": str(row.order_type or "MARKET"),
                "rejectReason": row.reject_reason,
            }
            for row in rows
        }

    def _audit_round_trips(
        self,
        db: Session,
        *,
        user_id: int,
        robot_id: int,
        limit: int,
        offset: int,
        session_id: UUID | None,
    ) -> tuple[list[dict[str, Any]], int]:
        timeline = self._audit_fills_all_chronological(
            db, user_id=user_id, robot_id=robot_id, session_id=session_id,
        )
        orders_by_id = self._audit_orders_by_id(
            db, user_id=user_id, robot_id=robot_id, session_id=session_id,
        )
        exit_reasons = self._audit_exit_reasons_map(
            db, user_id=user_id, robot_id=robot_id, session_id=session_id,
        )
        comm, tax = self._risk_rates_for_robot(db, user_id, robot_id)
        all_trips = build_round_trips(
            timeline,
            orders_by_id,
            exit_reasons,
            commission_rate=comm,
            tax_rate=tax,
        )
        total = len(all_trips)
        return all_trips[offset : offset + limit], total

    def query_audit(self, db: Session, user_id: int, request: RobotV2AuditRequest) -> dict[str, Any]:
        self.get_robot(db, user_id, request.robot_id)
        types = request.types or list(audit_queries.AUDIT_TYPES)
        limit = min(max(request.limit, 1), 500)
        offset = max(request.offset, 0)
        session_id: UUID | None = None
        if request.session_id:
            try:
                session_id = UUID(request.session_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid sessionId UUID",
                ) from exc

        unknown = [t for t in types if t not in audit_queries.AUDIT_TYPES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown audit types: {', '.join(unknown)}",
            )

        payload: dict[str, Any] = {"robotId": request.robot_id}
        if "sessions" in types:
            items, total = self._audit_sessions(
                db, user_id=user_id, robot_id=request.robot_id, limit=limit, offset=offset,
            )
            payload["sessions"] = {"items": items, "total": total}
        if "fills" in types:
            items, total = self._audit_fills(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            timeline = self._audit_fills_all_chronological(
                db, user_id=user_id, robot_id=request.robot_id, session_id=session_id,
            )
            comm, tax = self._risk_rates_for_robot(db, user_id, request.robot_id)
            items = enrich_fills_realized_pnl(
                items,
                commission_rate=comm,
                tax_rate=tax,
                all_fills_chronological=timeline,
            )
            payload["fills"] = {"items": items, "total": total}
        if "cycles" in types:
            items, total = self._audit_cycles(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            payload["cycles"] = {"items": items, "total": total}
        if "decisions" in types:
            items, total = self._audit_decisions(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            payload["decisions"] = {"items": items, "total": total}
        if "signals" in types:
            items, total = self._audit_signals(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            payload["signals"] = {"items": items, "total": total}
        if "orders" in types:
            items, total = self._audit_orders(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            payload["orders"] = {"items": items, "total": total}
        if "roundTrips" in types:
            items, total = self._audit_round_trips(
                db, user_id=user_id, robot_id=request.robot_id,
                limit=limit, offset=offset, session_id=session_id,
            )
            payload["roundTrips"] = {"items": items, "total": total}
        return payload


robots_v2_service = RobotsV2Service()
