"""
Загрузка и хранение исторических свечей (общие данные для всех пользователей).
"""
from __future__ import annotations

#///EPIC MarketData.ITEM Service.TOPIC Candle Load Cache Pipeline [1]
#/// Сервис market data: загрузка свечей из внешних источников, нормализация формата,
#/// сохранение в локальный репозиторий и выдача данных для аналитики/бэктеста.
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import httpx
from starlette.concurrency import run_in_threadpool

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.market_data import repository as repo
from app.modules.market_data.candle_format import api_candle_to_db_tuple, db_row_to_api_candle
from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.tinvest.token_service import token_service

CHUNK_DAYS = 365
MOEX_HTTP_RETRIES = 3
MOEX_HTTP_TIMEOUT_SEC = 20


async def _moex_get_json_with_retry(
        url: str,
        *,
        params: Optional[Dict[str, object]] = None,
        timeout: int = MOEX_HTTP_TIMEOUT_SEC,
        retries: int = MOEX_HTTP_RETRIES,
        context: str = "MOEX request",
) -> Dict[str, object]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"{context}: MOEX API error {resp.status_code} (попытка {attempt}/{retries})",
                )
            return resp.json()
        except HTTPException:
            raise
        except httpx.RequestError as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.35 * attempt)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{context}: не удалось подключиться к MOEX ISS (попытка {retries}/{retries})",
    ) from last_exc


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная дата в payload")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная дата в payload")


def _looks_like_figi(value: str) -> bool:
    v = (value or "").strip().upper()
    return len(v) >= 8 and v.startswith("BBG")


async def resolve_figi_and_ticker(
        figi: str,
        ticker: Optional[str],
        data_source: str,
        token: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    src = (data_source or "tinvest").strip().lower()
    figi_in = (figi or "").strip().upper()
    ticker_in = (ticker or "").strip().upper() or None

    if src == "moex":
        # Для MOEX в качестве figi-ключа допускаем тикер (например SBER).
        if not figi_in and ticker_in:
            return ticker_in, ticker_in, None
        if figi_in and not ticker_in and not _looks_like_figi(figi_in):
            return figi_in, figi_in, None
        return figi_in, ticker_in, None

    # T-Invest: если в поле figi ввели тикер, пробуем разрешить в настоящий FIGI.
    if _looks_like_figi(figi_in):
        return figi_in, ticker_in, None
    lookup_ticker = ticker_in or figi_in
    if not lookup_ticker:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите FIGI или ticker")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для поиска FIGI по ticker нужен токен T-Invest")
    client = InstrumentsClient(token)
    for getter in (client.get_shares, client.get_etfs, client.get_bonds):
        items = await getter()
        for row in items or []:
            tk = str(row.get("ticker") or "").upper()
            fg = str(row.get("figi") or "").upper()
            if tk == lookup_ticker and fg:
                return fg, tk, row.get("name")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Не найден инструмент по ticker '{lookup_ticker}' в T-Invest",
    )


async def resolve_market_sync_token(db: Session, user_id: int, token_id: Optional[int]) -> str:
    if settings.TINVEST_MARKET_DATA_TOKEN:
        return settings.TINVEST_MARKET_DATA_TOKEN.strip()
    if token_id is not None:
        row = await token_service.get_token_by_id(db, token_id, user_id)
        if not row or not row.get("token"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Указанный token_id недоступен")
        return row["token"]
    active = await token_service.get_active_token(db, user_id)
    if active and active.get("token"):
        return active["token"]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Нужен токен T-Invest: задайте TINVEST_MARKET_DATA_TOKEN или передайте token_id / добавьте активный токен",
    )


async def _fetch_range_chunks(
        client: InstrumentsClient,
        figi: str,
        interval: str,
        start: datetime,
        end: datetime,
) -> List[Tuple]:
    rows: List[Tuple] = []
    cur = _utc(start)
    end_u = _utc(end)
    if cur >= end_u:
        return rows
    while cur < end_u:
        chunk_end = min(end_u, cur + timedelta(days=CHUNK_DAYS))
        raw = await client.get_candles(figi, cur, chunk_end, interval)
        for c in raw or []:
            rows.append(api_candle_to_db_tuple(c, figi, interval))
        cur = chunk_end
    return rows


