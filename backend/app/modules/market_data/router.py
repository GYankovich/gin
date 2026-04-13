from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.market_data import schemas
from app.modules.market_data import service as market_service
from app.modules.robots.schemas import RobotHistoryBacktestResponse, RobotHistoryBacktestTrade
from app.modules.robots.trading.backtest.engine import run_backtest_simulation

router = APIRouter(prefix="/market", tags=["Market data"])


def _normalize_window_dates(from_dt: datetime, to_dt: datetime) -> tuple[datetime, datetime]:
    # Нормализуем до даты (dd-mm-yyyy semantics):
    # from -> начало дня UTC, to -> конец дня UTC.
    from_day = datetime(from_dt.year, from_dt.month, from_dt.day, 0, 0, 0, tzinfo=timezone.utc)
    to_day = datetime(to_dt.year, to_dt.month, to_dt.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return from_day, to_day


@router.get("/instruments", response_model=schemas.MarketInstrumentListResponse)
def list_market_instruments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Справочник инструментов с загруженными в БД свечами (общие данные)."""
    items = market_service.list_instruments(db)
    return schemas.MarketInstrumentListResponse(
        items=[schemas.MarketInstrumentRow(**x) for x in items]
    )


@router.post("/sync", response_model=schemas.MarketSyncResponse)
async def sync_market_history(
        body: schemas.MarketSyncRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Загрузить историю свечей в общую БД (по FIGI). Токен — системный или пользовательский."""
    source = (body.data_source or "tinvest").strip().lower()
    token = ""
    if source != "moex":
        token = await market_service.resolve_market_sync_token(db, current_user.id, body.token_id)
    figi_resolved, ticker_resolved, name_resolved = await market_service.resolve_figi_and_ticker(
        figi=body.figi,
        ticker=body.ticker,
        data_source=source,
        token=token,
    )
    try:
        if body.from_date and body.to_date:
            rows = await market_service.sync_candles_for_range(
                db=db,
                figi=figi_resolved,
                interval=body.candle_interval,
                from_dt=body.from_date,
                to_dt=body.to_date,
                token=token,
                ticker=ticker_resolved,
                name=body.name or name_resolved,
                data_source=source,
            )
            res = {"figi": figi_resolved, "interval": body.candle_interval, "years": 0, "rows_upserted": rows}
        else:
            res = await market_service.sync_history_years(
                db, figi_resolved, body.candle_interval, body.years, token,
                ticker=ticker_resolved, name=body.name or name_resolved, data_source=source,
            )
        return schemas.MarketSyncResponse(
            figi=res["figi"],
            interval=res["interval"],
            years=res["years"],
            rows_upserted=res["rows_upserted"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ошибка загрузки свечей: {e}",
        )


@router.post("/backtest", response_model=RobotHistoryBacktestResponse)
async def run_market_backtest(
        body: schemas.MarketBacktestRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Бэктест по свечам из БД; при необходимости дозагрузка через токен."""
    source = (body.data_source or "tinvest").strip().lower()
    token = ""
    if source != "moex":
        token = await market_service.resolve_market_sync_token(db, current_user.id, body.token_id)
    figi_resolved, ticker_resolved, _ = await market_service.resolve_figi_and_ticker(
        figi=body.figi,
        ticker=body.ticker,
        data_source=source,
        token=token or "",
    )
    from_dt, to_dt = _normalize_window_dates(body.from_date, body.to_date)

    try:
        stages = await market_service.ensure_candles_cover_window(
            db, figi_resolved, body.candle_interval, from_dt, to_dt, token,
            data_source=source,
            ticker=ticker_resolved,
        )
        candles = market_service.load_candles_for_backtest(
            db, figi_resolved, body.candle_interval, from_dt, to_dt,
        )
    except HTTPException:
        raise
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MOEX недоступен: ошибка подключения при загрузке свечей.",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ошибка подготовки свечей для бэктеста: {e}",
        ) from e
    if len(candles) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недостаточно свечей за период даже после автодозагрузки. Проверьте инструмент, интервал и диапазон дат.",
        )

    sp = dict(body.strategy_params or {})
    sp["figis"] = [figi_resolved]
    if "interval" not in sp:
        sp["interval"] = body.candle_interval

    result = await run_backtest_simulation(
        candles_by_figi={figi_resolved: candles},
        strategy_name=body.strategy,
        strategy_params=sp,
        risk_params=dict(body.risk or {}),
        initial_capital=body.initial_capital,
        cost_override=body.costs or None,
        robot_config_for_cost_defaults=None,
    )

    return RobotHistoryBacktestResponse(
        initial_capital=result.initial_capital,
        final_equity=result.final_equity,
        total_return_percent=result.total_return_percent,
        max_drawdown_percent=result.max_drawdown_percent,
        trades=[RobotHistoryBacktestTrade.model_validate(t) for t in result.trades],
        equity_curve=result.equity_curve,
        stages=stages + ["Тестируем...", "Бэктест завершен"],
    )


@router.post("/backtests", status_code=status.HTTP_201_CREATED)
def save_market_backtest(
        body: schemas.MarketBacktestSaveRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    bt_id = market_service.save_backtest(
        db=db,
        user_id=current_user.id,
        name=body.name,
        request_payload=body.request_payload,
        result_payload=body.result_payload,
    )
    return {"id": bt_id}


@router.post("/ensure-candles", response_model=schemas.MarketEnsureCandlesResponse)
async def ensure_candles_for_range(
        body: schemas.MarketEnsureCandlesRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    res = await market_service.ensure_and_load_candles(
        db=db,
        user_id=current_user.id,
        figi=body.figi,
        ticker=body.ticker,
        interval=body.candle_interval,
        from_dt=body.from_date,
        to_dt=body.to_date,
        data_source=body.data_source,
        token_id=body.token_id,
        name=body.name,
    )
    return schemas.MarketEnsureCandlesResponse(**res)


@router.get("/backtests", response_model=schemas.MarketBacktestListResponse)
def list_market_backtests(
        limit: int = Query(default=30, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    items = market_service.list_backtests(db, current_user.id, limit=limit)
    return schemas.MarketBacktestListResponse(
        items=[schemas.MarketBacktestSavedItem(**x) for x in items]
    )
