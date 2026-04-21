import hashlib
import json
from datetime import date, datetime, timezone, timedelta, time
from typing import Any, Dict, Optional, List
import httpx

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings


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
        "num_trades": 9,
        "gap": 10,
        "spread": 11,
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
                    INSERT INTO {settings.DB_SCHEMA}.external_api_logs
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
    ) -> Dict[str, Any]:
        ticker = str(row.get("ticker") or "").upper()
        open_price = self._safe_float(row.get("open_price"))
        prev_price = self._safe_float(row.get("prev_price"))
        last_price = self._safe_float(row.get("last_price"))
        value_today = self._safe_float(row.get("value_today")) or 0.0
        volume_lots = self._safe_float(row.get("volume_lots")) or 0.0
        trades_count = int(row.get("num_trades") or 0)
        issue_size = self._safe_float(row.get("issue_size"))
        min_step = self._safe_float(row.get("min_step"))
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
            return {"accepted": False, "reason": "Not in allowed_figis", "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}

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
                ok = value_today >= limit
                checks.append(ok)
                if not ok:
                    reasons.append(f"VALTODAY {value_today:.0f} < {limit:.0f}")
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

        if not checks:
            return {"accepted": True, "reason": None, "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}
        if str(mode).upper() == "ANY":
            accepted = any(checks)
            return {"accepted": accepted, "reason": None if accepted else "; ".join(reasons[:2]), "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}
        accepted = all(checks)
        return {"accepted": accepted, "reason": None if accepted else "; ".join(reasons[:2]), "gap_percent": gap_percent, "atr_percent": atr_percent, "spread_percent": spread_percent}

    async def _load_atr_percent_map(
        self,
        db: Session,
        board: str,
        rows: List[Dict[str, Any]],
        filters: List[Dict[str, Any]],
        user_id: Optional[int] = None,
    ) -> Dict[str, float]:
        atr_filter = next((f for f in filters if str((f or {}).get("type") or "").lower() == "atr" and (f or {}).get("enabled", True) is not False), None)
        if not atr_filter:
            return {}
        period = int(atr_filter.get("period") or 14)
        limit = max(5, min(60, period))
        out: Dict[str, float] = {}
        candidate_rows = [r for r in rows if str(r.get("ticker") or "").upper() and (self._safe_float(r.get("last_price")) or 0) > 0]
        chunk_size = 50
        for i in range(0, len(candidate_rows), chunk_size):
            chunk = candidate_rows[i:i + chunk_size]
            tickers = [str(r.get("ticker")).upper() for r in chunk]
            # Batch request for multiple tickers in one call.
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json"
            params = {"iss.meta": "off", "securities": ",".join(tickers), "interval": 24, "limit": limit}
            started_at = datetime.now(timezone.utc)
            try:
                async with httpx.AsyncClient(timeout=20, verify=False) as client:
                    resp = await client.get(url, params=params)
            except Exception as e:
                finished_at = datetime.now(timezone.utc)
                self._log_external_api_call(
                    db, endpoint=url, request_data={"params": dict(params)}, response_status=None, response_data={},
                    started_at=started_at, finished_at=finished_at, success=False, error_message=str(e), user_id=user_id
                )
                continue
            finished_at = datetime.now(timezone.utc)
            payload: Dict[str, Any] = {}
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            self._log_external_api_call(
                db, endpoint=url, request_data={"params": dict(params)}, response_status=resp.status_code, response_data=payload,
                started_at=started_at, finished_at=finished_at, success=resp.status_code == 200,
                error_message=None if resp.status_code == 200 else f"HTTP {resp.status_code}", user_id=user_id
            )
            if resp.status_code != 200:
                continue
            candles_block = payload.get("candles") or {}
            candles = candles_block.get("data") or []
            cols = candles_block.get("columns") or []
            idx = {name: ix for ix, name in enumerate(cols)}
            secid_i = idx.get("SECID") if "SECID" in idx else idx.get("secid")
            h_i, l_i, c_i = idx.get("high"), idx.get("low"), idx.get("close")
            if secid_i is None or h_i is None or l_i is None or c_i is None:
                continue
            candles_by_ticker: Dict[str, List[List[Any]]] = {}
            for c in candles:
                if secid_i >= len(c):
                    continue
                tk = str(c[secid_i]).upper()
                candles_by_ticker.setdefault(tk, []).append(c)
            price_by_ticker = {str(r.get("ticker") or "").upper(): self._safe_float(r.get("last_price")) for r in chunk}
            for ticker, c_rows in candles_by_ticker.items():
                last_price = price_by_ticker.get(ticker)
                if not last_price or last_price <= 0 or len(c_rows) < 2:
                    continue
                trs: List[float] = []
                prev_close: Optional[float] = None
                for c in c_rows:
                    high = self._safe_float(c[h_i] if h_i < len(c) else None)
                    low = self._safe_float(c[l_i] if l_i < len(c) else None)
                    close = self._safe_float(c[c_i] if c_i < len(c) else None)
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
        return out

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
                # MOEX sometimes ignores paging params; protect from infinite loops on repeated pages.
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
                rows.append(
                    {
                        "ticker": ticker,
                        "board_id": secv(row, "BOARDID"),
                        "short_name": secv(row, "SHORTNAME"),
                        "sec_name": secv(row, "SECNAME"),
                        "isin": secv(row, "ISIN"),
                        "lot_size": secv(row, "LOTSIZE"),
                        "last_price": mdv("LAST"),
                        "open_price": mdv("OPEN"),
                        "low_price": mdv("LOW"),
                        "high_price": mdv("HIGH"),
                        "prev_price": mdv("PREVPRICE"),
                        "close_price": mdv("CLOSEPRICE"),
                        "value_today": mdv("VALTODAY"),
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
                        "securities_payload": {k: secv(row, k) for k in sec_cols},
                        "marketdata_payload": {k: mdv(k) for k in md_cols},
                    }
                )
            if not has_cursor:
                # Endpoint returned a full dataset without explicit cursor paging metadata.
                break
            if len(sec_data) < 100:
                break
            start += len(sec_data)
            if len(seen_page_signatures) >= max_pages:
                break
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
            INSERT INTO {settings.DB_SCHEMA}.market_snapshot
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
                        UPDATE {settings.DB_SCHEMA}.market_snapshot
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
                INSERT INTO {settings.DB_SCHEMA}.market_snapshot_data
                (snapshot_id, ticker, board_id, short_name, sec_name, isin, lot_size,
                 last_price, open_price, low_price, high_price, prev_price, close_price,
                 value_today, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, bid, ask, spread, market_update_time,
                 securities_payload, marketdata_payload)
                VALUES
                (:snapshot_id, :ticker, :board_id, :short_name, :sec_name, :isin, :lot_size,
                 :last_price, :open_price, :low_price, :high_price, :prev_price, :close_price,
                 :value_today, :volume_lots, :security_status, :trading_status, :num_trades, :min_step, :issue_size, :bid, :ask, :spread, :market_update_time,
                 CAST(:securities_payload AS jsonb), CAST(:marketdata_payload AS jsonb))
                ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
                    board_id = EXCLUDED.board_id,
                    short_name = EXCLUDED.short_name,
                    sec_name = EXCLUDED.sec_name,
                    isin = EXCLUDED.isin,
                    lot_size = EXCLUDED.lot_size,
                    last_price = EXCLUDED.last_price,
                    open_price = EXCLUDED.open_price,
                    low_price = EXCLUDED.low_price,
                    high_price = EXCLUDED.high_price,
                    prev_price = EXCLUDED.prev_price,
                    close_price = EXCLUDED.close_price,
                    value_today = EXCLUDED.value_today,
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
                    securities_payload = EXCLUDED.securities_payload,
                    marketdata_payload = EXCLUDED.marketdata_payload
            """
            for r in raw_rows:
                bid = float(r["bid"]) if r.get("bid") is not None else None
                ask = float(r["ask"]) if r.get("ask") is not None else None
                spread = (ask - bid) if bid is not None and ask is not None else None
                db.execute(
                    text(insert_data_q),
                    {
                        "snapshot_id": snapshot_id,
                        "ticker": r["ticker"],
                        "board_id": r.get("board_id"),
                        "short_name": r.get("short_name"),
                        "sec_name": r.get("sec_name"),
                        "isin": r.get("isin"),
                        "lot_size": r.get("lot_size"),
                        "last_price": r.get("last_price"),
                        "open_price": r.get("open_price"),
                        "low_price": r.get("low_price"),
                        "high_price": r.get("high_price"),
                        "prev_price": r.get("prev_price"),
                        "close_price": r.get("close_price"),
                        "value_today": r.get("value_today"),
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
                        "securities_payload": json.dumps(r.get("securities_payload") or {}, ensure_ascii=False),
                        "marketdata_payload": json.dumps(r.get("marketdata_payload") or {}, ensure_ascii=False),
                    },
                )
            db.execute(
                text(f"UPDATE {settings.DB_SCHEMA}.market_snapshot SET status='SUCCESS' WHERE id=:id"),
                {"id": snapshot_id},
            )
            db.commit()
            return {"snapshot_id": snapshot_id, "status": "SUCCESS", "securities_count": len(raw_rows), "message": None}
        except Exception as e:
            db.execute(
                text(f"UPDATE {settings.DB_SCHEMA}.market_snapshot SET status='ERROR', error_message=:msg WHERE id=:id"),
                {"id": snapshot_id, "msg": str(e)},
            )
            db.commit()
            return {"snapshot_id": snapshot_id, "status": "ERROR", "securities_count": 0, "message": str(e)}

    async def cleanup_old_snapshots(self, db: Session, older_than_days: int = 3) -> Dict[str, int]:
        threshold = datetime.now(timezone.utc) - timedelta(days=max(1, int(older_than_days)))
        old_ids = db.execute(
            text(
                f"""
                SELECT id
                FROM {settings.DB_SCHEMA}.market_snapshot
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
                INSERT INTO {settings.DB_SCHEMA}.market_snapshot_history
                SELECT * FROM {settings.DB_SCHEMA}.market_snapshot
                WHERE id = ANY(:ids)
                ON CONFLICT DO NOTHING
                """
            ),
            {"ids": ids},
        )
        moved_rows = db.execute(
            text(
                f"""
                INSERT INTO {settings.DB_SCHEMA}.market_snapshot_data_history
                SELECT * FROM {settings.DB_SCHEMA}.market_snapshot_data
                WHERE snapshot_id = ANY(:ids)
                ON CONFLICT DO NOTHING
                RETURNING id
                """
            ),
            {"ids": ids},
        ).fetchall()
        db.execute(
            text(f"DELETE FROM {settings.DB_SCHEMA}.market_snapshot_data WHERE snapshot_id = ANY(:ids)"),
            {"ids": ids},
        )
        deleted_snapshots = db.execute(
            text(f"DELETE FROM {settings.DB_SCHEMA}.market_snapshot WHERE id = ANY(:ids) RETURNING id"),
            {"ids": ids},
        ).fetchall()
        db.commit()
        return {
            "moved_snapshots": len(ids),
            "moved_rows": len(moved_rows),
            "deleted_snapshots": len(deleted_snapshots),
        }

    async def _apply_analyzer(self, db: Session, robot_id: int, snapshot_id: int) -> int:
        robot_row = db.execute(
            text(f"SELECT config FROM {settings.DB_SCHEMA}.robots WHERE id=:robot_id"),
            {"robot_id": robot_id},
        ).first()
        config = dict(robot_row[0] or {}) if robot_row else {}
        schedule_row = db.execute(
            text(
                f"""
                SELECT start_time, end_time, weekdays
                FROM {settings.DB_SCHEMA}.robot_schedules
                WHERE robot_id=:robot_id AND COALESCE(is_active,1)=1
                ORDER BY priority DESC, id DESC
                LIMIT 1
                """
            ),
            {"robot_id": robot_id},
        ).first()
        schedule = {"start_time": schedule_row[0], "end_time": schedule_row[1], "weekdays": schedule_row[2]} if schedule_row else None
        pipeline = dict(config.get("pipeline") or {})
        pipeline_mode = "ANY" if str(pipeline.get("mode") or "").upper() == "ANY" else "ALL"
        optimize_order = bool(pipeline.get("optimize_order", True))
        filters = list(pipeline.get("filters") or [])
        allowed_figis = {str(x).upper() for x in (config.get("allowed_figis") or []) if x}

        rows = db.execute(
            text(
                f"""
                SELECT ticker, last_price, open_price, prev_price, value_today, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, spread, bid, ask
                FROM {settings.DB_SCHEMA}.market_snapshot_data
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
                "prev_price": float(r[3]) if r[3] is not None else None,
                "value_today": float(r[4]) if r[4] is not None else 0.0,
                "volume_lots": float(r[5]) if r[5] is not None else 0.0,
                "security_status": r[6],
                "trading_status": r[7],
                "num_trades": int(r[8]) if r[8] is not None else 0,
                "min_step": float(r[9]) if r[9] is not None else None,
                "issue_size": float(r[10]) if r[10] is not None else None,
                "spread": float(r[11]) if r[11] is not None else None,
                "bid": float(r[12]) if r[12] is not None else None,
                "ask": float(r[13]) if r[13] is not None else None,
            }
            for r in rows
        ]
        atr_filter_enabled = any(str((f or {}).get("type") or "").lower() == "atr" and (f or {}).get("enabled", True) is not False for f in filters)
        fast_filters = [f for f in filters if str((f or {}).get("type") or "").lower() != "atr"]
        pre_candidates: List[Dict[str, Any]] = []
        for mapped in mapped_rows:
            pre_res = self._evaluate_pipeline_row(
                mapped, filters=fast_filters, mode=pipeline_mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            if (pipeline_mode == "ALL" and pre_res["accepted"]) or (pipeline_mode == "ANY" and not pre_res["accepted"]):
                pre_candidates.append(mapped)
        atr_map = await self._load_atr_percent_map(db=db, board="TQBR", rows=pre_candidates if atr_filter_enabled else [], filters=filters)
        today = datetime.now(timezone.utc).date()
        upsert_q = text(
            f"""
            INSERT INTO {settings.DB_SCHEMA}.daily_universe
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
        written = 0
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
            written += 1
        db.commit()
        return written

    async def process_pending_subscriptions(self, db: Session) -> Dict[str, Any]:
        pending = db.execute(
            text(
                f"""
                SELECT id, robot_id, board
                FROM {settings.DB_SCHEMA}.dms_subscriptions
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
                        text(f"UPDATE {settings.DB_SCHEMA}.dms_subscriptions SET status='ERROR' WHERE id=:id"),
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
                        UPDATE {settings.DB_SCHEMA}.dms_subscriptions
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
            FROM {settings.DB_SCHEMA}.robots
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
            FROM {settings.DB_SCHEMA}.market_snapshot
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
            INSERT INTO {settings.DB_SCHEMA}.dms_subscriptions
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
            FROM {settings.DB_SCHEMA}.dms_subscriptions s
            JOIN {settings.DB_SCHEMA}.robots r ON r.id = s.robot_id
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
            FROM {settings.DB_SCHEMA}.market_snapshot s
            LEFT JOIN (
                SELECT snapshot_id, COUNT(*) AS cnt
                FROM {settings.DB_SCHEMA}.market_snapshot_data
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
            FROM {settings.DB_SCHEMA}.daily_universe u
            JOIN {settings.DB_SCHEMA}.robots r ON r.id = u.robot_id
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
            FROM {settings.DB_SCHEMA}.daily_universe u
            JOIN {settings.DB_SCHEMA}.robots r ON r.id = u.robot_id
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

    async def preview_pipeline(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        board: str,
        filters: List[Dict[str, Any]],
        mode: str,
    ) -> Dict[str, Any]:
        robot = db.execute(
            text(f"SELECT id, config FROM {settings.DB_SCHEMA}.robots WHERE id=:robot_id AND user_id=:user_id AND status != 0"),
            {"robot_id": robot_id, "user_id": user_id},
        ).first()
        if not robot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Робот не найден")

        robot_config = dict(robot[1] or {}) if len(robot) > 1 else {}
        allowed_figis = {str(x).upper() for x in (robot_config.get("allowed_figis") or []) if x}
        pipeline = dict(robot_config.get("pipeline") or {})
        optimize_order = bool(pipeline.get("optimize_order", True))

        snap = db.execute(
            text(
                f"""
                SELECT id
                FROM {settings.DB_SCHEMA}.market_snapshot
                WHERE board=:board AND status='SUCCESS'
                ORDER BY snapshot_time DESC
                LIMIT 1
                """
            ),
            {"board": board},
        ).first()
        if not snap:
            created = await self.create_snapshot(db, board=board, ttl_minutes=0, is_manual=True, user_id=user_id)
            if created.get("status") != "SUCCESS":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=created.get("message") or "Не удалось получить snapshot")
            snapshot_id = int(created["snapshot_id"])
        else:
            snapshot_id = int(snap[0])

        rows = db.execute(
            text(
                f"""
                SELECT ticker, last_price, open_price, prev_price, value_today, volume_lots, security_status, trading_status, num_trades, min_step, issue_size, spread, bid, ask
                FROM {settings.DB_SCHEMA}.market_snapshot_data
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
                "prev_price": float(r[3]) if r[3] is not None else None,
                "value_today": float(r[4]) if r[4] is not None else 0.0,
                "volume_lots": float(r[5]) if r[5] is not None else 0.0,
                "security_status": r[6],
                "trading_status": r[7],
                "num_trades": int(r[8]) if r[8] is not None else 0,
                "min_step": float(r[9]) if r[9] is not None else None,
                "issue_size": float(r[10]) if r[10] is not None else None,
                "spread": float(r[11]) if r[11] is not None else None,
                "bid": float(r[12]) if r[12] is not None else None,
                "ask": float(r[13]) if r[13] is not None else None,
            }
            for r in rows
        ]
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
        atr_map = await self._load_atr_percent_map(
            db=db, board=board, rows=pre_candidates if atr_filter_enabled else [], filters=filters, user_id=user_id
        )
        total = len(rows)
        passed = 0
        rejected = 0
        sample: List[Dict[str, Any]] = []
        for mapped in mapped_rows:
            mapped["atr_percent"] = atr_map.get(str(mapped["ticker"]).upper())
            res = self._evaluate_pipeline_row(
                mapped, filters=filters, mode=mode, optimize_order=optimize_order, allowed_figis=allowed_figis
            )
            if res["accepted"]:
                passed += 1
            else:
                rejected += 1
            if len(sample) < 50:
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
        return {"total_checked": total, "passed": passed, "rejected": rejected, "sample": sample}


dms_service = DmsService()