async def _fetch_moex_range_chunks(
        figi: str,
        ticker: Optional[str],
        start: datetime,
        end: datetime,
        interval: str,
) -> List[Tuple]:
    moex_interval_map = {
        "CANDLE_INTERVAL_1_MIN": 1,
        "CANDLE_INTERVAL_10_MIN": 10,
        "CANDLE_INTERVAL_HOUR": 60,
        "CANDLE_INTERVAL_DAY": 24,
        "CANDLE_INTERVAL_WEEK": 7,
        "CANDLE_INTERVAL_MONTH": 31,
    }
    if interval not in moex_interval_map:
        supported = ", ".join(moex_interval_map.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MOEX источник не поддерживает интервал: {interval}. Поддерживаются: {supported}",
        )
    moex_interval = moex_interval_map[interval]
    secid = (ticker or figi).strip().upper()
    if not secid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для MOEX нужен ticker или figi")

    async def resolve_board_and_market(security_id: str) -> Tuple[str, str]:
        meta_url = f"https://iss.moex.com/iss/securities/{security_id}.json"
        try:
            payload = await _moex_get_json_with_retry(
                meta_url,
                timeout=15,
                retries=2,
                context=f"MOEX metadata {security_id}",
            )
        except (httpx.RequestError, HTTPException):
            # Не блокируем бэктест из-за мета-запроса: используем дефолтную доску.
            return "TQBR", "shares"
        boards = payload.get("boards", {})
        cols = boards.get("columns", []) or []
        data = boards.get("data", []) or []
        if not data or not cols:
            return "TQBR", "shares"
        idx = {name: i for i, name in enumerate(cols)}
        chosen = None
        for item in data:
            engine = str(item[idx["engine"]] if "engine" in idx else "")
            market = str(item[idx["market"]] if "market" in idx else "")
            primary = int(item[idx["is_primary"]] if "is_primary" in idx and item[idx["is_primary"]] is not None else 0)
            if engine == "stock" and market == "shares" and primary == 1:
                chosen = item
                break
        if chosen is None:
            for item in data:
                engine = str(item[idx["engine"]] if "engine" in idx else "")
                market = str(item[idx["market"]] if "market" in idx else "")
                if engine == "stock" and market == "shares":
                    chosen = item
                    break
        if chosen is None:
            chosen = data[0]
        board = str(chosen[idx["boardid"]] if "boardid" in idx else "TQBR")
        market = str(chosen[idx["market"]] if "market" in idx else "shares")
        return board, market

    board, market = await resolve_board_and_market(secid)
    rows: List[Tuple] = []
    cur = _utc(start)
    end_u = _utc(end)
    while cur < end_u:
        chunk_end = min(end_u, cur + timedelta(days=365))
        url = f"https://iss.moex.com/iss/engines/stock/markets/{market}/boards/{board}/securities/{secid}/candles.json"
        start_offset = 0
        while True:
            params = {
                "from": cur.date().isoformat(),
                "till": chunk_end.date().isoformat(),
                "interval": moex_interval,
                "start": start_offset,
            }
            payload = await _moex_get_json_with_retry(
                url,
                params=params,
                timeout=MOEX_HTTP_TIMEOUT_SEC,
                retries=MOEX_HTTP_RETRIES,
                context=(
                    "Загрузка свечей MOEX "
                    f"{secid} {cur.date().isoformat()}..{chunk_end.date().isoformat()}"
                ),
            )
            candles = payload.get("candles", {})
            cols = candles.get("columns", []) or []
            data = candles.get("data", []) or []
            if not data:
                break
            idx = {name: i for i, name in enumerate(cols)}
            for item in data:
                begin = item[idx["begin"]] if "begin" in idx else None
                if not begin:
                    continue
                ts = _utc(datetime.fromisoformat(str(begin).replace("Z", "+00:00")))
                o = Decimal(str(item[idx["open"]])) if "open" in idx and item[idx["open"]] is not None else Decimal(0)
                h = Decimal(str(item[idx["high"]])) if "high" in idx and item[idx["high"]] is not None else o
                l = Decimal(str(item[idx["low"]])) if "low" in idx and item[idx["low"]] is not None else o
                c = Decimal(str(item[idx["close"]])) if "close" in idx and item[idx["close"]] is not None else o
                vol = int(item[idx["volume"]]) if "volume" in idx and item[idx["volume"]] is not None else None
                rows.append((figi, interval, ts, o, h, l, c, vol))
            if len(data) < 500:
                break
            start_offset += len(data)
        cur = chunk_end
    return rows


async def sync_candles_for_range(
        db: Session,
        figi: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
        token: str,
        ticker: Optional[str] = None,
        name: Optional[str] = None,
        data_source: str = "tinvest",
) -> int:
    """Подкачивает свечи за интервал [from_dt, to_dt], upsert в БД. Возвращает число сохранённых строк."""
    schema = settings.DB_SCHEMA
    source = (data_source or "tinvest").strip().lower()
    if source == "moex":
        if not ticker:
            ticker = repo.get_instrument_ticker(db, schema, figi)
        rows = await _fetch_moex_range_chunks(figi, ticker, from_dt, to_dt, interval)
    else:
        client = InstrumentsClient(token)
        rows = await _fetch_range_chunks(client, figi, interval, from_dt, to_dt)
    await run_in_threadpool(repo.upsert_instrument, db, schema, figi, ticker, name, None)
    await run_in_threadpool(repo.upsert_candles_batch, db, schema, rows)
    await run_in_threadpool(db.commit)
    return len(rows)


