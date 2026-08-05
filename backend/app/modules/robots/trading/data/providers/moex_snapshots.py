"""
MOEX ISS history snapshots → market_snapshot_history (BRD-ARCH-04 этап 2 хвост).

Единственная точка HTTP к iss.moex.com для history-backtest snapshots.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.moex.http_gate import moex_http_acquire
from app.modules.moex.securities_listing_archive import load_listing_board_row_map

logger = logging.getLogger(__name__)

_MOEX_RETRYABLE_HTTP_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ProtocolError
)


def _safe_float_opt(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int_opt(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def history_backtest_moex_log(msg: str, *args: Any) -> None:
    logger.info(msg, *args)
    try:
        from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_info

        if args:
            log_backtest_run_info(msg, *args)
        else:
            log_backtest_run_info("%s", msg)
    except Exception:
        pass
    try:
        from app.core.logging_config import get_rest_logger

        get_rest_logger().info("    [MOEX-outbound] " + msg, *args)
    except Exception:
        pass


def log_moex_external_api_isolated(
    *,
    user_id: Optional[int],
    run_id: Optional[int],
    endpoint: str,
    request_data: Dict[str, Any],
    response_status: Optional[int],
    response_data: Optional[Dict[str, Any]],
    started_at: datetime,
    finished_at: datetime,
    success: bool,
    error_message: Optional[str] = None
) -> None:
    duration_ms = int(max(0.0, (finished_at - started_at).total_seconds() * 1000))
    schema = settings.DB_SCHEMA
    log_db = SessionLocal()
    try:
        log_db.execute(
            text(
                f"""
                INSERT INTO external_api_logs
                (user_id, token_id, broker, context_type, context_ref, endpoint, request_data, response_status, response_data,
                 started_at, finished_at, duration_ms, success, error_message)
                VALUES
                (:user_id, NULL, 'moex', 'history_backtest', :context_ref, :endpoint, CAST(:request_data AS jsonb), :response_status, CAST(:response_data AS jsonb),
                 :started_at, :finished_at, :duration_ms, :success, :error_message)
                """
            ),
            {
                "user_id": user_id,
                "context_ref": (str(run_id) if run_id is not None else None),
                "endpoint": (endpoint or "")[:500],
                "request_data": json.dumps(request_data, ensure_ascii=False),
                "response_status": response_status,
                "response_data": json.dumps(response_data or {}, ensure_ascii=False),
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "success": 1 if success else 0,
                "error_message": error_message,
            }
        )
        log_db.commit()
    except Exception as ex:
        logger.warning("external_api_logs (moex) insert failed: %s", ex)
        try:
            log_db.rollback()
        except Exception:
            pass
    finally:
        log_db.close()


async def fetch_board_issuesize_map(*, board: str) -> Dict[str, float]:
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,ISSUESIZE",
        "securities.limit": 10000,
    }
    out_m: Dict[str, float] = {}
    try:
        async with moex_http_acquire():
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=8.0, read=25.0),
                verify=False
            ) as client:
                resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return out_m
        payload = resp.json()
        block = payload.get("securities") or {}
        cols = list(block.get("columns") or [])
        data = list(block.get("data") or [])
        idx = {c: i for i, c in enumerate(cols)}
        si = idx.get("SECID", 0)
        ii = idx.get("ISSUESIZE")
        if ii is None:
            return out_m
        for r in data:
            if si >= len(r):
                continue
            secid = str(r[si]).strip().upper()
            raw = r[ii] if ii < len(r) else None
            sz = _safe_float_opt(raw)
            if secid and sz is not None and sz > 0:
                out_m[secid] = float(sz)
    except Exception as e:
        logger.warning("issuesize map fetch failed board=%s: %s", board, e)
    return out_m


async def fetch_moex_history_snapshot_day(
    *,
    day: date,
    board: str = "TQBR",
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    is_cancelled: Optional[Callable[[], bool]] = None
) -> Optional[List[Dict[str, Any]]]:
    from app.modules.robots.service import is_history_backtest_cancelled

    url = f"https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/{board}/securities.json"
    out: List[Dict[str, Any]] = []
    start = 0
    page_size = 100
    max_pages = 50
    seen_signatures: set[str] = set()

    def _cancelled() -> bool:
        if is_cancelled and is_cancelled():
            return True
        return run_id is not None and is_history_backtest_cancelled(run_id)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=8.0, read=20.0, write=20.0, pool=20.0),
        verify=False
    ) as client:
        from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

        for _ in range(max_pages):
            if _cancelled():
                return out
            if run_id is not None:
                touch_backtest_progress_runtime(run_id)
            params = {"iss.meta": "off", "date": day.isoformat(), "start": start}
            page_started = datetime.now(timezone.utc)
            attempts = 3
            resp: Optional[httpx.Response] = None
            for attempt in range(1, attempts + 1):
                try:
                    async with moex_http_acquire():
                        resp = await client.get(url, params=params)
                    break
                except _MOEX_RETRYABLE_HTTP_ERRORS as e:
                    if attempt >= attempts:
                        fin = datetime.now(timezone.utc)
                        if run_id is not None:
                            log_moex_external_api_isolated(
                                user_id=user_id,
                                run_id=run_id,
                                endpoint=url,
                                request_data={"params": dict(params), "board": board},
                                response_status=None,
                                response_data={"attempts": attempts, "error_type": "network"},
                                started_at=page_started,
                                finished_at=fin,
                                success=False,
                                error_message=str(e)[:2000]
                            )
                        history_backtest_moex_log(
                            "[history-backtest] MOEX iss GET failed day=%s start=%s err=%s",
                            day.isoformat(),
                            start,
                            str(e)
                        )
                        return None
                    await asyncio.sleep(0.6 * attempt)
                except Exception as ex:
                    fin = datetime.now(timezone.utc)
                    if run_id is not None:
                        log_moex_external_api_isolated(
                            user_id=user_id,
                            run_id=run_id,
                            endpoint=url,
                            request_data={"params": dict(params), "board": board},
                            response_status=None,
                            response_data={"error_type": "unexpected"},
                            started_at=page_started,
                            finished_at=fin,
                            success=False,
                            error_message=str(ex)[:2000]
                        )
                    history_backtest_moex_log(
                        "[history-backtest] MOEX iss GET unexpected error day=%s start=%s err=%s",
                        day.isoformat(),
                        start,
                        str(ex)
                    )
                    return None
            if resp is None or resp.status_code != 200:
                fin = datetime.now(timezone.utc)
                if run_id is not None:
                    log_moex_external_api_isolated(
                        user_id=user_id,
                        run_id=run_id,
                        endpoint=url,
                        request_data={"params": dict(params), "board": board},
                        response_status=resp.status_code if resp else None,
                        response_data={"error": "no_response" if resp is None else "non_200"},
                        started_at=page_started,
                        finished_at=fin,
                        success=False,
                        error_message=None if resp is None else f"HTTP {resp.status_code}"
                    )
                return None

            payload = resp.json() if resp.content else {}
            block = payload.get("history") or {}
            cols = block.get("columns") or []
            rows = block.get("data") or []
            fin = datetime.now(timezone.utc)
            if run_id is not None:
                log_moex_external_api_isolated(
                    user_id=user_id,
                    run_id=run_id,
                    endpoint=url,
                    request_data={"params": dict(params), "board": board},
                    response_status=resp.status_code,
                    response_data={
                        "history_columns": len(cols),
                        "history_rows_page": len(rows),
                        "empty_page": len(rows) == 0,
                    },
                    started_at=page_started,
                    finished_at=fin,
                    success=(resp.status_code == 200),
                    error_message=None
                )
            if not rows:
                break

            sig = f"{start}:{len(rows)}:{rows[0][0] if rows and rows[0] else ''}:{rows[-1][0] if rows and rows[-1] else ''}"
            if sig in seen_signatures:
                break
            seen_signatures.add(sig)

            idx = {c: i for i, c in enumerate(cols)}
            for r in rows:
                secid_i = idx.get("SECID")
                if secid_i is None or secid_i >= len(r):
                    continue

                def g(name: str, _r=r, _idx=idx):
                    i = _idx.get(name)
                    return _r[i] if i is not None and i < len(_r) else None

                def g_first(*names: str):
                    for nm in names:
                        v = g(nm)
                        if v is not None:
                            return v
                    return None

                close_price = _safe_float_opt(g_first("CLOSE", "LEGALCLOSEPRICE"))
                trend_pct = _safe_float_opt(g("TRENDCLSPR"))
                prev_price_v: Optional[float] = None
                if close_price is not None and close_price > 0 and trend_pct is not None:
                    try:
                        denom = 1.0 + (trend_pct / 100.0)
                        if abs(denom) > 1e-12:
                            prev_price_v = float(close_price / denom)
                    except (ArithmeticError, TypeError, ValueError):
                        prev_price_v = None
                if prev_price_v is None or prev_price_v <= 0:
                    prev_price_v = close_price
                bid_price = _safe_float_opt(g_first("BID", "BIDPRICE"))
                ask_price = _safe_float_opt(g_first("OFFER", "ASK", "ASKPRICE"))
                spread_val = _safe_float_opt(g_first("SPREAD"))
                if spread_val is None and bid_price is not None and ask_price is not None:
                    spread_val = ask_price - bid_price
                out.append({
                    "ticker": str(g("SECID") or "").upper(),
                    "board_id": g("BOARDID"),
                    "last_price": close_price,
                    "close_price": close_price,
                    "open_price": _safe_float_opt(g("OPEN")),
                    "high_price": _safe_float_opt(g("HIGH")),
                    "low_price": _safe_float_opt(g("LOW")),
                    "prev_price": prev_price_v,
                    "value_today": _safe_float_opt(g("VALUE")),
                    "volume_lots": _safe_float_opt(g("VOLUME")),
                    "num_trades": _safe_int_opt(g("NUMTRADES")),
                    "short_name": g("SHORTNAME"),
                    "security_status": str(g_first("STATUS", "SECSTATUS", "SECURITYSTATUS") or "A"),
                    "trading_status": str(g_first("TRADINGSTATUS", "TRADING_STATUS") or "T"),
                    "issue_size": _safe_float_opt(g_first("ISSUE_SIZE", "ISSUESIZE")),
                    "min_step": _safe_float_opt(g_first("MINSTEP", "MIN_STEP")),
                    "bid": bid_price,
                    "ask": ask_price,
                    "spread": spread_val,
                    "isin": None,
                    "lot_size": None,
                    "prev_legal_close_price": None,
                    "raw_payload": {k: g(k) for k in cols},
                })

            if len(rows) < page_size:
                break
            start += page_size

    if out:
        try:
            listing_ref = await load_listing_board_row_map(listing_date=day, board=board)
        except Exception as ex:
            logger.warning("securities listing archive merge skipped day=%s: %s", day.isoformat(), ex)
            listing_ref = {}
        if listing_ref:
            for row in out:
                tk = str(row.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                meta = listing_ref.get(tk)
                if not meta:
                    continue
                if meta.get("issue_size"):
                    row["issue_size"] = float(meta["issue_size"])
                if meta.get("lot_size") is not None:
                    row["lot_size"] = int(meta["lot_size"])
                if meta.get("isin"):
                    row["isin"] = meta["isin"]
                if meta.get("prev_legal_close_price") is not None:
                    row["prev_legal_close_price"] = float(meta["prev_legal_close_price"])
        sizes = await fetch_board_issuesize_map(board=board)
        if sizes:
            for row in out:
                tk = str(row.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                ex_sz = row.get("issue_size")
                if ex_sz is None or (isinstance(ex_sz, (int, float)) and float(ex_sz) <= 0):
                    sz = sizes.get(tk)
                    if sz is not None and sz > 0:
                        row["issue_size"] = float(sz)
    logger.info("moex history loaded day=%s board=%s rows=%s", day.isoformat(), board, len(out))
    return out


async def ensure_daily_snapshot_history(
    db: Session,
    *,
    day: date,
    board: str = "TQBR",
    user_id: Optional[int] = None,
    run_id: Optional[int] = None
) -> Optional[int]:
    """DB-first snapshot; MOEX ISS только при cache miss."""
    from app.modules.robots.service import is_history_backtest_cancelled

    schema = settings.DB_SCHEMA
    min_rows_for_reuse = 150 if str(board).upper() == "TQBR" else 1
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end_exclusive = day_start + timedelta(days=1)

    existing = db.execute(
        text(
            f"""
            SELECT h.id,
                   (SELECT COUNT(*) FROM market_snapshot_data_history d WHERE d.snapshot_id = h.id) AS data_rows
            FROM market_snapshot_history h
            WHERE h.board=:board
              AND h.status='SUCCESS'
              AND h.snapshot_time >= :day_start
              AND h.snapshot_time < :day_end
            ORDER BY h.snapshot_time ASC
            LIMIT 1
            """
        ),
        {"board": board, "day_start": day_start, "day_end": day_end_exclusive}
    ).first()
    existing_id = int(existing[0]) if existing else None
    existing_rows = int(existing[1] or 0) if existing else 0

    if run_id is not None and is_history_backtest_cancelled(run_id):
        return None
    if existing_id and existing_rows >= min_rows_for_reuse:
        if run_id is not None:
            from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

            touch_backtest_progress_runtime(run_id)
        logger.info(
            "history snapshot cache hit day=%s board=%s snapshot_id=%s data_rows=%s",
            day.isoformat(),
            board,
            existing_id,
            existing_rows
        )
        history_backtest_moex_log(
            "skip fetch (cache): day=%s board=%s snapshot_id=%s data_rows=%s",
            day.isoformat(),
            board,
            existing_id,
            existing_rows
        )
        return existing_id

    if existing_id:
        db.execute(
            text(f"DELETE FROM market_snapshot_data_history WHERE snapshot_id=:sid"),
            {"sid": existing_id}
        )
        db.execute(
            text(f"DELETE FROM market_snapshot_history WHERE id=:sid"),
            {"sid": existing_id}
        )
        db.commit()

    rows = await fetch_moex_history_snapshot_day(
        day=day, board=board, user_id=user_id, run_id=run_id
    )
    if run_id is not None:
        from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

        touch_backtest_progress_runtime(run_id)
    if rows is None:
        logger.warning("history snapshot MOEX fetch failed day=%s board=%s", day.isoformat(), board)
        return None
    if not rows:
        logger.warning("history snapshot MOEX empty day=%s board=%s", day.isoformat(), board)
        return None

    def _next_pk(table_name: str) -> int:
        seq_name = db.execute(
            text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
            {"tbl": f"{table_name}"}
        ).scalar()
        if seq_name:
            try:
                return int(db.execute(text("SELECT nextval(:seq)"), {"seq": seq_name}).scalar())
            except Exception:
                pass
        mx = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")).scalar()
        return int(mx or 0) + 1

    snapshot_id = _next_pk("market_snapshot_history")
    now_utc = datetime.now(timezone.utc)
    db.execute(
        text(
            f"""
            INSERT INTO market_snapshot_history
            (id, snapshot_time, board, status, is_manual, ttl_minutes, created_at)
            VALUES (:id, :snapshot_time, :board, 'SUCCESS', TRUE, 0, :created_at)
            """
        ),
        {"id": snapshot_id, "snapshot_time": day_start, "board": board, "created_at": now_utc}
    )

    next_data_id = _next_pk("market_snapshot_data_history")
    for i, r in enumerate(rows):
        rid = next_data_id + i
        raw = dict(r.get("raw_payload") or {})
        db.execute(
            text(
                f"""
                INSERT INTO market_snapshot_data_history
                (id, snapshot_id, ticker, last_price, open_price, prev_price, volume_today, value_today, volume_lots,
                 bid, ask, spread, security_status, trading_status, num_trades, min_step, issue_size, board_id,
                 short_name, low_price, high_price, close_price, value, isin, lot_size, prev_legal_close_price,
                 securities_payload, marketdata_payload)
                VALUES
                (:id, :snapshot_id, :ticker, :last_price, :open_price, :prev_price, :volume_today, :value_today, :volume_lots,
                 :bid, :ask, :spread, :security_status, :trading_status, :num_trades, :min_step, :issue_size, :board_id,
                 :short_name, :low_price, :high_price, :close_price, :value, :isin, :lot_size, :prev_legal_close_price,
                 CAST(:securities_payload AS jsonb), CAST(:marketdata_payload AS jsonb))
                """
            ),
            {
                "id": rid,
                "snapshot_id": snapshot_id,
                "ticker": str(r.get("ticker") or "").upper(),
                "last_price": r.get("last_price"),
                "open_price": r.get("open_price"),
                "prev_price": r.get("prev_price"),
                "volume_today": r.get("volume_lots"),
                "value_today": r.get("value_today"),
                "volume_lots": r.get("volume_lots"),
                "bid": r.get("bid"),
                "ask": r.get("ask"),
                "spread": r.get("spread"),
                "security_status": r.get("security_status"),
                "trading_status": r.get("trading_status"),
                "num_trades": r.get("num_trades"),
                "min_step": r.get("min_step"),
                "issue_size": r.get("issue_size"),
                "board_id": r.get("board_id"),
                "short_name": r.get("short_name"),
                "low_price": r.get("low_price"),
                "high_price": r.get("high_price"),
                "close_price": r.get("close_price") if r.get("close_price") is not None else r.get("last_price"),
                "value": r.get("value_today"),
                "isin": r.get("isin"),
                "lot_size": r.get("lot_size"),
                "prev_legal_close_price": r.get("prev_legal_close_price"),
                "securities_payload": json.dumps(raw, ensure_ascii=False),
                "marketdata_payload": json.dumps(raw, ensure_ascii=False),
            }
        )
    db.commit()
    return snapshot_id


__all__ = [
    "ensure_daily_snapshot_history",
    "fetch_moex_history_snapshot_day",
    "fetch_board_issuesize_map",
]
