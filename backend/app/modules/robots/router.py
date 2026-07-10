from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date
from typing import Optional, List

#///EPIC Backtesting.ITEM RobotsAPI.TOPIC Endpoints Map [1]
#/// REST-контракт модуля robots: CRUD, schedule/config, history-backtest, live snapshot,
#/// сравнение прогонов и вспомогательные операции по инструментам.
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.config import settings
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, service, queries
from .usecases import robot_backtest_usecase, robot_live_snapshot_usecase

logger = get_logger(__name__)
router = APIRouter(prefix="/robots", tags=["Trading Robots"])


async def _continue_history_backtest_async(run_id: int, user_id: int, body: dict) -> None:
    """Фоновое продолжение прогона после 202 (отдельная DB-сессия)."""
    from app.core.database import SessionLocal
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        req = schemas.RobotHistoryBacktestRequest.model_validate(body)
        out = await service.robot_service.run_robot_history_backtest(
            db, user_id, req, deferred_run_id=run_id,
        )
        if isinstance(out, dict) and out.get("__worker_aborted__"):
            logger.info("async history-backtest worker aborted run_id=%s", run_id)
            return
        if isinstance(out, dict) and out.get("__prefetch_scheduled__"):
            logger.info(
                "async history-backtest deferred to crypto_screening_prefetch run_id=%s",
                run_id,
            )
            return
    except HTTPException as hex:
        if hex.status_code == status.HTTP_409_CONFLICT:
            logger.info(
                "async history-backtest not started run_id=%s (cancelled or finished): %s",
                run_id,
                hex.detail,
            )
            return
        logger.warning("async history-backtest HTTP error run_id=%s: %s", run_id, hex.detail)
        from app.modules.robots.service import _mark_backtest_run_failed

        _mark_backtest_run_failed(db, run_id, str(hex.detail))
    except Exception as exc:
        logger.exception("async history-backtest worker failed run_id=%s", run_id)
        from app.modules.robots.service import _mark_backtest_run_failed

        _mark_backtest_run_failed(db, run_id, str(exc))
    finally:
        db.close()

# app/modules/robots/router.py

# === ПРОСМОТР РОБОТА ===

@router.post("/data", response_model=schemas.RobotListResponse)
async def get_robots(
        request: schemas.RobotListRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка всех роботов пользователя
    """

    # Строим запрос для получения данных
    query, params = queries.build_get_user_robots_query(
        robot_status=request.robot_status,
        robot_type=request.robot_type,
        robot_name=request.robot_name,
        token_type=request.token_type,
        limit=request.limit,
        offset=request.offset,
        sort_by=request.sort_by,
        sort_order=request.sort_order,
        schema=settings.DB_SCHEMA
    )
    params["user_id"] = current_user.id

    # Выполняем запрос
    result = db.execute(text(query), params).fetchall()

    # Строим запрос для подсчета общего количества
    count_query, count_params = queries.build_count_user_robots_query(
        robot_status=request.robot_status,
        robot_type=request.robot_type,
        robot_name=request.robot_name,
        token_type=request.token_type,
        schema=settings.DB_SCHEMA
    )
    count_params["user_id"] = current_user.id
    total = db.execute(text(count_query), count_params).scalar() or 0

    robots = []
    for row in result:
        cfg = row[12] if row[12] is not None else {}
        if int(row[8] or 0) == 2:
            cfg = service.robot_service._normalize_trading_robot_config_for_api(cfg)
        robot_dict = {
            "id": row[0],
            "user_id": row[1],
            "token": {
                "id": row[2],
                "name": row[3],
                "status": row[4],
                "type": row[5],
                "typeName": row[6]
            },
            "name": row[7],
            "type": row[8],
            "typeName": row[9],
            "status": row[10],
            "statusName": row[11],
            "config": cfg,
            "last_started": row[13],
            "last_error": row[14],
            "last_error_at": row[15],
            "last_stopped": row[16],
            "usercre": row[17],
            "date_creation": row[18],
            "usermod": row[19],
            "date_modification": row[20]
        }
        robots.append(robot_dict)

    return schemas.RobotListResponse(
        total=total,
        items=robots,
        limit=request.limit,
        offset=request.offset
    )

# === ИЗМЕНЕНИЕ РОБОТА ===

@router.post("/create", response_model=schemas.RobotInDB, status_code=status.HTTP_201_CREATED)
async def create_robot(
        robot_data: schemas.RobotCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Создание нового робота

    - **name**: Название робота (обязательно)
    - **type**: Тип робота (1 - Portfolio, 2 - Trading)
    - **token_id**: ID токена доступа
    """

    # Валидация
    if robot_data.type not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только роботы: 1 (опросник), 2 (торговый)"
        )

    try:
        robot = await service.robot_service.create_robot(db, current_user.id, robot_data)
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании робота: {str(e)}"
        )