async def ensure_candles_cover_window(
        db: Session,
        figi: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
        token: str,
        data_source: str = "tinvest",
        ticker: Optional[str] = None,
) -> List[str]:
    """Дозагружает недостающие хвосты относительно уже имеющихся данных в БД."""
    schema = settings.DB_SCHEMA
    from_u = _utc(from_dt)
    to_u = _utc(to_dt)
    stages: List[str] = [
        "Проверяем свечи в базе...",
    ]
    bounds = await run_in_threadpool(repo.fetch_coverage_bounds, db, schema, figi, interval)
    source = (data_source or "tinvest").strip().lower()
    client = InstrumentsClient(token) if source != "moex" else None
    if source == "moex" and not ticker:
        ticker = await run_in_threadpool(repo.get_instrument_ticker, db, schema, figi)
    total_rows = 0
    if bounds is None:
        stages.append("Свечи не найдены - запрашиваем...")
        rows = await (
            _fetch_moex_range_chunks(figi, ticker, from_u, to_u, interval)
            if source == "moex"
            else _fetch_range_chunks(client, figi, interval, from_u, to_u)
        )
        await run_in_threadpool(repo.upsert_instrument, db, schema, figi, None, None, None)
        await run_in_threadpool(repo.upsert_candles_batch, db, schema, rows)
        total_rows += len(rows)
    else:
        mn, mx = bounds
        mn = _utc(mn)
        mx = _utc(mx)
        if from_u < mn:
            stages.append("Недостаточно данных в начале диапазона - дозагружаем...")
            rows = await (
                _fetch_moex_range_chunks(figi, ticker, from_u, mn, interval)
                if source == "moex"
                else _fetch_range_chunks(client, figi, interval, from_u, mn)
            )
            await run_in_threadpool(repo.upsert_candles_batch, db, schema, rows)
            total_rows += len(rows)
        if to_u > mx:
            stages.append("Недостаточно данных в конце диапазона - дозагружаем...")
            rows = await (
                _fetch_moex_range_chunks(figi, ticker, mx, to_u, interval)
                if source == "moex"
                else _fetch_range_chunks(client, figi, interval, mx, to_u)
            )
            await run_in_threadpool(repo.upsert_candles_batch, db, schema, rows)
            total_rows += len(rows)
    await run_in_threadpool(db.commit)
    if total_rows > 0:
        stages.append(f"Свечи загружены: {total_rows}")
    else:
        stages.append("Свечи уже есть в базе.")
    return stages


async def sync_history_years(
        db: Session,
        figi: str,
        interval: str,
        years: int,
        token: str,
        ticker: Optional[str] = None,
        name: Optional[str] = None,
        data_source: str = "tinvest",
) -> Dict[str, Any]:
    years = max(1, min(int(years), 15))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years)
    n = await sync_candles_for_range(db, figi, interval, start, end, token, ticker=ticker, name=name, data_source=data_source)
    return {"figi": figi, "interval": interval, "years": years, "rows_upserted": n}


def load_candles_for_backtest(
        db: Session,
        figi: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
) -> List[Dict[str, Any]]:
    schema = settings.DB_SCHEMA
    rows = repo.fetch_candles_range(db, schema, figi, interval, _utc(from_dt), _utc(to_dt))
    return [db_row_to_api_candle(r) for r in rows]


def list_instruments(db: Session) -> List[Dict[str, Any]]:
    schema = settings.DB_SCHEMA
    out = []
    for row in repo.list_instruments_with_data(db, schema):
        out.append({
            "figi": row[0],
            "ticker": row[1],
            "name": row[2],
            "instrument_type": row[3],
            "candle_interval": row[4],
            "first_candle_at": row[5].isoformat() if row[5] else None,
            "last_candle_at": row[6].isoformat() if row[6] else None,
            "candle_count": int(row[7]) if row[7] is not None else 0,
        })
    return out


def save_backtest(
        db: Session,
        user_id: int,
        name: Optional[str],
        request_payload: Dict[str, Any],
        result_payload: Dict[str, Any],
) -> int:
    schema = settings.DB_SCHEMA
    figi = str(request_payload.get("figi") or "").strip()
    strategy = str(request_payload.get("strategy") or "").strip()
    interval = str(request_payload.get("candle_interval") or "CANDLE_INTERVAL_DAY").strip()
    from_dt = _coerce_datetime(request_payload.get("from_date"))
    to_dt = _coerce_datetime(request_payload.get("to_date"))
    initial_capital = float(request_payload.get("initial_capital") or 1_000_000)
    if not figi or not strategy:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request_payload должен содержать figi и strategy")
    bt_id = repo.insert_backtest(
        db=db,
        schema=schema,
        user_id=user_id,
        name=name.strip() if isinstance(name, str) and name.strip() else None,
        figi=figi,
        candle_interval=interval,
        strategy=strategy,
        from_dt=from_dt,
        to_dt=to_dt,
        initial_capital=initial_capital,
        request_payload=request_payload,
        result_payload=result_payload,
    )
    db.commit()
    return int(bt_id)


