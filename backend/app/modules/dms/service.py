import hashlib
import json
from datetime import date, datetime, timezone, timedelta, time
from typing import Any, Callable, Dict, Optional, List
import httpx

from fastapi import HTTPException, status
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.universe import (
    UNIVERSE_MODE_FIXED,
    UNIVERSE_MODE_TQBR,
    normalize_universe_mode,
    universe_min_tradable_row,
    universe_uses_pipeline,
    universe_whitelist_tickers,
)
from app.modules.dms.models import CandleCache
from app.modules.moex.http_gate import moex_http_acquire


class DmsService:
    FILTER_COST_ORDER = {
        "security_status": 1,
        "trading_status": 2,
        "last_price": 3,
        "allowed_tickers": 4,
        "excluded_tickers": 5,
        "exclude_tickers": 5,
        "only_tickers": 6,
        "volume": 7,
        "volume_lots": 8,
        "turnover": 8,
        "num_trades": 9,
        "gap_retention": 9,
        "gap": 10,
        "price_vs_open": 10,
        "spread": 11,
        "opening_range": 11,
        "capitalization": 12,
        "min_step_ratio": 13,
        "atr": 100,
    }

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _interval_code_to_cache_label(interval_code: int) -> str:
        if int(interval_code) == 5:
            return "M5"
        if int(interval_code) == 24:
            return "D1"
        return f"I{interval_code}"

    async def _fetch_moex_candles(
        self,
        db: Session,
        *,
        board: str,
        ticker: str,
        interval_code: int,
        days_back: int,
        from_date: Optional[str] = None,
        till_date: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not from_date:
            from_date = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days_back)))).date().isoformat()
        if not till_date:
            till_date = datetime.now(timezone.utc).date().isoformat()
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities/{ticker}/candles.json"
        params = {
            "iss.meta": "off",
            "interval": int(interval_code),
            "from": from_date,
            "till": till_date,
        }
        started_at = datetime.now(timezone.utc)
        try:
            async with moex_http_acquire():
                async with httpx.AsyncClient(timeout=20, verify=False) as client:
                    resp = await client.get(url, params=params)
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            self._log_external_api_call(
                db,
                endpoint=url,
                request_data={"params": dict(params)},
                response_status=None,
                response_data={},
                started_at=started_at,
                finished_at=finished_at,
                success=False,
                error_message=str(e),
                user_id=user_id,
            )
            return []
        finished_at = datetime.now(timezone.utc)
        payload: Dict[str, Any] = {}
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        self._log_external_api_call(
            db,
            endpoint=url,
            request_data={"params": dict(params)},
            response_status=resp.status_code,
            response_data=payload,
            started_at=started_at,
            finished_at=finished_at,
            success=resp.status_code == 200,
            error_message=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
            user_id=user_id,
        )
        if resp.status_code != 200:
            return []
        candles_block = payload.get("candles") or {}
        cols = candles_block.get("columns") or []
        rows = candles_block.get("data") or []
        idx = {name: i for i, name in enumerate(cols)}
        begin_i = idx.get("begin")
        open_i = idx.get("open")
        high_i = idx.get("high")
        low_i = idx.get("low")
        close_i = idx.get("close")
        volume_i = idx.get("volume")
        out: List[Dict[str, Any]] = []
        for r in rows:
            if begin_i is None or begin_i >= len(r):
                continue
            out.append(
                {
                    "candle_time": r[begin_i],
                    "open": r[open_i] if open_i is not None and open_i < len(r) else None,
                    "high": r[high_i] if high_i is not None and high_i < len(r) else None,
                    "low": r[low_i] if low_i is not None and low_i < len(r) else None,
                    "close": r[close_i] if close_i is not None and close_i < len(r) else None,
                    "volume": r[volume_i] if volume_i is not None and volume_i < len(r) else None,
                }
            )
        return out

    def _upsert_candles_cache(
        self,
        db: Session,
        *,
        ticker: str,
        interval_label: str,
        candles: List[Dict[str, Any]],
        market: str = "moex",
        source: str = "moex_iss",
    ) -> None:
        if not candles:
            return
        table = CandleCache.__table__
        now = datetime.now(timezone.utc)
        rows = [
            {
                "market": str(market or "moex").strip().lower(),
                "instrument_id": ticker,
                "ticker": ticker,
                "interval": interval_label,
                "candle_time": c.get("candle_time"),
                "open": c.get("open"),
                "high": c.get("high"),
                "low": c.get("low"),
                "close": c.get("close"),
                "volume": c.get("volume"),
                "source": source,
                "updated_at": now,
            }
            for c in candles
        ]
        # Один round-trip на чанк вместо построчного INSERT.
        chunk_size = 750
        for off in range(0, len(rows), chunk_size):
            batch = rows[off : off + chunk_size]
            ins = pg_insert(table).values(batch)
            ins = ins.on_conflict_do_update(
                index_elements=["market", "instrument_id", "interval", "candle_time"],
                set_={
                    "open": ins.excluded.open,
                    "high": ins.excluded.high,
                    "low": ins.excluded.low,
                    "close": ins.excluded.close,
                    "volume": ins.excluded.volume,
                    "source": ins.excluded.source,
                    "updated_at": ins.excluded.updated_at,
                },
            )
            db.execute(ins)

    #///EPIC Backtesting.ITEM CandleCache.TOPIC Incremental Fetch Strategy [1]
    #/// Гарантирует полноту candles_cache на диапазоне дат без лишних запросов:
    #/// вычисляет min/max покрытие по тикеру, догружает только разрывы,
    #/// при необходимости обновляет последний intraday-день и ведет статистику fetch/cache hits.
    async def _ensure_candles_cached_for_tickers(
        self,
        db: Session,
        *,
        board: str,
        tickers: List[str],
        interval_code: int,
        days_back: int,
        from_date: Optional[date] = None,
        till_date: Optional[date] = None,
        refresh_recent_intraday: bool = True,
        min_candles_per_ticker: int = 0,
        user_id: Optional[int] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        on_ticker_processed: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, int]:
        interval_label = self._interval_code_to_cache_label(interval_code)
        now_utc = datetime.now(timezone.utc)
        req_from_date = from_date or (now_utc - timedelta(days=max(1, int(days_back)))).date()
        req_till_date = till_date or now_utc.date()
        stats = {
            "total_tickers": len(tickers),
            "cache_full_hits": 0,
            "fetched_tickers": 0,
            "fetched_ranges": 0,
            "fetched_candles": 0,
        }

        def _to_utc(v: Any) -> Optional[datetime]:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v.astimezone(timezone.utc) if v.tzinfo else v.replace(tzinfo=timezone.utc)
            s = str(v)
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                try:
                    d = date.fromisoformat(s[:10])
                    return datetime.combine(d, time.min, tzinfo=timezone.utc)
                except Exception:
                    return None

        for ti, tk in enumerate(tickers):
            if cancel_check and cancel_check():
                break
            cached_count = int(
                db.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM candles_cache
                        WHERE market='moex'
                          AND instrument_id=:instrument_id
                          AND interval=:interval
                          AND candle_time >= :from_dt
                          AND candle_time < :till_dt
                        """
                    ),
                    {
                        "instrument_id": tk,
                        "interval": interval_label,
                        "from_dt": datetime.combine(req_from_date, time.min, tzinfo=timezone.utc),
                        "till_dt": datetime.combine(req_till_date + timedelta(days=1), time.min, tzinfo=timezone.utc),
                    },
                ).scalar()
                or 0
            )
            cache_range = db.execute(
                text(
                    f"""
                    SELECT
                        MIN(candle_time) AS min_ct,
                        MAX(candle_time) AS max_ct
                    FROM candles_cache
                    WHERE market='moex'
                      AND instrument_id=:instrument_id
                      AND interval=:interval
                      AND candle_time >= :from_dt
                      AND candle_time < :till_dt
                    """
                ),
                {
                    "instrument_id": tk,
                    "interval": interval_label,
                    "from_dt": datetime.combine(req_from_date, time.min, tzinfo=timezone.utc),
                    "till_dt": datetime.combine(req_till_date + timedelta(days=1), time.min, tzinfo=timezone.utc),
                },
            ).first()

            min_cached = _to_utc(cache_range[0]) if cache_range else None
            max_cached = _to_utc(cache_range[1]) if cache_range else None
            fetch_ranges: List[tuple[date, date]] = []

            if min_cached is None or max_cached is None:
                fetch_ranges.append((req_from_date, req_till_date))
            else:
                min_cached_day = min_cached.date()
                max_cached_day = max_cached.date()
                if min_cached_day > req_from_date:
                    fetch_ranges.append((req_from_date, min_cached_day - timedelta(days=1)))
                if max_cached_day < req_till_date:
                    fetch_ranges.append((max_cached_day + timedelta(days=1), req_till_date))
                elif refresh_recent_intraday and interval_label == "M5" and max_cached_day == req_till_date:
                    # Intraday candles can be incomplete for the current day.
                    last_touch = db.execute(
                        text(
                            f"""
                            SELECT MAX(updated_at)
                            FROM candles_cache
                            WHERE market='moex'
                              AND instrument_id=:instrument_id
                              AND interval=:interval
                              AND candle_time >= :today_from
                            """
                        ),
                        {
                            "instrument_id": tk,
                            "interval": interval_label,
                            "today_from": datetime.combine(req_till_date, time.min, tzinfo=timezone.utc),
                        },
                    ).scalar()
                    last_touch_utc = _to_utc(last_touch)
                    if not last_touch_utc or (now_utc - last_touch_utc) > timedelta(minutes=3):
                        fetch_ranges.append((req_till_date, req_till_date))
            if int(min_candles_per_ticker or 0) > 0 and cached_count < int(min_candles_per_ticker):
                fetch_ranges = [(req_from_date, req_till_date)]

            fetched_any = False
            for rng_from, rng_till in fetch_ranges:
                if rng_from > rng_till:
                    continue
                candles = await self._fetch_moex_candles(
                    db,
                    board=board,
                    ticker=tk,
                    interval_code=interval_code,
                    days_back=days_back,
                    from_date=rng_from.isoformat(),
                    till_date=rng_till.isoformat(),
                    user_id=user_id,
                )
                self._upsert_candles_cache(db, ticker=tk, interval_label=interval_label, candles=candles)
                fetched_any = True
                stats["fetched_ranges"] += 1
                stats["fetched_candles"] += len(candles)
            if fetched_any:
                stats["fetched_tickers"] += 1
            else:
                stats["cache_full_hits"] += 1
            if on_ticker_processed:
                try:
                    on_ticker_processed(ti + 1, len(tickers), tk)
                except Exception:
                    pass
        db.commit()
        return stats

    def _log_external_api_call(
        self,
        db: Session,
        *,
        endpoint: str,
        request_data: Dict[str, Any],
        response_status: Optional[int],
        response_data: Optional[Any],
        started_at: datetime,
        finished_at: datetime,
        success: bool,
        error_message: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> None:
        duration_ms = int(max(0.0, (finished_at - started_at).total_seconds() * 1000))
        try:
            db.execute(
                text(
                    f"""
                    INSERT INTO external_api_logs
                    (user_id, token_id, broker, context_type, context_ref, endpoint, request_data, response_status, response_data,
                     started_at, finished_at, duration_ms, success, error_message)
                    VALUES
                    (:user_id, NULL, 'moex', 'dms', 'pipeline', :endpoint, CAST(:request_data AS jsonb), :response_status, CAST(:response_data AS jsonb),
                     :started_at, :finished_at, :duration_ms, :success, :error_message)
                    """
                ),
                {
                    "user_id": user_id,
                    "endpoint": endpoint,
                    "request_data": json.dumps(request_data, ensure_ascii=False),
                    "response_status": response_status,
                    "response_data": json.dumps(response_data if response_data is not None else {}, ensure_ascii=False),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "success": 1 if success else 0,
                    "error_message": error_message,
                },
            )
            db.commit()
        except Exception:
            db.rollback()

    def _evaluate_pipeline_row(
        self,
        row: Dict[str, Any],
        filters: List[Dict[str, Any]],
        mode: str,
        *,
        optimize_order: bool = False,
        allowed_figis: Optional[set[str]] = None,
        allow_missing_spread: bool = False,
    ) -> Dict[str, Any]:
        ticker = str(row.get("ticker") or "").upper()
        open_price = self._safe_float(row.get("open_price"))
        prev_price = self._safe_float(row.get("prev_price"))
        last_price = self._safe_float(row.get("last_price"))
        high_price = self._safe_float(row.get("high_price"))
        low_price = self._safe_float(row.get("low_price"))
        value_today = self._safe_float(row.get("value_today")) or 0.0
        volume_lots = self._safe_float(row.get("volume_lots")) or 0.0
        trades_count = int(row.get("num_trades") or 0)
        issue_size = self._safe_float(row.get("issue_size"))
        min_step = self._safe_float(row.get("min_step"))
        sec_payload = row.get("securities_payload") or row.get("raw_payload") or {}
        if not isinstance(sec_payload, dict):
            sec_payload = {}
        if issue_size is None:
            issue_size = self._safe_float(sec_payload.get("ISSUE_SIZE"))
            if issue_size is None:
                issue_size = self._safe_float(sec_payload.get("ISSUESIZE"))
        if min_step is None:
            min_step = self._safe_float(sec_payload.get("MINSTEP"))
            if min_step is None:
                min_step = self._safe_float(sec_payload.get("MIN_STEP"))
        spread_raw = self._safe_float(row.get("spread"))
        bid = self._safe_float(row.get("bid"))
        ask = self._safe_float(row.get("ask"))
        security_status = str(row.get("security_status") or "")
        trading_status = str(row.get("trading_status") or "")
        atr_percent = self._safe_float(row.get("atr_percent"))

        gap_percent = None
        if open_price is not None and prev_price is not None and abs(prev_price) > 1e-9:
            gap_percent = ((open_price - prev_price) / prev_price) * 100.0
        capitalization = issue_size
        spread_percent = None
        if spread_raw is not None and ask is not None and ask > 0:
            spread_percent = (spread_raw / ask) * 100.0
        elif bid is not None and ask is not None and ask > 0:
            spread_percent = ((ask - bid) / ask) * 100.0

        if allowed_figis and ticker not in allowed_figis:
            return {
                "accepted": False,
                "reason": "Не в списке разрешённых инструментов (universe)",
                "gap_percent": gap_percent,
                "atr_percent": atr_percent,
                "spread_percent": spread_percent,
            }

        checks: List[bool] = []
        reasons: List[str] = []
        active_filters = [f for f in filters if isinstance(f, dict) and f.get("enabled", True) is not False]
        if optimize_order:
            active_filters = sorted(active_filters, key=lambda f: self.FILTER_COST_ORDER.get(str(f.get("type") or "").lower(), 50))

        for f in active_filters:
            if not isinstance(f, dict):
                continue
            t = str(f.get("type") or "").lower()
            if t == "volume":
                limit = float(f.get("min") or 0)
                hist_avg = self._safe_float(row.get("historical_avg_volume_rub"))
                vol_value = hist_avg if hist_avg is not None else value_today
                ok = vol_value >= limit
                checks.append(ok)
                if not ok:
                    reasons.append(f"VALTODAY {vol_value:.0f} < {limit:.0f}")
            elif t in ("min_avg_volume", "volume_avg"):
                limit = float(f.get("min") or 0)
                hist_avg = self._safe_float(row.get("historical_avg_volume_rub"))
                if hist_avg is None:
                    ok = False
                    reasons.append("historical_avg_volume unavailable")
                else:
                    ok = hist_avg >= limit
                    if not ok:
                        reasons.append(f"AVG_VOL {hist_avg:.0f} < {limit:.0f}")
                checks.append(ok)
            elif t == "gap":
                max_gap = float(f.get("max_percent") or 0)
                direction = str(f.get("direction") or "BOTH").upper()
                if gap_percent is None or open_price is None or prev_price is None:
                    ok = False
                elif direction == "UP_ONLY":
                    ok = gap_percent >= 0 and gap_percent <= max_gap
                elif direction == "DOWN_ONLY":
                    ok = gap_percent <= 0 and abs(gap_percent) <= max_gap
                else:
                    ok = abs(gap_percent) <= max_gap
                checks.append(ok)
                if not ok:
                    reasons.append(f"Гэп {(gap_percent if gap_percent is not None else 0):.2f}% не прошел direction={direction} max={max_gap:.2f}%")
            elif t == "excluded_tickers" or t == "exclude_tickers":
                values = {str(x).upper() for x in (f.get("list") or []) if x}
                ok = ticker not in values
                checks.append(ok)
                if not ok:
                    reasons.append("Исключен фильтром excluded_tickers")
            elif t == "only_tickers":
                values = {str(x).upper() for x in (f.get("list") or []) if x}
                ok = True if not values else ticker in values
                checks.append(ok)
                if not ok:
                    reasons.append("Нет в only_tickers")
            elif t == "allowed_tickers":
                values = {str(x).upper() for x in (f.get("list") or []) if x}
                ok = True if not values else ticker in values
                checks.append(ok)
                if not ok:
                    reasons.append("Нет в allowed_tickers")
            elif t == "security_status":
                expected = str(f.get("eq") or "A").upper()
                ok = security_status.upper() == expected
                checks.append(ok)
                if not ok:
                    reasons.append(f"STATUS {security_status} != {expected}")
            elif t == "trading_status":
                expected = str(f.get("eq") or "T").upper()
                ok = trading_status.upper() == expected
                checks.append(ok)
                if not ok:
                    reasons.append(f"TRADINGSTATUS {trading_status} != {expected}")
            elif t == "last_price":
                ok = last_price is not None and last_price > 0
                checks.append(ok)
                if not ok:
                    reasons.append("LAST отсутствует или <= 0")
            elif t == "num_trades":
                min_trades = int(f.get("min") or 0)
                ok = trades_count >= min_trades
                checks.append(ok)
                if not ok:
                    reasons.append(f"NUMTRADES {trades_count} < {min_trades}")
            elif t == "volume_lots":
                min_lots = float(f.get("min") or 0.0)
                ok = volume_lots >= min_lots
                checks.append(ok)
                if not ok:
                    reasons.append(f"VOLTODAY {volume_lots:.0f} < {min_lots:.0f}")
            elif t == "spread":
                max_spread = float(f.get("max_percent") or 0.0)
                if spread_percent is None and allow_missing_spread:
                    ok = True
                else:
                    ok = spread_percent is not None and spread_percent <= max_spread
                checks.append(ok)
                if not ok:
                    reasons.append(f"SPREAD {spread_percent if spread_percent is not None else 0:.3f}% > {max_spread:.3f}%")
            elif t == "capitalization":
                min_cap = float(f.get("min") or 0.0)
                ok = capitalization is not None and capitalization >= min_cap
                checks.append(ok)
                if not ok:
                    reasons.append(f"CAP {capitalization if capitalization is not None else 0:.0f} < {min_cap:.0f}")
            elif t == "atr":
                min_atr = float(f.get("min_percent") or 0.0)
                if atr_percent is None:
                    ok = False
                    reasons.append("ATR% unavailable (no candle data or API error)")
                else:
                    ok = atr_percent >= min_atr
                    if not ok:
                        reasons.append(f"ATR% {atr_percent:.2f} < {min_atr:.2f}")
                checks.append(ok)
            elif t == "min_step_ratio":
                max_steps = float(f.get("max_steps") or 5)
                if min_step is None or min_step <= 0 or last_price is None or last_price <= 0:
                    ok = False
                else:
                    commission_per_lot = last_price * 0.0005
                    min_steps_to_cover = commission_per_lot / min_step
                    ok = min_steps_to_cover <= max_steps
                checks.append(ok)
                if not ok:
                    reasons.append("MINSTEP ratio too high for commission cover")
            elif t == "turnover":
                # Оборачиваемость: VALUE / (ISSUESIZE * PREVPRICE) * 100% (VALUE — оборот в руб. из снапшота).
                # PREVPRICE — prev_price из истории (CLOSE / (1 + TRENDCLSPR/100)) или prev_legal_close_price.
                min_turnover = float(f.get("min_percent") or 0.0)
                prev_for_cap = prev_price
                if prev_for_cap is None or prev_for_cap <= 0:
                    prev_for_cap = self._safe_float(row.get("prev_legal_close_price"))
                if (prev_for_cap is None or prev_for_cap <= 0) and isinstance(sec_payload, dict):
                    prev_for_cap = self._safe_float(sec_payload.get("PREVLEGALCLOSEPRICE"))
                hist_avg = self._safe_float(row.get("historical_avg_volume_rub"))
                val_rub = hist_avg if hist_avg is not None else self._safe_float(row.get("value_today"))
                if val_rub is None:
                    val_rub = 0.0
                if (
                        issue_size is None
                        or issue_size <= 0
                        or prev_for_cap is None
                        or prev_for_cap <= 0
                        or val_rub <= 0
                ):
                    checks.append(True)
                    continue
                mcap = issue_size * prev_for_cap
                if mcap <= 0:
                    checks.append(True)
                    continue
                turnover_pct = (val_rub / mcap) * 100.0
                ok = turnover_pct >= min_turnover
                checks.append(ok)
                if not ok:
                    reasons.append(f"TURNOVER {turnover_pct:.3f}% < {min_turnover:.3f}%")
            elif t == "gap_retention":
                min_retention = float(f.get("min_ratio") or 0.0)
                if open_price and prev_price and prev_price > 0 and last_price:
                    gap_val = abs(open_price - prev_price)
                    movement = abs(last_price - open_price)
                    if gap_val > 1e-9:
                        retention = movement / gap_val
                        ok = retention >= min_retention
                    else:
                        retention = 0.0
                        ok = False
                else:
                    retention = None
                    ok = False
                checks.append(ok)
                if not ok:
                    retention_label = f"{retention:.2f}" if retention is not None else "N/A"
                    reasons.append(f"GAP_RETENTION {retention_label} < {min_retention:.2f}")
            elif t == "price_vs_open":
                min_ratio = float(f.get("min_percent") or 0.998)
                if last_price and open_price and open_price > 0:
                    ratio = last_price / open_price
                    ok = ratio >= min_ratio
                else:
                    ratio = None
                    ok = False
                checks.append(ok)
                if not ok:
                    ratio_label = f"{ratio:.3f}" if ratio is not None else "N/A"
                    reasons.append(f"PRICE_VS_OPEN {ratio_label} < {min_ratio:.3f}")
            elif t == "opening_range":
                min_range = float(f.get("min_percent") or 0.0)
                if high_price and low_price and prev_price and prev_price > 0:
                    range_pct = ((high_price - low_price) / prev_price) * 100.0
                    ok = range_pct >= min_range
                else:
                    range_pct = None
                    ok = False
                checks.append(ok)
                if not ok:
                    range_label = f"{range_pct:.2f}" if range_pct is not None else "N/A"
                    reasons.append(f"OPENING_RANGE {range_label}% < {min_range:.2f}%")

        if not checks:
            return {"accepted": True, "reason": None, "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}
        if str(mode).upper() == "ANY":
            accepted = any(checks)
            return {"accepted": accepted, "reason": None if accepted else "; ".join(reasons[:2]), "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}
        accepted = all(checks)
        return {"accepted": accepted, "reason": None if accepted else "; ".join(reasons[:2]), "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}

    @staticmethod
    def _resolve_allowed_tickers_from_config(config: Dict[str, Any]) -> set[str]:
        """
        Whitelist-тикеры для pre-filter в pipeline.
        Только universe_mode=fixed; для dms_pipeline/tqbr_scan — пустой набор (без whitelist).
        """
        wl = universe_whitelist_tickers(config)
        if wl is None:
            return set()
        return wl

    async def _load_atr_percent_map(
        self,
        db: Session,
        board: str,
        rows: List[Dict[str, Any]],
        filters: List[Dict[str, Any]],
        as_of_date: Optional[date] = None,
        fetch_missing_candles: bool = True,
        user_id: Optional[int] = None,
    ) -> tuple[Dict[str, float], Dict[str, int]]:
        atr_filter = next((f for f in filters if str((f or {}).get("type") or "").lower() == "atr" and (f or {}).get("enabled", True) is not False), None)
        if not atr_filter:
            return {}, {
                "total_tickers": 0,
                "cache_full_hits": 0,
                "fetched_tickers": 0,
                "fetched_ranges": 0,
                "fetched_candles": 0,
            }
        period = int(atr_filter.get("period") or 14)
        lookback_days = max(20, min(120, period + 20))
        out: Dict[str, float] = {}
        candidate_rows = [r for r in rows if str(r.get("ticker") or "").upper() and (self._safe_float(r.get("last_price")) or 0) > 0]
        tickers = [str(r.get("ticker")).upper() for r in candidate_rows]
        atr_till_date = (as_of_date - timedelta(days=1)) if as_of_date else None
        atr_from_date = (atr_till_date - timedelta(days=lookback_days)) if atr_till_date else None
        if fetch_missing_candles:
            cache_stats = await self._ensure_candles_cached_for_tickers(
                db,
                board=board,
                tickers=tickers,
                interval_code=24,
                days_back=lookback_days,
                from_date=atr_from_date,
                till_date=atr_till_date,
                refresh_recent_intraday=False,
                user_id=user_id,
            )
        else:
            cache_stats = {
                "total_tickers": len(tickers),
                "cache_full_hits": 0,
                "fetched_tickers": 0,
                "fetched_ranges": 0,
                "fetched_candles": 0,
            }
        price_by_ticker = {str(r.get("ticker") or "").upper(): self._safe_float(r.get("last_price")) for r in candidate_rows}
        if not tickers:
            return out, cache_stats
        from_dt = datetime.combine(atr_from_date, time.min, tzinfo=timezone.utc) if atr_from_date else None
        to_dt = datetime.combine((atr_till_date + timedelta(days=1)), time.min, tzinfo=timezone.utc) if atr_till_date else None
        d1_stmt = text(
            f"""
            SELECT instrument_id, high, low, close
            FROM candles_cache
            WHERE market = 'moex'
              AND interval = 'D1'
              AND instrument_id IN :tickers
              AND (:from_dt IS NULL OR candle_time >= :from_dt)
              AND (:to_dt IS NULL OR candle_time < :to_dt)
            ORDER BY ticker ASC, candle_time ASC
            """
        ).bindparams(bindparam("tickers", expanding=True))
        rows_db_all = db.execute(
            d1_stmt,
            {"tickers": list(tickers), "from_dt": from_dt, "to_dt": to_dt},
        ).fetchall()
        by_ticker: Dict[str, List[Any]] = {}
        for r in rows_db_all:
            tk = str(r[0]).upper()
            by_ticker.setdefault(tk, []).append((r[1], r[2], r[3]))
        for ticker in tickers:
            rows_db = by_ticker.get(ticker, [])
            last_price = price_by_ticker.get(ticker)
            if not last_price or last_price <= 0 or len(rows_db) < 2:
                continue
            trs: List[float] = []
            prev_close: Optional[float] = None
            for h, l, c in rows_db:
                high = self._safe_float(h)
                low = self._safe_float(l)
                close = self._safe_float(c)
                if high is None or low is None:
                    prev_close = close
                    continue
                tr = (high - low) if prev_close is None else max(high - low, abs(high - prev_close), abs(low - prev_close))
                trs.append(float(tr))
                prev_close = close
            if not trs:
                continue
            atr = sum(trs[-period:]) / float(min(len(trs), period))
            out[ticker] = (atr / last_price) * 100.0
        return out, cache_stats

    @staticmethod
    def _is_probably_market_closed(now: datetime) -> bool:
        # Conservative heuristic for MOEX stock board: weekends are always closed.
        return now.weekday() >= 5

    @staticmethod
    def _inside_schedule_window(now_utc: datetime, schedule: Optional[Dict[str, Any]]) -> bool:
        if not schedule:
            return True
        weekdays = int(schedule.get("weekdays") or 0)
        if weekdays > 0 and ((weekdays & (1 << now_utc.weekday())) == 0):
            return False

        def _to_t(v: Any) -> Optional[time]:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v.timetz()
            if isinstance(v, time):
                return v
            s = str(v)
            m = s[11:19] if "T" in s else s[:8]
            try:
                return time.fromisoformat(m)
            except Exception:
                return None

        start_t = _to_t(schedule.get("start_time"))
        end_t = _to_t(schedule.get("end_time"))
        if not start_t or not end_t:
            return True
        now_t = now_utc.timetz().replace(tzinfo=None)
        st = start_t.replace(tzinfo=None)
        et = end_t.replace(tzinfo=None)
        return (st <= now_t <= et) if st <= et else (now_t >= st or now_t <= et)

    async def _fetch_moex_board_snapshot(self, db: Session, board: str, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json"
        params = {"iss.meta": "off", "iss.only": "securities,marketdata", "securities.start": 0, "marketdata.start": 0}
        rows: List[Dict[str, Any]] = []
        start = 0
        seen_page_signatures: set[str] = set()
        max_pages = 200

        while True:
            params["securities.start"] = start
            params["marketdata.start"] = start
            started_at = datetime.now(timezone.utc)
            async with moex_http_acquire():
                async with httpx.AsyncClient(timeout=20, verify=False) as client:
                    resp = await client.get(url, params=params)
            finished_at = datetime.now(timezone.utc)
            payload: Dict[str, Any] = {}
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            self._log_external_api_call(
                db,
                endpoint=url,
                request_data={"params": dict(params)},
                response_status=resp.status_code,
                response_data=payload,
                started_at=started_at,
                finished_at=finished_at,
                success=resp.status_code == 200,
                error_message=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                user_id=user_id,
            )
            if resp.status_code != 200:
                db.commit()
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MOEX API error {resp.status_code}")

            sec = payload.get("securities", {})
            md = payload.get("marketdata", {})
            sec_cols = sec.get("columns", []) or []
            md_cols = md.get("columns", []) or []
            sec_data = sec.get("data", []) or []
            md_data = md.get("data", []) or []

            if not sec_data:
                break

            page_signature = f"{len(sec_data)}:{sec_data[0][0] if sec_data and sec_data[0] else ''}:{sec_data[-1][0] if sec_data and sec_data[-1] else ''}"
            if page_signature in seen_page_signatures:
                break
            seen_page_signatures.add(page_signature)

            has_cursor = isinstance(payload, dict) and (
                    ("securities.cursor" in payload) or ("marketdata.cursor" in payload)
            )

            sec_idx = {name: i for i, name in enumerate(sec_cols)}
            md_idx = {name: i for i, name in enumerate(md_cols)}

            def secv(sec_row, name: str):
                i = sec_idx.get(name)
                return sec_row[i] if i is not None and i < len(sec_row) else None

            md_by_secid: Dict[str, Any] = {}
            for row in md_data:
                secid_i = md_idx.get("SECID")
                if secid_i is None or secid_i >= len(row):
                    continue
                md_by_secid[str(row[secid_i])] = row

            for row in sec_data:
                secid_i = sec_idx.get("SECID")
                if secid_i is None or secid_i >= len(row):
                    continue
                ticker = str(row[secid_i])
                md_row = md_by_secid.get(ticker)
                if not md_row:
                    continue

                def mdv(name: str):
                    i = md_idx.get(name)
                    return md_row[i] if i is not None and i < len(md_row) else None

                # === ИСПРАВЛЕНИЕ: правильный prev_price ===
                close_price = mdv("CLOSEPRICE")
                prev_price = secv(row, "PREVPRICE")  # fallback

                # Явная логика: CLOSEPRICE приоритетнее, но если он None — берем PREVPRICE
                if close_price is not None:
                    prev_price = close_price

                rows.append(
                    {
                        "ticker": ticker,
                        "board_id": secv(row, "BOARDID"),
                        "short_name": secv(row, "SHORTNAME"),
                        "sec_name": secv(row, "SECNAME"),
                        "isin": secv(row, "ISIN"),
                        "sec_type": secv(row, "SECTYPE"),
                        "list_level": secv(row, "LISTLEVEL"),
                        "face_value": secv(row, "FACEVALUE"),
                        "board_name": secv(row, "BOARDNAME"),
                        "decimals": secv(row, "DECIMALS"),
                        "remarks": secv(row, "REMARKS"),
                        "market_code": secv(row, "MARKETCODE"),
                        "instr_id": secv(row, "INSTRID"),
                        "sector_id": secv(row, "SECTORID"),
                        "face_unit": secv(row, "FACEUNIT"),
                        "prev_date": secv(row, "PREVDATE"),
                        "lat_name": secv(row, "LATNAME"),
                        "reg_number": secv(row, "REGNUMBER"),
                        "currency_id": secv(row, "CURRENCYID"),
                        "settle_date": secv(row, "SETTLEDATE"),
                        "lot_size": secv(row, "LOTSIZE"),
                        "last_price": mdv("LAST"),
                        "open_price": mdv("OPEN"),
                        "low_price": mdv("LOW"),
                        "high_price": mdv("HIGH"),
                        # === ИСПРАВЛЕНИЕ ===
                        "prev_price": prev_price,
                        "prev_wa_price": secv(row, "PREVWAPRICE"),
                        "prev_legal_close_price": secv(row, "PREVLEGALCLOSEPRICE"),
                        # Убираем close_price, оставляем только prev_price
                        "value": mdv("VALUE"),
                        "value_usd": mdv("VALUE_USD"),
                        "wa_price": mdv("WAPRICE"),
                        "last_change": mdv("LASTCHANGE"),
                        "last_change_prcnt": mdv("LASTCHANGEPRCNT"),
                        "market_price_today": mdv("MARKETPRICETODAY"),
                        "market_price": mdv("MARKETPRICE"),
                        "last_to_prev_price": mdv("LASTTOPREVPRICE"),
                        "value_today": mdv("VALTODAY"),
                        "val_today_rur": mdv("VALTODAY_RUR"),
                        "volume_lots": mdv("VOLTODAY"),
                        "security_status": secv(row, "STATUS"),
                        "trading_status": mdv("TRADINGSTATUS"),
                        "num_trades": mdv("NUMTRADES"),
                        "min_step": secv(row, "MINSTEP"),
                        "issue_size": secv(row, "ISSUESIZE"),
                        "bid": mdv("BID"),
                        "ask": mdv("OFFER"),
                        "spread": mdv("SPREAD"),
                        "market_update_time": mdv("UPDATETIME"),
                        "trading_session": mdv("TRADINGSESSION"),
                        "seq_num": mdv("SEQNUM"),
                        "sys_time": mdv("SYSTIME"),
                        "issue_capitalization": mdv("ISSUECAPITALIZATION"),
                        "trend_issue_capitalization": mdv("TRENDISSUECAPITALIZATION"),
                        "securities_payload": {k: secv(row, k) for k in sec_cols},
                        "marketdata_payload": {k: mdv(k) for k in md_cols},
                    }
                )

            if not has_cursor:
                break
            if len(sec_data) < 100:
                break
            start += len(sec_data)
            if len(seen_page_signatures) >= max_pages:
                break

        # === ВОТ ЗДЕСЬ ПРАВИЛЬНОЕ МЕСТО ДЛЯ COMMIT И RETURN ===
        db.commit()
        return rows

    async def create_snapshot(
        self,
        db: Session,
        board: str = "TQBR",
        ttl_minutes: int = 5,
        is_manual: bool = True,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        insert_snapshot_q = f"""
            INSERT INTO market_snapshot
            (snapshot_time, board, status, is_manual, ttl_minutes, created_at)
            VALUES (:snapshot_time, :board, 'PROCESSING', :is_manual, :ttl_minutes, :created_at)
            RETURNING id
        """
        snapshot_row = db.execute(
            text(insert_snapshot_q),
            {"snapshot_time": now, "board": board, "is_manual": bool(is_manual), "ttl_minutes": int(ttl_minutes), "created_at": now},
        ).first()
        snapshot_id = int(snapshot_row[0])
        db.commit()
        try:
            raw_rows = await self._fetch_moex_board_snapshot(db=db, board=board, user_id=user_id)
            if not raw_rows and self._is_probably_market_closed(now):
                db.execute(
                    text(
                        f"""
                        UPDATE market_snapshot
                        SET status='MARKET_CLOSED',
                            error_message=:msg
                        WHERE id=:id
                        """
                    ),
                    {"id": snapshot_id, "msg": "Биржа закрыта (выходной день)"},
                )
                db.commit()
                return {"snapshot_id": snapshot_id, "status": "MARKET_CLOSED", "securities_count": 0, "message": "Биржа закрыта"}
            insert_data_q = f"""
                INSERT INTO market_snapshot_data
                (snapshot_id, ticker, board_id, short_name, sec_name, isin, sec_type, list_level, face_value, board_name, decimals, remarks, market_code, instr_id, sector_id, face_unit, prev_date, lat_name, reg_number, currency_id, settle_date, lot_size,
                 last_price, open_price, low_price, high_price, prev_price, prev_wa_price, prev_legal_close_price, close_price, value, value_usd, wa_price, last_change, last_change_prcnt, market_price_today, market_price, last_to_prev_price,
                 value_today, val_today_rur, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, bid, ask, spread, market_update_time, trading_session, seq_num, sys_time, issue_capitalization, trend_issue_capitalization,
                 securities_payload, marketdata_payload)
                VALUES
                (:snapshot_id, :ticker, :board_id, :short_name, :sec_name, :isin, :sec_type, :list_level, :face_value, :board_name, :decimals, :remarks, :market_code, :instr_id, :sector_id, :face_unit, :prev_date, :lat_name, :reg_number, :currency_id, :settle_date, :lot_size,
                 :last_price, :open_price, :low_price, :high_price, :prev_price, :prev_wa_price, :prev_legal_close_price, :close_price, :value, :value_usd, :wa_price, :last_change, :last_change_prcnt, :market_price_today, :market_price, :last_to_prev_price,
                 :value_today, :val_today_rur, :volume_lots, :security_status, :trading_status, :num_trades, :min_step, :issue_size, :bid, :ask, :spread, :market_update_time, :trading_session, :seq_num, :sys_time, :issue_capitalization, :trend_issue_capitalization,
                 CAST(:securities_payload AS jsonb), CAST(:marketdata_payload AS jsonb))
                ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
                    board_id = EXCLUDED.board_id,
                    short_name = EXCLUDED.short_name,
                    sec_name = EXCLUDED.sec_name,
                    isin = EXCLUDED.isin,
                    sec_type = EXCLUDED.sec_type,
                    list_level = EXCLUDED.list_level,
                    face_value = EXCLUDED.face_value,
                    board_name = EXCLUDED.board_name,
                    decimals = EXCLUDED.decimals,
                    remarks = EXCLUDED.remarks,
                    market_code = EXCLUDED.market_code,
                    instr_id = EXCLUDED.instr_id,
                    sector_id = EXCLUDED.sector_id,
                    face_unit = EXCLUDED.face_unit,
                    prev_date = EXCLUDED.prev_date,
                    lat_name = EXCLUDED.lat_name,
                    reg_number = EXCLUDED.reg_number,
                    currency_id = EXCLUDED.currency_id,
                    settle_date = EXCLUDED.settle_date,
                    lot_size = EXCLUDED.lot_size,
                    last_price = EXCLUDED.last_price,
                    open_price = EXCLUDED.open_price,
                    low_price = EXCLUDED.low_price,
                    high_price = EXCLUDED.high_price,
                    prev_price = EXCLUDED.prev_price,
                    prev_wa_price = EXCLUDED.prev_wa_price,
                    prev_legal_close_price = EXCLUDED.prev_legal_close_price,
                    close_price = EXCLUDED.close_price,
                    value = EXCLUDED.value,
                    value_usd = EXCLUDED.value_usd,
                    wa_price = EXCLUDED.wa_price,
                    last_change = EXCLUDED.last_change,
                    last_change_prcnt = EXCLUDED.last_change_prcnt,
                    market_price_today = EXCLUDED.market_price_today,
                    market_price = EXCLUDED.market_price,
                    last_to_prev_price = EXCLUDED.last_to_prev_price,
                    value_today = EXCLUDED.value_today,
                    val_today_rur = EXCLUDED.val_today_rur,
                    volume_lots = EXCLUDED.volume_lots,
                    security_status = EXCLUDED.security_status,
                    trading_status = EXCLUDED.trading_status,
                    num_trades = EXCLUDED.num_trades,
                    min_step = EXCLUDED.min_step,
                    issue_size = EXCLUDED.issue_size,
                    bid = EXCLUDED.bid,
                    ask = EXCLUDED.ask,
                    spread = EXCLUDED.spread,
                    market_update_time = EXCLUDED.market_update_time,
                    trading_session = EXCLUDED.trading_session,
                    seq_num = EXCLUDED.seq_num,
                    sys_time = EXCLUDED.sys_time,
                    issue_capitalization = EXCLUDED.issue_capitalization,
                    trend_issue_capitalization = EXCLUDED.trend_issue_capitalization,
                    securities_payload = EXCLUDED.securities_payload,
                    marketdata_payload = EXCLUDED.marketdata_payload
            """
            for r in raw_rows:
                bid = float(r["bid"]) if r.get("bid") is not None else None
                ask = float(r["ask"]) if r.get("ask") is not None else None
                spread = r.get("spread")
                if spread is None and bid is not None and ask is not None:
                    spread = ask - bid
                db.execute(
                    text(insert_data_q),
                    {
                        "snapshot_id": snapshot_id,
                        "ticker": r["ticker"],
                        "board_id": r.get("board_id"),
                        "short_name": r.get("short_name"),
                        "sec_name": r.get("sec_name"),
                        "isin": r.get("isin"),
                        "sec_type": r.get("sec_type"),
                        "list_level": r.get("list_level"),
                        "face_value": r.get("face_value"),
                        "board_name": r.get("board_name"),
                        "decimals": r.get("decimals"),
                        "remarks": r.get("remarks"),
                        "market_code": r.get("market_code"),
                        "instr_id": r.get("instr_id"),
                        "sector_id": r.get("sector_id"),
                        "face_unit": r.get("face_unit"),
                        "prev_date": r.get("prev_date"),
                        "lat_name": r.get("lat_name"),
                        "reg_number": r.get("reg_number"),
                        "currency_id": r.get("currency_id"),
                        "settle_date": r.get("settle_date"),
                        "lot_size": r.get("lot_size"),
                        "last_price": r.get("last_price"),
                        "open_price": r.get("open_price"),
                        "low_price": r.get("low_price"),
                        "high_price": r.get("high_price"),
                        "prev_price": r.get("prev_price"),
                        "prev_wa_price": r.get("prev_wa_price"),
                        "prev_legal_close_price": r.get("prev_legal_close_price"),
                        "close_price": r.get("close_price"),
                        "value": r.get("value"),
                        "value_usd": r.get("value_usd"),
                        "wa_price": r.get("wa_price"),
                        "last_change": r.get("last_change"),
                        "last_change_prcnt": r.get("last_change_prcnt"),
                        "market_price_today": r.get("market_price_today"),
                        "market_price": r.get("market_price"),
                        "last_to_prev_price": r.get("last_to_prev_price"),
                        "value_today": r.get("value_today"),
                        "val_today_rur": r.get("val_today_rur"),
                        "volume_lots": r.get("volume_lots"),
                        "security_status": r.get("security_status"),
                        "trading_status": r.get("trading_status"),
                        "num_trades": r.get("num_trades"),
                        "min_step": r.get("min_step"),
                        "issue_size": r.get("issue_size"),
                        "bid": r.get("bid"),
                        "ask": r.get("ask"),
                        "spread": spread,
                        "market_update_time": r.get("market_update_time"),
                        "trading_session": r.get("trading_session"),
                        "seq_num": r.get("seq_num"),
                        "sys_time": r.get("sys_time"),
                        "issue_capitalization": r.get("issue_capitalization"),
                        "trend_issue_capitalization": r.get("trend_issue_capitalization"),
                        "securities_payload": json.dumps(r.get("securities_payload") or {}, ensure_ascii=False),
                        "marketdata_payload": json.dumps(r.get("marketdata_payload") or {}, ensure_ascii=False),
                    },
                )
            db.execute(
                text(f"UPDATE market_snapshot SET status='SUCCESS' WHERE id=:id"),
                {"id": snapshot_id},
            )
            db.commit()
            return {"snapshot_id": snapshot_id, "status": "SUCCESS", "securities_count": len(raw_rows), "message": None}
        except Exception as e:
            db.execute(
                text(f"UPDATE market_snapshot SET status='ERROR', error_message=:msg WHERE id=:id"),
                {"id": snapshot_id, "msg": str(e)},
            )
            db.commit()
            return {"snapshot_id": snapshot_id, "status": "ERROR", "securities_count": 0, "message": str(e)}

    async def initialize_trading_day(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        robot_id: int,
        board: str = "TQBR",
        force_refresh_snapshot: bool = False,
        force_recompute_universe: bool = False,
    ) -> Dict[str, Any]:
        if user_id is None:
            robot = db.execute(
                text(
                    f"""
                    SELECT id
                    FROM robots
                    WHERE id=:robot_id AND status != 0
                    LIMIT 1
                    """
                ),
                {"robot_id": robot_id},
            ).first()
        else:
            robot = db.execute(
                text(
                    f"""
                    SELECT id
                    FROM robots
                    WHERE id=:robot_id AND user_id=:user_id AND status != 0
                    LIMIT 1
                    """
                ),
                {"robot_id": robot_id, "user_id": user_id},
            ).first()
        if not robot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Робот не найден")

        today = datetime.now(timezone.utc).date()
        existing = db.execute(
            text(
                f"""
                SELECT snapshot_id
                FROM daily_universe
                WHERE robot_id=:robot_id
                  AND trade_date=:trade_date
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"robot_id": robot_id, "trade_date": today},
        ).first()

        if existing and not force_refresh_snapshot and not force_recompute_universe:
            return {
                "robot_id": robot_id,
                "board": board,
                "trade_date": today,
                "snapshot_id": int(existing[0]) if existing[0] is not None else 0,
                "initialized": False,
                "recomputed": False,
                "analyzer_written_rows": 0,
                "message": "Уже инициализировано за сегодня",
            }

        if force_recompute_universe:
            db.execute(
                text(
                    f"""
                    DELETE FROM daily_universe
                    WHERE robot_id = :robot_id AND trade_date = :trade_date
                    """
                ),
                {"robot_id": robot_id, "trade_date": today},
            )
            db.commit()

        snap = db.execute(
            text(
                f"""
                SELECT id, snapshot_time
                FROM market_snapshot
                WHERE board=:board AND status='SUCCESS'
                ORDER BY snapshot_time DESC
                LIMIT 1
                """
            ),
            {"board": board},
        ).first()
        snapshot_id: Optional[int] = None
        if not force_refresh_snapshot and not force_recompute_universe and snap:
            snap_id = int(snap[0])
            snap_time = snap[1]
            if snap_time and snap_time.astimezone(timezone.utc).date() == today:
                snapshot_id = snap_id

        if snapshot_id is None:
            created = await self.create_snapshot(
                db=db,
                board=board,
                ttl_minutes=0,
                is_manual=True,
                user_id=user_id,
            )
            if created.get("status") != "SUCCESS":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=created.get("message") or "Не удалось создать snapshot",
                )
            snapshot_id = int(created["snapshot_id"])

        written = await self._apply_analyzer(
            db,
            robot_id=robot_id,
            snapshot_id=snapshot_id,
            force_recompute=force_recompute_universe,
        )
        return {
            "robot_id": robot_id,
            "board": board,
            "trade_date": today,
            "snapshot_id": int(snapshot_id),
            "initialized": written > 0,
            "recomputed": bool(force_recompute_universe and written > 0),
            "analyzer_written_rows": written,
            "message": None if written > 0 else "Уже инициализировано за сегодня",
        }

    async def cleanup_old_snapshots(self, db: Session, older_than_days: int = 3) -> Dict[str, int]:
        threshold = datetime.now(timezone.utc) - timedelta(days=max(1, int(older_than_days)))
        old_ids = db.execute(
            text(
                f"""
                SELECT id
                FROM market_snapshot
                WHERE snapshot_time < :threshold
                ORDER BY snapshot_time ASC
                LIMIT 10000
                """
            ),
            {"threshold": threshold},
        ).fetchall()
        if not old_ids:
            return {"moved_snapshots": 0, "moved_rows": 0, "deleted_snapshots": 0}
        ids = [int(r[0]) for r in old_ids]
        db.execute(
            text(
                f"""
                INSERT INTO market_snapshot_history
                SELECT * FROM market_snapshot
                WHERE id = ANY(:ids)
                ON CONFLICT DO NOTHING
                """
            ),
            {"ids": ids},
        )
        moved_rows = db.execute(
            text(
                f"""
                INSERT INTO market_snapshot_data_history
                SELECT * FROM market_snapshot_data
                WHERE snapshot_id = ANY(:ids)
                ON CONFLICT DO NOTHING
                RETURNING id
                """
            ),
            {"ids": ids},
        ).fetchall()
        db.execute(
            text(f"DELETE FROM market_snapshot_data WHERE snapshot_id = ANY(:ids)"),
            {"ids": ids},
        )
        deleted_snapshots = db.execute(
            text(f"DELETE FROM market_snapshot WHERE id = ANY(:ids) RETURNING id"),
            {"ids": ids},
        ).fetchall()
        db.commit()
        return {
            "moved_snapshots": len(ids),
            "moved_rows": len(moved_rows),
            "deleted_snapshots": len(deleted_snapshots),
        }

    async def _apply_analyzer(
        self,
        db: Session,
        robot_id: int,
        snapshot_id: int,
        *,
        force_recompute: bool = False,
    ) -> int:
        today = datetime.now(timezone.utc).date()
        if not force_recompute:
            already_initialized = db.execute(
                text(
                    f"""
                    SELECT 1
                    FROM daily_universe
                    WHERE robot_id = :robot_id
                      AND trade_date = :trade_date
                    LIMIT 1
                    """
                ),
                {"robot_id": robot_id, "trade_date": today},
            ).first()
            if already_initialized:
                return 0

        robot_row = db.execute(
            text(f"SELECT config FROM robots WHERE id=:robot_id"),
            {"robot_id": robot_id},
        ).first()
        config = dict(robot_row[0] or {}) if robot_row else {}
        schedule_row = db.execute(
            text(
                f"""
                SELECT start_time, end_time, weekdays
                FROM robot_schedules
                WHERE robot_id=:robot_id AND COALESCE(is_active,1)=1
                ORDER BY priority DESC, id DESC
                LIMIT 1
                """
            ),
            {"robot_id": robot_id},
        ).first()
        schedule = {"start_time": schedule_row[0], "end_time": schedule_row[1], "weekdays": schedule_row[2]} if schedule_row else None
        from app.modules.robots.config.migration import effective_pipeline_from_config, ensure_config_v2

        config = ensure_config_v2(config)
        universe_mode = normalize_universe_mode(config)
        pipeline = effective_pipeline_from_config(config)
        pipeline_mode = "ANY" if str(pipeline.get("mode") or "").upper() == "ANY" else "ALL"
        optimize_order = bool(dict(config.get("pipeline") or {}).get("optimize_order", True))
        filters = (
            list(pipeline.get("filters") or [])
            if universe_uses_pipeline(config) or universe_whitelist_tickers(config) is not None
            else []
        )
        allowed_figis = self._resolve_allowed_tickers_from_config(config)

        rows = db.execute(
            text(
                f"""
                SELECT ticker, last_price, open_price, high_price, low_price, prev_price, value_today, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, spread, bid, ask, prev_legal_close_price
                FROM market_snapshot_data
                WHERE snapshot_id = :snapshot_id
                """
            ),
            {"snapshot_id": snapshot_id},
        ).fetchall()
        mapped_rows = [
            {
                "ticker": str(r[0]).upper(),
                "last_price": float(r[1]) if r[1] is not None else None,
                "open_price": float(r[2]) if r[2] is not None else None,
                "high_price": float(r[3]) if r[3] is not None else None,
                "low_price": float(r[4]) if r[4] is not None else None,
                "prev_price": float(r[5]) if r[5] is not None else None,
                "value_today": float(r[6]) if r[6] is not None else 0.0,
                "volume_lots": float(r[7]) if r[7] is not None else 0.0,
                "security_status": r[8],
                "trading_status": r[9],
                "num_trades": int(r[10]) if r[10] is not None else 0,
                "min_step": float(r[11]) if r[11] is not None else None,
                "issue_size": float(r[12]) if r[12] is not None else None,
                "spread": float(r[13]) if r[13] is not None else None,
                "bid": float(r[14]) if r[14] is not None else None,
                "ask": float(r[15]) if r[15] is not None else None,
                "prev_legal_close_price": float(r[16]) if r[16] is not None else None,
            }
            for r in rows
        ]
        if universe_mode == UNIVERSE_MODE_FIXED and allowed_figis:
            mapped_rows = [r for r in mapped_rows if r.get("ticker") in allowed_figis]
        elif allowed_figis:
            mapped_rows = [r for r in mapped_rows if r.get("ticker") in allowed_figis]
        elif universe_mode == UNIVERSE_MODE_TQBR:
            mapped_rows = [r for r in mapped_rows if universe_min_tradable_row(r)]
        atr_filter_enabled = any(str((f or {}).get("type") or "").lower() == "atr" and (f or {}).get("enabled", True) is not False for f in filters)
        fast_filters = [f for f in filters if str((f or {}).get("type") or "").lower() != "atr"]
        pre_candidates: List[Dict[str, Any]] = []
        for mapped in mapped_rows:
            pre_res = self._evaluate_pipeline_row(
                mapped, filters=fast_filters, mode=pipeline_mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            if (pipeline_mode == "ALL" and pre_res["accepted"]) or (pipeline_mode == "ANY" and not pre_res["accepted"]):
                pre_candidates.append(mapped)
        atr_map, _ = await self._load_atr_percent_map(db=db, board="TQBR", rows=pre_candidates if atr_filter_enabled else [], filters=filters)
        upsert_q = text(
            f"""
            INSERT INTO daily_universe
            (robot_id, trade_date, ticker, source, filter_result, reject_reason, snapshot_id,
             price_at_filter, volume_at_filter, gap_percent, applied_filters, created_at)
            VALUES
            (:robot_id, :trade_date, :ticker, 'PIPELINE', :filter_result, :reject_reason, :snapshot_id,
             :price_at_filter, :volume_at_filter, :gap_percent, :applied_filters, :created_at)
            ON CONFLICT (robot_id, trade_date, ticker)
            DO UPDATE SET
                source = EXCLUDED.source,
                filter_result = EXCLUDED.filter_result,
                reject_reason = EXCLUDED.reject_reason,
                snapshot_id = EXCLUDED.snapshot_id,
                price_at_filter = EXCLUDED.price_at_filter,
                volume_at_filter = EXCLUDED.volume_at_filter,
                gap_percent = EXCLUDED.gap_percent,
                applied_filters = EXCLUDED.applied_filters
            """
        )
        decision_q = text(
            f"""
            INSERT INTO robot_decisions
            (robot_id, figi, stage, decision_type, decision, reason_code, payload, created_at)
            VALUES
            (:robot_id, :figi, 'dms_init', 'paper_selection', :decision, :reason_code, CAST(:payload AS jsonb), :created_at)
            """
        )
        written = 0
        accepted_tickers: List[str] = []
        for mapped in mapped_rows:
            ticker = mapped["ticker"]
            mapped["atr_percent"] = atr_map.get(ticker)
            if not self._inside_schedule_window(datetime.now(timezone.utc), schedule):
                reject_reason = "Outside trading hours"
                db.execute(
                    upsert_q,
                    {
                        "robot_id": robot_id,
                        "trade_date": today,
                        "ticker": ticker,
                        "filter_result": "SKIP",
                        "reject_reason": reject_reason,
                        "snapshot_id": snapshot_id,
                        "price_at_filter": mapped["last_price"],
                        "volume_at_filter": int(mapped["value_today"] or 0),
                        "gap_percent": None,
                        "applied_filters": json.dumps(filters, ensure_ascii=False),
                        "created_at": datetime.now(timezone.utc),
                    },
                )
                written += 1
                continue
            eval_res = self._evaluate_pipeline_row(
                mapped, filters=filters, mode=pipeline_mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            reject_reason = None if eval_res["accepted"] else eval_res["reason"]
            db.execute(
                upsert_q,
                {
                    "robot_id": robot_id,
                    "trade_date": today,
                    "ticker": ticker,
                    "filter_result": "REJECT" if reject_reason else "ACCEPT",
                    "reject_reason": reject_reason,
                    "snapshot_id": snapshot_id,
                    "price_at_filter": mapped["last_price"],
                    "volume_at_filter": int(mapped["value_today"] or 0),
                    "gap_percent": eval_res.get("gap_percent"),
                    "applied_filters": json.dumps(filters, ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.execute(
                decision_q,
                {
                    "robot_id": robot_id,
                    "figi": ticker,
                    "decision": "ACCEPT" if reject_reason is None else "REJECT",
                    "reason_code": None if reject_reason is None else "FILTER_REJECT",
                    "payload": json.dumps(
                        {
                            "source": "PIPELINE",
                            "snapshot_id": snapshot_id,
                            "reason": reject_reason,
                            "filters": filters,
                        },
                        ensure_ascii=False,
                    ),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            if reject_reason is None:
                accepted_tickers.append(ticker)
            written += 1

        # Always include open portfolio positions for monitoring, even if they failed morning filters.
        portfolio_rows = db.execute(
            text(
                f"""
                SELECT DISTINCT COALESCE(NULLIF(ticker, ''), figi) AS ticker
                FROM robot_trades
                WHERE robot_id = :robot_id
                  AND status = 'open'
                """
            ),
            {"robot_id": robot_id},
        ).fetchall()
        portfolio_tickers = [str(r[0]).upper() for r in portfolio_rows if r[0]]
        for ticker in portfolio_tickers:
            db.execute(
                upsert_q,
                {
                    "robot_id": robot_id,
                    "trade_date": today,
                    "ticker": ticker,
                    "filter_result": "ACCEPT",
                    "reject_reason": "В портфеле",
                    "snapshot_id": snapshot_id,
                    "price_at_filter": None,
                    "volume_at_filter": 0,
                    "gap_percent": None,
                    "applied_filters": json.dumps(filters, ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.execute(
                decision_q,
                {
                    "robot_id": robot_id,
                    "figi": ticker,
                    "decision": "ACCEPT",
                    "reason_code": "PORTFOLIO_FORCE_INCLUDE",
                    "payload": json.dumps(
                        {
                            "source": "PORTFOLIO",
                            "snapshot_id": snapshot_id,
                            "reason": "Open position exists",
                        },
                        ensure_ascii=False,
                    ),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            if ticker not in accepted_tickers:
                accepted_tickers.append(ticker)

        if accepted_tickers:
            await self._ensure_candles_cached_for_tickers(
                db,
                board="TQBR",
                tickers=accepted_tickers,
                interval_code=5,
                days_back=2,
            )
        db.commit()
        return written

    async def process_pending_subscriptions(self, db: Session) -> Dict[str, Any]:
        pending = db.execute(
            text(
                f"""
                SELECT id, robot_id, board
                FROM dms_subscriptions
                WHERE status = 'PENDING'
                ORDER BY requested_at ASC
                LIMIT 200
                """
            )
        ).fetchall()
        if not pending:
            return {"processed_subscriptions": 0, "created_snapshots": 0, "analyzer_written_rows": 0, "errors": []}
        grouped: Dict[str, List[Any]] = {}
        for p in pending:
            grouped.setdefault(str(p[2]), []).append(p)
        created_snapshots = 0
        processed = 0
        analyzer_written = 0
        errors: List[str] = []
        for board, subs in grouped.items():
            snap = await self.create_snapshot(db, board=board, ttl_minutes=5, is_manual=False)
            if snap["status"] != "SUCCESS":
                err = snap.get("message") or f"snapshot error for board {board}"
                errors.append(err)
                for s in subs:
                    db.execute(
                        text(f"UPDATE dms_subscriptions SET status='ERROR' WHERE id=:id"),
                        {"id": int(s[0])},
                    )
                db.commit()
                continue
            created_snapshots += 1
            snapshot_id = int(snap["snapshot_id"])
            for s in subs:
                sub_id = int(s[0])
                robot_id = int(s[1])
                db.execute(
                    text(
                        f"""
                        UPDATE dms_subscriptions
                        SET status='READY', snapshot_id=:snapshot_id
                        WHERE id=:id
                        """
                    ),
                    {"id": sub_id, "snapshot_id": snapshot_id},
                )
                analyzer_written += await self._apply_analyzer(db, robot_id=robot_id, snapshot_id=snapshot_id)
                processed += 1
            db.commit()
        return {
            "processed_subscriptions": processed,
            "created_snapshots": created_snapshots,
            "analyzer_written_rows": analyzer_written,
            "errors": errors,
        }

    def _subscription_key(self, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:64]

    async def subscribe(self, db: Session, user_id: int, body) -> Dict[str, Any]:
        robot_q = f"""
            SELECT id, type
            FROM robots
            WHERE id = :robot_id AND user_id = :user_id AND status != 0
            LIMIT 1
        """
        robot = db.execute(text(robot_q), {"robot_id": body.robot_id, "user_id": user_id}).first()
        if not robot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Робот не найден")

        key_payload = {
            "board": body.board,
            "include_candles": body.include_candles,
            "candle_interval": body.candle_interval,
            "candle_depth": body.candle_depth,
            "snapshot_hour": body.snapshot_hour,
        }
        sub_key = self._subscription_key(key_payload)
        now = datetime.now(timezone.utc)
        req_date = now.date()

        fresh_snapshot_q = f"""
            SELECT id
            FROM market_snapshot
            WHERE board = :board
              AND status = 'SUCCESS'
              AND snapshot_time >= :min_time
            ORDER BY snapshot_time DESC
            LIMIT 1
        """
        min_time = now - timedelta(minutes=max(int(body.ttl_minutes), 0))
        fresh = db.execute(text(fresh_snapshot_q), {"board": body.board, "min_time": min_time}).first()
        snapshot_id: Optional[int] = int(fresh[0]) if fresh else None
        sub_status = "READY" if snapshot_id else "PENDING"

        insert_q = f"""
            INSERT INTO dms_subscriptions
            (robot_id, subscription_key, board, include_candles, candle_interval, candle_depth,
             requested_at, request_date, snapshot_hour, status, snapshot_id, created_at)
            VALUES
            (:robot_id, :subscription_key, :board, :include_candles, :candle_interval, :candle_depth,
             :requested_at, :request_date, :snapshot_hour, :status, :snapshot_id, :created_at)
            ON CONFLICT (robot_id, subscription_key, request_date, snapshot_hour)
            DO UPDATE SET
                requested_at = EXCLUDED.requested_at,
                status = EXCLUDED.status,
                snapshot_id = COALESCE(EXCLUDED.snapshot_id, dms_subscriptions.snapshot_id)
            RETURNING id, robot_id, subscription_key, board, status, requested_at, snapshot_hour, snapshot_id
        """
        row = db.execute(
            text(insert_q),
            {
                "robot_id": body.robot_id,
                "subscription_key": sub_key,
                "board": body.board,
                "include_candles": bool(body.include_candles),
                "candle_interval": body.candle_interval,
                "candle_depth": int(body.candle_depth),
                "requested_at": now,
                "request_date": req_date,
                "snapshot_hour": body.snapshot_hour,
                "status": sub_status,
                "snapshot_id": snapshot_id,
                "created_at": now,
            },
        ).first()
        db.commit()
        return {
            "subscription": {
                "id": int(row[0]),
                "robot_id": int(row[1]),
                "subscription_key": str(row[2]),
                "board": str(row[3]),
                "status": str(row[4]),
                "requested_at": row[5],
                "snapshot_hour": row[6],
                "snapshot_id": int(row[7]) if row[7] is not None else None,
            },
            "reused_snapshot": bool(snapshot_id),
        }

    async def list_subscriptions(self, db: Session, user_id: int):
        q = f"""
            SELECT s.id, s.robot_id, s.subscription_key, s.board, s.status, s.requested_at, s.snapshot_hour, s.snapshot_id
            FROM dms_subscriptions s
            JOIN robots r ON r.id = s.robot_id
            WHERE r.user_id = :user_id
            ORDER BY s.requested_at DESC
            LIMIT 200
        """
        rows = db.execute(text(q), {"user_id": user_id}).fetchall()
        return [
            {
                "id": int(r[0]),
                "robot_id": int(r[1]),
                "subscription_key": str(r[2]),
                "board": str(r[3]),
                "status": str(r[4]),
                "requested_at": r[5],
                "snapshot_hour": r[6],
                "snapshot_id": int(r[7]) if r[7] is not None else None,
            }
            for r in rows
        ]

    async def list_snapshots(self, db: Session, board: Optional[str] = None):
        q = f"""
            SELECT s.id, s.snapshot_time, s.board, s.status, s.error_message, s.ttl_minutes, s.created_at,
                   COALESCE(d.cnt, 0) AS securities_count
            FROM market_snapshot s
            LEFT JOIN (
                SELECT snapshot_id, COUNT(*) AS cnt
                FROM market_snapshot_data
                GROUP BY snapshot_id
            ) d ON d.snapshot_id = s.id
            WHERE (:board IS NULL OR s.board = :board)
            ORDER BY s.snapshot_time DESC
            LIMIT 100
        """
        rows = db.execute(text(q), {"board": board}).fetchall()
        return [
            {
                "id": int(r[0]),
                "snapshot_time": r[1],
                "board": str(r[2]),
                "status": str(r[3]),
                "error_message": r[4],
                "ttl_minutes": int(r[5] or 0),
                "created_at": r[6],
                "securities_count": int(r[7] or 0),
            }
            for r in rows
        ]

    async def list_daily_universe(self, db: Session, user_id: int, robot_id: Optional[int], trade_date: Optional[date]):
        q = f"""
            SELECT u.id, u.robot_id, u.trade_date, u.ticker, u.source, u.filter_result, u.reject_reason,
                   u.snapshot_id, u.price_at_filter, u.volume_at_filter, u.atr_value, u.gap_percent, u.applied_filters, u.created_at
            FROM daily_universe u
            JOIN robots r ON r.id = u.robot_id
            WHERE r.user_id = :user_id
              AND (:robot_id IS NULL OR u.robot_id = :robot_id)
              AND (:trade_date IS NULL OR u.trade_date = :trade_date)
            ORDER BY u.created_at DESC
            LIMIT 1000
        """
        rows = db.execute(
            text(q),
            {"user_id": user_id, "robot_id": robot_id, "trade_date": trade_date},
        ).fetchall()
        items = []
        for r in rows:
            parsed_filters = None
            if r[12]:
                try:
                    parsed_filters = json.loads(r[12]) if isinstance(r[12], str) else r[12]
                except Exception:
                    parsed_filters = None
            items.append(
                {
                    "id": int(r[0]),
                    "robot_id": int(r[1]),
                    "trade_date": r[2],
                    "ticker": str(r[3]),
                    "source": str(r[4]),
                    "filter_result": r[5],
                    "reject_reason": r[6],
                    "snapshot_id": int(r[7]) if r[7] is not None else None,
                    "price_at_filter": float(r[8]) if r[8] is not None else None,
                    "volume_at_filter": int(r[9]) if r[9] is not None else None,
                    "atr_value": float(r[10]) if r[10] is not None else None,
                    "gap_percent": float(r[11]) if r[11] is not None else None,
                    "applied_filters": parsed_filters,
                    "created_at": r[13],
                }
            )
        return {"total": len(items), "items": items}

    async def get_filter_log(self, db: Session, user_id: int, robot_id: Optional[int], trade_date: Optional[date], limit: int = 500):
        q = f"""
            SELECT u.id, u.robot_id, u.trade_date, u.ticker, u.source, u.filter_result, u.reject_reason,
                   u.snapshot_id, u.price_at_filter, u.volume_at_filter, u.atr_value, u.gap_percent, u.applied_filters, u.created_at
            FROM daily_universe u
            JOIN robots r ON r.id = u.robot_id
            WHERE r.user_id = :user_id
              AND (:robot_id IS NULL OR u.robot_id = :robot_id)
              AND (:trade_date IS NULL OR u.trade_date = :trade_date)
            ORDER BY u.created_at DESC
            LIMIT :limit
        """
        rows = db.execute(
            text(q),
            {"user_id": user_id, "robot_id": robot_id, "trade_date": trade_date, "limit": max(1, min(limit, 2000))},
        ).fetchall()
        items = []
        passed = 0
        rejected = 0
        for r in rows:
            filter_result = (r[5] or "").upper() if r[5] else None
            if filter_result == "ACCEPT":
                passed += 1
            elif filter_result == "REJECT":
                rejected += 1
            parsed_filters = None
            if r[12]:
                try:
                    parsed_filters = json.loads(r[12]) if isinstance(r[12], str) else r[12]
                except Exception:
                    parsed_filters = None
            items.append(
                {
                    "id": int(r[0]),
                    "robot_id": int(r[1]),
                    "trade_date": r[2],
                    "ticker": str(r[3]),
                    "source": str(r[4]),
                    "filter_result": r[5],
                    "reject_reason": r[6],
                    "snapshot_id": int(r[7]) if r[7] is not None else None,
                    "price_at_filter": float(r[8]) if r[8] is not None else None,
                    "volume_at_filter": int(r[9]) if r[9] is not None else None,
                    "atr_value": float(r[10]) if r[10] is not None else None,
                    "gap_percent": float(r[11]) if r[11] is not None else None,
                    "applied_filters": parsed_filters,
                    "created_at": r[13],
                }
            )
        return {
            "total_checked": len(items),
            "passed": passed,
            "rejected": rejected,
            "items": items,
        }

    async def preview_pipeline_setup(
        self,
        db: Session,
        user_id: int,
        board: str,
        filters: List[Dict[str, Any]],
        mode: str,
        universe_mode: str,
        fixed_tickers: List[str],
        warmup_candles: bool = False,
    ) -> Dict[str, Any]:
        """Preview pipeline для ad-hoc /testing (без robot_id)."""
        synthetic_config = {
            "universe_mode": normalize_universe_mode(universe_mode),
            "allowed_figis": [str(t).strip().upper() for t in (fixed_tickers or []) if str(t).strip()],
            "pipeline": {"mode": mode, "filters": filters, "optimize_order": True},
        }
        return await self.preview_pipeline(
            db=db,
            user_id=user_id,
            robot_id=0,
            board=board,
            filters=filters,
            mode=mode,
            warmup_candles=warmup_candles,
            config_override=synthetic_config,
        )

    async def preview_pipeline(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        board: str,
        filters: List[Dict[str, Any]],
        mode: str,
        warmup_candles: bool = True,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if config_override is not None:
            robot_config = dict(config_override)
        else:
            robot = db.execute(
                text(f"SELECT id, config FROM robots WHERE id=:robot_id AND user_id=:user_id AND status != 0"),
                {"robot_id": robot_id, "user_id": user_id},
            ).first()
            if not robot:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Робот не найден")
            robot_config = dict(robot[1] or {}) if len(robot) > 1 else {}

        allowed_figis = self._resolve_allowed_tickers_from_config(robot_config)
        universe_mode = normalize_universe_mode(robot_config)
        pipeline = dict(robot_config.get("pipeline") or {})
        optimize_order = bool(pipeline.get("optimize_order", True))

        now_utc = datetime.now(timezone.utc)
        today_utc = now_utc.date()
        snap = db.execute(
            text(
                f"""
                SELECT id, snapshot_time
                FROM market_snapshot
                WHERE board=:board AND status='SUCCESS'
                ORDER BY snapshot_time DESC
                LIMIT 1
                """
            ),
            {"board": board},
        ).first()
        latest_snapshot_id: Optional[int] = None
        latest_snapshot_time: Optional[datetime] = None
        if snap:
            latest_snapshot_id = int(snap[0])
            latest_snapshot_time = snap[1]

        is_fresh_today = bool(
            latest_snapshot_id
            and latest_snapshot_time is not None
            and latest_snapshot_time.astimezone(timezone.utc).date() == today_utc
        )

        if not is_fresh_today:
            created = await self.create_snapshot(db, board=board, ttl_minutes=0, is_manual=True, user_id=user_id)
            if created.get("status") != "SUCCESS":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=created.get("message") or "Не удалось получить snapshot")
            snapshot_id = int(created["snapshot_id"])
        else:
            snapshot_id = int(latest_snapshot_id)

        rows = db.execute(
            text(
                f"""
                SELECT ticker, last_price, open_price, high_price, low_price, prev_price, value_today, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, spread, bid, ask, prev_legal_close_price
                FROM market_snapshot_data
                WHERE snapshot_id=:snapshot_id
                ORDER BY ticker
                """
            ),
            {"snapshot_id": snapshot_id},
        ).fetchall()
        mapped_rows = [
            {
                "ticker": r[0],
                "last_price": float(r[1]) if r[1] is not None else None,
                "open_price": float(r[2]) if r[2] is not None else None,
                "high_price": float(r[3]) if r[3] is not None else None,
                "low_price": float(r[4]) if r[4] is not None else None,
                "prev_price": float(r[5]) if r[5] is not None else None,
                "value_today": float(r[6]) if r[6] is not None else 0.0,
                "volume_lots": float(r[7]) if r[7] is not None else 0.0,
                "security_status": r[8],
                "trading_status": r[9],
                "num_trades": int(r[10]) if r[10] is not None else 0,
                "min_step": float(r[11]) if r[11] is not None else None,
                "issue_size": float(r[12]) if r[12] is not None else None,
                "spread": float(r[13]) if r[13] is not None else None,
                "bid": float(r[14]) if r[14] is not None else None,
                "ask": float(r[15]) if r[15] is not None else None,
                "prev_legal_close_price": float(r[16]) if r[16] is not None else None,
            }
            for r in rows
        ]
        if universe_mode == UNIVERSE_MODE_FIXED and allowed_figis:
            mapped_rows = [r for r in mapped_rows if str(r.get("ticker") or "").upper() in allowed_figis]
        elif universe_mode == UNIVERSE_MODE_TQBR:
            mapped_rows = [r for r in mapped_rows if universe_min_tradable_row({**r, "ticker": str(r.get("ticker") or "").upper()})]
        pipeline_mode = "ANY" if str(mode or "").upper() == "ANY" else "ALL"
        atr_filter_enabled = any(str((f or {}).get("type") or "").lower() == "atr" and (f or {}).get("enabled", True) is not False for f in filters)
        fast_filters = [f for f in filters if str((f or {}).get("type") or "").lower() != "atr"]
        pre_candidates: List[Dict[str, Any]] = []
        for mapped in mapped_rows:
            pre_res = self._evaluate_pipeline_row(
                mapped, filters=fast_filters, mode=pipeline_mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            if (pipeline_mode == "ALL" and pre_res["accepted"]) or (pipeline_mode == "ANY" and not pre_res["accepted"]):
                pre_candidates.append(mapped)
        atr_map, _ = await self._load_atr_percent_map(
            db=db, board=board, rows=pre_candidates if atr_filter_enabled else [], filters=filters, user_id=user_id
        )
        total = len(rows)
        passed = 0
        rejected = 0
        sample: List[Dict[str, Any]] = []
        accepted_tickers: List[str] = []
        for mapped in mapped_rows:
            mapped["atr_percent"] = atr_map.get(str(mapped["ticker"]).upper())
            res = self._evaluate_pipeline_row(
                mapped, filters=filters, mode=mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            if res["accepted"]:
                passed += 1
                accepted_tickers.append(str(mapped["ticker"]).upper())
            else:
                rejected += 1
            sample.append(
                {
                    "ticker": mapped["ticker"],
                    "result": "ACCEPT" if res["accepted"] else "REJECT",
                    "reason": res["reason"],
                    "last_price": mapped["last_price"],
                    "value_today": mapped["value_today"],
                    "volume_lots": mapped["volume_lots"],
                    "gap_percent": res["gap_percent"],
                    "atr_percent": res.get("atr_percent"),
                    "spread_percent": res.get("spread_percent"),
                }
            )
        if warmup_candles and accepted_tickers:
            await self._ensure_candles_cached_for_tickers(
                db,
                board=board,
                tickers=accepted_tickers,
                interval_code=5,
                days_back=2,
                user_id=user_id,
            )
        return {
            "total_checked": total,
            "passed": passed,
            "rejected": rejected,
            "sample": sample,
        }


dms_service = DmsService()
