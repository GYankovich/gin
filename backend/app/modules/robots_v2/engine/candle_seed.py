"""Bootstrap OHLCV history for robots v2 strategy warmup."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.robots.trading.contracts import Candle
from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows_bulk
from app.modules.robots.trading.intervals import (
    normalize_interval,
    resolve_strategy_interval,
)
from app.modules.robots_v2.config.v4_schema import (
    GridParams,
    MomentumParams,
    ReversionParams,
    TradingRobotConfigV4,
)
from app.modules.robots_v2.universe.token_context import TokenContext

logger = logging.getLogger(__name__)

_SEED_CONCURRENCY = 4
_MAX_SEED_BARS = 200


def warmup_bars_needed(config: TradingRobotConfigV4) -> int:
    arch = config.strategy.archetype
    params = config.strategy.params or {}
    if arch == "momentum":
        p = MomentumParams.model_validate(params)
        return p.ma_period + p.breakout_lookback
    if arch == "reversion":
        p = ReversionParams.model_validate(params)
        return p.rsi_period + 5
    if arch == "grid":
        GridParams.model_validate(params)
        return 19
    return 0


def lookback_days_for_warmup(*, timeframe: str, need_bars: int) -> int:
    """Calendar days of history to cover need_bars on MOEX-ish sessions."""
    resolved = resolve_strategy_interval(timeframe)
    minutes = int(resolved.code_num or 60)
    if minutes >= 24:  # day/week codes
        return max(need_bars + 10, 40)
    # ~6.5h MOEX cash session ≈ 390 minutes / bar_minutes bars per day
    bars_per_day = max(1, int(390 / max(minutes, 1)))
    days = int((need_bars / bars_per_day) * 1.6) + 5
    return max(7, min(days, 120))


def _parse_candle_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        # seconds or ms
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_candle_time(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _is_tinvest_candle_row(row: dict[str, Any]) -> bool:
    close = row.get("close")
    return isinstance(close, dict) and ("units" in close or "nano" in close)


def _row_to_candle(row: Any, *, tf: str, ticker: str) -> Candle | None:
    try:
        if hasattr(row, "_mapping"):
            m = dict(row._mapping)
        elif isinstance(row, dict):
            m = row
        else:
            m = {
                "candle_time": getattr(row, "candle_time", None),
                "time": getattr(row, "time", None),
                "open": getattr(row, "open", None),
                "high": getattr(row, "high", None),
                "low": getattr(row, "low", None),
                "close": getattr(row, "close", None),
                "volume": getattr(row, "volume", None),
            }
        if isinstance(m, dict) and _is_tinvest_candle_row(m):
            c = Candle.from_tinvest_dict(m, interval=tf, secid=ticker.upper())
            return c if c.close > 0 else None
        ct = _parse_candle_time(m.get("candle_time") or m.get("time"))
        if ct is None:
            return None
        close = float(m.get("close") or 0)
        if close <= 0:
            return None
        return Candle(
            interval=tf,
            time=ct,
            open=float(m.get("open") or close),
            high=float(m.get("high") or close),
            low=float(m.get("low") or close),
            close=close,
            volume=float(m.get("volume") or 0),
            secid=ticker.upper(),
        )
    except (TypeError, ValueError, KeyError):
        return None


def _load_from_cache(
    db: Session,
    *,
    market: str,
    ids: list[str],
    interval_code: str,
    interval_code_num: int,
    from_dt: datetime,
    to_dt: datetime,
) -> dict[str, list[Any]]:
    if not ids:
        return {}
    return query_candles_cache_rows_bulk(
        db,
        market=market,
        instrument_ids=ids,
        interval_code=interval_code,
        interval_code_num=interval_code_num,
        from_dt=from_dt,
        to_dt_exclusive=to_dt,
    ) or {}


async def seed_candle_history(
    *,
    config: TradingRobotConfigV4,
    universe: list[str],
    token_ctx: TokenContext,
    instrument_map: dict[str, str],
    log: Any | None = None,
    robot_id: int | None = None,
) -> dict[str, list[Candle]]:
    """
    Prefill candle_history for strategy warmup.

    1) DB candles_cache by ticker + FIGI/symbol
    2) Broker REST get_candles for tickers still short of warmup
    """
    arch = config.strategy.archetype
    if arch not in ("momentum", "reversion", "grid") or not universe:
        return {}

    def _log(msg: str) -> None:
        if log is not None:
            log.info(msg)
        else:
            logger.info(msg)

    need = warmup_bars_needed(config)
    if need <= 0:
        return {}

    tf = config.strategy.timeframe or "5m"
    resolved = resolve_strategy_interval(tf)
    interval_code = resolved.cache_label
    interval_code_num = int(resolved.code_num)
    days = lookback_days_for_warmup(timeframe=tf, need_bars=need)
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=days)
    cache_market = "bybit" if token_ctx.market == "crypto" else "moex"

    # Collect cache ids: tickers + mapped instrument ids (FIGI)
    ticker_to_iid = {
        t.upper(): str(instrument_map.get(t.upper()) or t).upper()
        for t in universe
    }
    cache_ids = sorted({*ticker_to_iid.keys(), *ticker_to_iid.values()})

    db = SessionLocal()
    try:
        grouped = _load_from_cache(
            db,
            market=cache_market,
            ids=cache_ids,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt=to_dt,
        )
    finally:
        db.close()

    out: dict[str, list[Candle]] = {}
    for ticker in universe:
        t = ticker.upper()
        iid = ticker_to_iid.get(t, t)
        rows = grouped.get(t) or grouped.get(iid) or []
        candles: list[Candle] = []
        for row in rows[-_MAX_SEED_BARS:]:
            c = _row_to_candle(row, tf=tf, ticker=t)
            if c is not None:
                candles.append(c)
        if candles:
            out[t] = candles

    cache_ok = sum(1 for t in universe if len(out.get(t.upper()) or []) >= need)
    _log(
        f"Candle seed cache interval={interval_code} need={need} "
        f"ready={cache_ok}/{len(universe)} lookbackDays={days}"
    )

    short = [t.upper() for t in universe if len(out.get(t.upper()) or []) < need]
    if not short:
        return out

    # Broker REST fill for remaining (T-Invest needs real FIGI, not ticker)
    from app.modules.robots_v2.engine.broker_factory import (
        _looks_like_figi,
        create_broker_from_token,
    )

    broker = create_broker_from_token(
        token_ctx,
        instrument_type=config.core.instrument_type,
        robot_id=robot_id,
    )
    broker_interval = normalize_interval(tf, getattr(broker, "broker_type", token_ctx.broker) if broker else token_ctx.broker)
    rest_attempted = 0
    rest_skipped_no_figi = 0

    def _merge_into(ticker: str, candles: list[Candle]) -> None:
        if not candles:
            return
        existing = out.get(ticker) or []
        if len(candles) >= len(existing):
            out[ticker] = candles
            return
        by_t = {str(c.time): c for c in existing}
        for c in candles:
            by_t[str(c.time)] = c
        merged = [by_t[k] for k in sorted(by_t.keys())]
        out[ticker] = merged[-_MAX_SEED_BARS:]

    if broker is None:
        _log(f"Candle seed broker unavailable — short={len(short)}")
    else:
        sem = asyncio.Semaphore(_SEED_CONCURRENCY)

        async def _fetch_one(ticker: str) -> tuple[str, list[Candle], str | None]:
            iid = ticker_to_iid.get(ticker, ticker)
            if token_ctx.broker == "tinvest" and not _looks_like_figi(iid):
                return ticker, [], "no_figi"
            async with sem:
                try:
                    raw = await broker.get_candles(iid, from_dt, to_dt, broker_interval)
                except Exception as exc:
                    logger.warning(
                        "candle seed REST failed ticker=%s iid=%s: %s", ticker, iid, exc
                    )
                    return ticker, [], "error"
            candles: list[Candle] = []
            for row in raw or []:
                c = _row_to_candle(row, tf=tf, ticker=ticker)
                if c is not None and c.close > 0:
                    candles.append(c)
            candles.sort(
                key=lambda x: x.time if x.time is not None else datetime.min.replace(tzinfo=timezone.utc)
            )
            return ticker, candles[-_MAX_SEED_BARS:], None

        try:
            results = await asyncio.gather(*[_fetch_one(t) for t in short])
        finally:
            close = getattr(broker, "close", None)
            if callable(close):
                try:
                    maybe = close()
                    if asyncio.iscoroutine(maybe):
                        await maybe
                except Exception:
                    pass

        fetched_ok = 0
        for ticker, candles, err in results:
            if err == "no_figi":
                rest_skipped_no_figi += 1
                continue
            rest_attempted += 1
            if not candles:
                continue
            _merge_into(ticker, candles)
            if len(out.get(ticker) or []) >= need:
                fetched_ok += 1

        ready = sum(1 for t in universe if len(out.get(t.upper()) or []) >= need)
        _log(
            f"Candle seed REST interval={broker_interval} fetched={fetched_ok}/{len(short)} "
            f"attempted={rest_attempted} skippedNoFigi={rest_skipped_no_figi} "
            f"ready={ready}/{len(universe)} need={need}"
        )

    # MOEX ISS fallback — works with ticker, no FIGI required
    short = [t.upper() for t in universe if len(out.get(t.upper()) or []) < need]
    if short and token_ctx.market == "moex":
        moex_ok = await _seed_from_moex(
            tickers=short,
            tf=tf,
            broker_interval=broker_interval,
            from_dt=from_dt,
            to_dt=to_dt,
            need=need,
            out=out,
            merge=_merge_into,
        )
        ready = sum(1 for t in universe if len(out.get(t.upper()) or []) >= need)
        _log(
            f"Candle seed MOEX filled={moex_ok}/{len(short)} "
            f"ready={ready}/{len(universe)} need={need}"
        )

    return out


async def _seed_from_moex(
    *,
    tickers: list[str],
    tf: str,
    broker_interval: str,
    from_dt: datetime,
    to_dt: datetime,
    need: int,
    out: dict[str, list[Candle]],
    merge,
) -> int:
    """Fetch OHLCV from MOEX ISS for tickers still short of warmup."""
    from app.modules.market_data.service import _fetch_moex_range_chunks

    sem = asyncio.Semaphore(_SEED_CONCURRENCY)
    filled = 0

    async def _one(ticker: str) -> tuple[str, list[Candle]]:
        async with sem:
            try:
                rows = await _fetch_moex_range_chunks(
                    ticker, ticker, from_dt, to_dt, broker_interval
                )
            except Exception as exc:
                logger.warning("candle seed MOEX failed ticker=%s: %s", ticker, exc)
                return ticker, []
        candles: list[Candle] = []
        for row in rows or []:
            # (figi, interval, ts, o, h, l, c, vol)
            try:
                _, _, ts, o, h, low, c, vol = row
                close = float(c or 0)
                if close <= 0:
                    continue
                ct = ts if isinstance(ts, datetime) else _parse_candle_time(ts)
                if ct is None:
                    continue
                candles.append(
                    Candle(
                        interval=tf,
                        time=ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc),
                        open=float(o or close),
                        high=float(h or close),
                        low=float(low or close),
                        close=close,
                        volume=int(vol or 0),
                        secid=ticker,
                    )
                )
            except (TypeError, ValueError, IndexError):
                continue
        candles.sort(
            key=lambda x: x.time if x.time is not None else datetime.min.replace(tzinfo=timezone.utc)
        )
        return ticker, candles[-_MAX_SEED_BARS:]

    results = await asyncio.gather(*[_one(t) for t in tickers])
    for ticker, candles in results:
        if not candles:
            continue
        merge(ticker, candles)
        if len(out.get(ticker) or []) >= need:
            filled += 1
    return filled