def list_backtests(db: Session, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    schema = settings.DB_SCHEMA
    out = []
    for row in repo.list_backtests(db, schema, user_id, limit=max(1, min(limit, 200))):
        out.append({
            "id": int(row[0]),
            "user_id": int(row[1]),
            "name": row[2],
            "figi": row[3],
            "candle_interval": row[4],
            "strategy": row[5],
            "from_date": row[6].isoformat() if row[6] else "",
            "to_date": row[7].isoformat() if row[7] else "",
            "initial_capital": float(row[8]) if row[8] is not None else 0.0,
            "request_payload": row[9] or {},
            "result_payload": row[10] or {},
            "created_at": row[11].isoformat() if row[11] else "",
        })
    return out


async def get_imoex_return_percent(from_dt: datetime, to_dt: datetime) -> Optional[float]:
    """
    Доходность IMOEX за период в процентах.
    Использует MOEX ISS свечи (дневной интервал) по индексу IMOEX.
    """
    start = _utc(from_dt)
    end = _utc(to_dt)
    if start >= end:
        return None
    rows = await _fetch_moex_range_chunks(
        figi="IMOEX",
        ticker="IMOEX",
        start=start,
        end=end,
        interval="CANDLE_INTERVAL_DAY",
    )
    if not rows:
        return None
    rows_sorted = sorted(rows, key=lambda x: x[2])
    first_close = float(rows_sorted[0][6] or 0.0)
    last_close = float(rows_sorted[-1][6] or 0.0)
    if abs(first_close) < 1e-9:
        return None
    return ((last_close - first_close) / first_close) * 100.0


async def ensure_and_load_candles(
        db: Session,
        user_id: int,
        figi: str,
        ticker: Optional[str],
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
        data_source: str = "moex",
        token_id: Optional[int] = None,
        name: Optional[str] = None,
) -> Dict[str, Any]:
    stages: List[str] = []
    source = (data_source or "moex").strip().lower()
    stages.append("Старт проверки инструмента и диапазона")
    token = ""
    if source != "moex":
        stages.append("Получение токена T-Invest")
        token = await resolve_market_sync_token(db, user_id, token_id)
    stages.append("Разрешение FIGI/ticker")
    figi_resolved, ticker_resolved, name_resolved = await resolve_figi_and_ticker(
        figi=figi,
        ticker=ticker,
        data_source=source,
        token=token,
    )
    schema = settings.DB_SCHEMA
    stages.append("Проверка покрытия диапазона в БД")
    bounds = await run_in_threadpool(repo.fetch_coverage_bounds, db, schema, figi_resolved, interval)
    from_u = _utc(from_dt)
    to_u = _utc(to_dt)
    was_full_in_db = bool(bounds and _utc(bounds[0]) <= from_u and _utc(bounds[1]) >= to_u)
    rows_loaded = 0
    if not was_full_in_db:
        stages.append("Дозагрузка недостающих свечей из внешнего источника")
        before = len(await run_in_threadpool(load_candles_for_backtest, db, figi_resolved, interval, from_u, to_u))
        await ensure_candles_cover_window(
            db=db,
            figi=figi_resolved,
            interval=interval,
            from_dt=from_u,
            to_dt=to_u,
            token=token,
            data_source=source,
            ticker=ticker_resolved,
        )
        await run_in_threadpool(repo.upsert_instrument, db, schema, figi_resolved, ticker_resolved, name or name_resolved, None)
        await run_in_threadpool(db.commit)
        stages.append("Сохранение/обновление данных в БД завершено")
        after = len(await run_in_threadpool(load_candles_for_backtest, db, figi_resolved, interval, from_u, to_u))
        rows_loaded = max(0, after - before)
    else:
        stages.append("Данные за период уже полностью есть в БД")
    stages.append("Формирование ответа со свечами")
    candles = await run_in_threadpool(load_candles_for_backtest, db, figi_resolved, interval, from_u, to_u)
    return {
        "figi": figi_resolved,
        "ticker": ticker_resolved,
        "candle_interval": interval,
        "from_date": from_u.isoformat(),
        "to_date": to_u.isoformat(),
        "was_full_in_db": was_full_in_db,
        "rows_loaded": rows_loaded,
        "candle_count": len(candles),
        "stages": stages,
        "candles": candles,
    }