@router.post(
    "/duplicate",
    response_model=schemas.RobotInDB,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_robot(
        request: schemas.RobotDuplicateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Создать копию робота (§7.8).

    Копирует strategy/risk/costs/schedule, сбрасывает universe и списки инструментов.
    `broker_type` можно задать для смены контура (MOEX → crypto).
    """
    try:
        robot = await service.robot_service.duplicate_robot(
            db=db,
            user_id=current_user.id,
            request=request,
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при дублировании робота: {str(e)}",
        )


@router.get("/id/{robot_id}", response_model=schemas.RobotInDB)
async def get_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    return schemas.RobotInDB.model_validate(
        await service.robot_service.get_robot_by_id(db, robot_id, current_user.id)
    )


@router.post(
    "/update",
    response_model=schemas.RobotInDB,
    responses={
        409: {
            "description": "Conflict: broker_type is immutable for existing robot",
            "content": {"application/json": {"example": {"detail": "broker_type нельзя изменить для существующего робота"}}},
        }
    },
)
async def update_robot(
        request: schemas.RobotUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    try:
        robot = await service.robot_service.update_robot(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            patch=request.patch
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении робота: {str(e)}"
        )


@router.post("/change_status", response_model=schemas.RobotInDB)
async def change_robot_status(
        request: schemas.ChangeStatusRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):

    if request.status not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Статус должен быть 1 (Включить) или 2 (Выключить)"
        )

    try:
        robot = await service.robot_service.change_robot_status(
            db,
            request.robotId,
            current_user.id,
            request.status
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при изменении статуса робота: {str(e)}"
        )


@router.post("/delete")
async def delete_robot(
        request: schemas.RobotIdRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Мягкое удаление робота (status=0)"""
    try:
        result = await service.robot_service.delete_robot(db, request.robotId, current_user.id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при удалении робота: {str(e)}"
        )


@router.get("/strategies", response_model=schemas.StrategyListResponse)
async def get_strategies(
        current_user: User = Depends(get_current_user)
):
    """Список стратегий и схем параметров для динамической формы на фронтенде."""
    items = await service.robot_service.get_available_strategies()
    return schemas.StrategyListResponse(items=items)


@router.get("/strategies/{name}", response_model=schemas.StrategyInfoResponse)
async def get_strategy_info(
        name: str,
        current_user: User = Depends(get_current_user)
):
    """Детальная информация по конкретной стратегии."""
    return await service.robot_service.get_strategy_info(name)


@router.post(
    "/config",
    response_model=schemas.RobotInDB,
    responses={
        409: {
            "description": "Conflict: broker_type is immutable for existing robot",
            "content": {"application/json": {"example": {"detail": "broker_type нельзя изменить для существующего робота"}}},
        }
    },
)
async def update_robot_config(
        request: schemas.RobotConfigUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление конфигурации робота."""
    try:
        robot = await service.robot_service.update_robot_config(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            config=dict(request.config or {}),
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении конфигурации: {str(e)}"
        )


@router.get(
    "/config-schema/{schema_profile}",
    response_model=schemas.RobotConfigSchemaResponse,
    responses={
        404: {
            "description": "Unknown schema profile",
            "content": {"application/json": {"example": {"detail": "Unknown schema profile: type2_bybit"}}},
        }
    },
)
async def get_robot_config_schema(
        schema_profile: str,
        current_user: User = Depends(get_current_user),
):
    """JSON Schema профиля конфигурации (для UI / IDE)."""
    from app.modules.robots.config.profiles import export_config_schema

    _ = current_user
    try:
        payload = export_config_schema(schema_profile)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown schema profile: {schema_profile}",
        )
    return schemas.RobotConfigSchemaResponse(
        schema_profile=schema_profile,
        json_schema=payload,
    )


@router.post(
    "/validate-config",
    response_model=schemas.RobotValidateConfigResponse,
    responses={
        422: {
            "description": "Validation error",
            "content": {"application/json": {"example": {"detail": "Некорректный config: ..."}}},
        }
    },
)
async def validate_robot_config(
        request: schemas.RobotValidateConfigRequest,
        current_user: User = Depends(get_current_user),
):
    """Проверка/нормализация конфига без сохранения в БД."""
    _ = current_user
    payload = service.robot_service.validate_robot_config_payload(
        robot_type=request.robot_type,
        broker_type=request.broker_type,
        config=request.config,
    )
    return schemas.RobotValidateConfigResponse.model_validate(payload)


@router.post("/schedule", response_model=schemas.RobotInDB)
async def update_robot_schedule(
        request: schemas.RobotScheduleUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление расписания робота в robot_schedules."""
    try:
        robot = await service.robot_service.update_robot_schedule(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            poll_interval_hours=request.poll_interval_hours,
            trading_hours_start=request.trading_hours_start,
            trading_hours_end=request.trading_hours_end,
            allowed_weekdays=request.allowed_weekdays,
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении расписания: {str(e)}"
        )


@router.get("/trading-defaults", response_model=schemas.RobotTradingDefaultsResponse)
async def get_robot_trading_defaults():
    """Доли комиссии и НДФЛ из settings.robots (и .env ROBOTS__*)."""
    from app.core.config import settings
    return schemas.RobotTradingDefaultsResponse(
        broker_commission_rate=float(settings.robots.broker_commission_rate),
        ndfl_rate=float(settings.robots.ndfl_rate),
    )


@router.post(
    "/history-backtest",
    response_model=None,
    responses={
        200: {"model": schemas.RobotHistoryBacktestResponse},
        202: {"model": schemas.RobotHistoryBacktestAsyncAccepted},
    },
)
async def run_robot_history_backtest(
        request: schemas.RobotHistoryBacktestRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Исторический бэктест стратегии робота на свечах T-Invest."""
    from app.core.background_jobs.repository import enqueue_background_job
    from app.core.background_jobs.worker import LANE_HEAVY

    payload = await robot_backtest_usecase.execute(db, current_user.id, request)
    if isinstance(payload, dict) and payload.get("__async_enqueue__"):
        rid = int(payload["run_id"])
        job_id = enqueue_background_job(
            db,
            lane=LANE_HEAVY,
            job_type="history_backtest",
            payload={
                "run_id": rid,
                "user_id": current_user.id,
                "body": request.model_dump(mode="json"),
            },
            idempotency_key=f"history_backtest:{rid}",
        )
        if job_id is None:
            db.execute(
                text(
                    f"""
                    UPDATE {settings.DB_SCHEMA}.backtest_runs
                    SET status = 'FAILED',
                        finished_at = CURRENT_TIMESTAMP,
                        error_message = :err
                    WHERE id = :rid AND status = 'QUEUED'
                    """
                ),
                {
                    "rid": rid,
                    "err": (
                        "enqueue-failed: фоновая задача не создана (дубликат idempotency_key или "
                        "конфликт очереди). Отмените зависший прогон и запустите снова."
                    ),
                },
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Не удалось поставить бэктест в очередь (дубликат или занятая очередь heavy)",
            )
        db.commit()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=schemas.RobotHistoryBacktestAsyncAccepted(
                run_id=rid,
                status="queued",
                message=f"Опросите GET /api/robots/history-backtest/runs/{rid} для статуса и результата."
                + (f" job_id={job_id}" if job_id else ""),
            ).model_dump(),
        )
    return schemas.RobotHistoryBacktestResponse.model_validate(payload)


@router.get("/history-backtest/runs/active")
async def get_active_robot_backtest_run(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    try:
        data = await service.robot_service.get_active_backtest_run(db=db, user_id=current_user.id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_active_robot_backtest_run failed user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить активный прогон",
        )
    if not data:
        return JSONResponse(status_code=200, content=None)
    try:
        return schemas.RobotBacktestRunStatusResponse.model_validate(data)
    except Exception:
        logger.exception(
            "active backtest status validation failed user_id=%s run_id=%s",
            current_user.id,
            data.get("run_id"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Некорректное состояние активного прогона",
        )


@router.get("/history-backtest/runs/{run_id}", response_model=schemas.RobotBacktestRunDetailsResponse)
async def get_robot_backtest_run_by_id(
        run_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_run_details(
        db=db,
        run_id=run_id,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestRunDetailsResponse(**data)


@router.get("/history-backtest/runs/{run_id}/status", response_model=schemas.RobotBacktestRunStatusResponse)
async def get_robot_backtest_run_status(
        run_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_run_status(
        db=db,
        run_id=run_id,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestRunStatusResponse(**data)


@router.post("/history-backtest/runs/{run_id}/cancel", response_model=schemas.RobotBacktestCancelResponse)
async def cancel_robot_backtest_run(
        run_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.request_backtest_cancel(
        db=db,
        run_id=run_id,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestCancelResponse(**data)


@router.post("/live/snapshot", response_model=schemas.RobotLiveSnapshotResponse)
async def get_robot_live_snapshot(
        request: schemas.RobotLiveSnapshotRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await robot_live_snapshot_usecase.execute(db, current_user.id, request.robotId)
    return schemas.RobotLiveSnapshotResponse(**data)


@router.post("/migrate-config-v2", response_model=schemas.RobotMigrateConfigV2Response)
async def migrate_robots_config_v2(
    request: schemas.RobotMigrateConfigV2Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Привести config роботов type=2 к схеме v2 (П1/П2/П3) и сохранить в БД."""
    try:
        data = await service.robot_service.migrate_trading_robots_config_v2(
            db,
            user_id=current_user.id,
            robot_id=request.robotId,
        )
        return schemas.RobotMigrateConfigV2Response(**data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка миграции config v2: {e}",
        ) from e


@router.post("/migrate-config-v3", response_model=schemas.RobotMigrateConfigV3Response)
async def migrate_robots_config_v3(
    request: schemas.RobotMigrateConfigV3Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Привести config роботов type=2 к схеме v3 (schema_profile + config_version=3)."""
    try:
        data = await service.robot_service.migrate_trading_robots_config_v3(
            db,
            user_id=current_user.id,
            robot_id=request.robotId,
        )
        return schemas.RobotMigrateConfigV3Response(**data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка миграции config v3: {e}",
        ) from e


@router.post("/jobs/historical-screening", response_model=schemas.RobotHistoricalScreeningResponse)
async def run_historical_screening_job(
    request: schemas.RobotJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """П1: пересчёт candidate_pool (MOEX lookback + исторические фильтры)."""
    try:
        data = await service.robot_service.run_historical_screening_job(
            db, robot_id=request.robotId, user_id=current_user.id,
        )
        return schemas.RobotHistoricalScreeningResponse(robot_id=request.robotId, **data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка historical screening: {e}",
        ) from e


@router.post("/jobs/paper-selection", response_model=schemas.RobotPaperSelectionResponse)
async def run_paper_selection_job(
    request: schemas.RobotJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """П2: пересчёт tradable_universe и allowed_figis по paper_selection."""
    try:
        data = await service.robot_service.run_paper_selection_job(
            db,
            robot_id=request.robotId,
            user_id=current_user.id,
            force_refresh_snapshot=request.force_refresh_snapshot,
            force_recompute_universe=request.force_recompute_universe,
        )
        return schemas.RobotPaperSelectionResponse(robot_id=request.robotId, **data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка paper selection: {e}",
        ) from e


@router.post("/jobs/crypto-screening", response_model=schemas.RobotCryptoScreeningResponse)
async def run_crypto_screening_job(
    request: schemas.RobotJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crypto-screening: ByBit tickers -> allowed_symbols."""
    try:
        data = await service.robot_service.run_crypto_screening_job(
            db, robot_id=request.robotId, user_id=current_user.id, force=True,
        )
        return schemas.RobotCryptoScreeningResponse(robot_id=request.robotId, **data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка crypto screening: {e}",
        ) from e


@router.get("/{robot_id}/universe/daily", response_model=schemas.RobotUniverseDailyResponse)
async def list_robot_universe_daily(
    robot_id: int,
    trade_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Строки universe за день: MOEX daily_universe или crypto_universe_daily."""
    try:
        data = await service.robot_service.list_universe_daily(
            db, robot_id=robot_id, user_id=current_user.id, trade_date=trade_date,
        )
        return schemas.RobotUniverseDailyResponse(**data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка загрузки universe: {e}",
        ) from e


@router.get("/{robot_id}/universe/active-counts", response_model=schemas.RobotUniverseActiveCountsResponse)
async def get_robot_universe_active_counts(
    robot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Активные инструменты в universe за сегодня и вчера (MOEX daily_universe / crypto_universe_daily)."""
    try:
        data = await service.robot_service.get_universe_active_counts(
            db, robot_id=robot_id, user_id=current_user.id,
        )
        return schemas.RobotUniverseActiveCountsResponse(**data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка загрузки universe counts: {e}",
        ) from e


@router.post("/sync-universe", response_model=schemas.RobotSyncUniverseResponse)
async def sync_robot_universe(
        request: schemas.RobotSyncUniverseRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Пересобрать daily_universe за сегодня и записать allowed_figis в конфиг робота."""
    try:
        data = await service.robot_service.sync_live_universe_from_pipeline(
            db,
            robot_id=request.robotId,
            user_id=current_user.id,
            force_refresh_snapshot=request.force_refresh_snapshot,
            force_recompute_universe=request.force_recompute_universe,
        )
        return schemas.RobotSyncUniverseResponse(robot_id=request.robotId, **data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка пересборки universe: {e}",
        ) from e


@router.post("/history-backtest/list", response_model=schemas.RobotBacktestHistoryResponse)
async def list_robot_backtest_history(
        request: schemas.RobotBacktestHistoryRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_history(
        db=db,
        user_id=current_user.id,
        robot_id=request.robotId,
        limit=request.limit,
        only_active=request.only_active,
        broker_type=request.broker_type,
    )
    return schemas.RobotBacktestHistoryResponse(**data)


@router.post("/history-backtest/run", response_model=schemas.RobotBacktestRunDetailsResponse)
async def get_robot_backtest_run_details(
        request: schemas.RobotBacktestRunRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_run_details(
        db=db,
        run_id=request.runId,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestRunDetailsResponse(**data)


@router.post("/history-backtest/compare", response_model=schemas.RobotBacktestCompareResponse)
async def compare_robot_backtest_runs(
        request: schemas.RobotBacktestCompareRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.compare_backtest_runs(
        db=db,
        base_run_id=request.baseRunId,
        compare_run_id=request.compareRunId,
        user_id=current_user.id,
        name=request.name,
    )
    return schemas.RobotBacktestCompareResponse(**data)


@router.post("/history-backtest/compare/list", response_model=schemas.RobotBacktestCompareListResponse)
async def list_robot_backtest_comparisons(
        request: schemas.RobotBacktestCompareListRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.list_backtest_comparisons(
        db=db,
        user_id=current_user.id,
        limit=request.limit,
        offset=request.offset,
    )
    return schemas.RobotBacktestCompareListResponse(**data)


@router.post("/history-backtest/compare/id", response_model=schemas.RobotBacktestCompareResponse)
async def get_robot_backtest_comparison(
        request: schemas.RobotBacktestCompareIdRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_comparison(
        db=db,
        comparison_id=request.comparisonId,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestCompareResponse(**data)


@router.post("/instruments/auto-select")
async def auto_select_instruments(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Автоподбор топ-20 инструментов по ликвидности."""
    from app.modules.robots.trading.instrument_selector import InstrumentSelector
    from app.modules.tinvest.token_service import token_service

    token_data = await token_service.get_active_token(db, current_user.id)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нет активного токена")

    selector = InstrumentSelector(token_data["token"])
    try:
        instruments = await selector.select_instruments()
        return {"items": instruments, "total": len(instruments)}
    finally:
        await selector.close()


