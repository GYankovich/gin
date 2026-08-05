"""Per-day crypto universe scoring for history backtest."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.crypto_universe import (
    ScreeningRow,
    apply_basic_filters,
    apply_derivative_filters,
    apply_volatility_filters,
    resolve_crypto_universe_filters,
)
from app.modules.robots.trading.backtest.universe_reject_report import screening_row_to_reject_decision
from app.modules.robots.trading.pipeline.historical_liquidity import (
    crypto_metrics_as_of_date,
    list_bybit_symbols_from_cache,
    volume_lookback_days,
)
from app.modules.robots.trading.pipeline.bybit_symbol_filter import is_dated_bybit_contract
from app.core.db_retry import run_db_read_with_retry
from app.modules.robots.trading.pipeline.universe_scoring import (
    SCORING_PROGRESS_SUBSTEPS,
    _scoring_heartbeat,
)
from app.modules.robots.trading.backtest.backtest_narrative_log import (
    backtest_narrative,
    format_symbol_list,
    format_trade_date,
    narrative_result,
    narrative_section,
    narrative_step,
    narrative_sub,
)
from app.modules.robots.universe import resolve_crypto_symbols

ProgressFlush = Callable[..., None]


@dataclass
class CryptoUniverseScoringResult:
    allowed_figis_by_date: Dict[str, List[str]] = field(default_factory=dict)
    decisions_rows: List[Dict[str, Any]] = field(default_factory=list)
    processed_days: int = 0
    selected_tickers: List[str] = field(default_factory=list)
    cancelled: bool = False
    scanned_tickers: int = 0


def _load_cached_symbols_by_date(
    db: Session,
    robot_id: Optional[int],
    trade_dates: List[date],
) -> Dict[str, List[str]]:
    if robot_id is None or not trade_dates:
        return {}
    rows = db.execute(
        text(
            f"""
            SELECT trade_date, symbol
            FROM crypto_universe_daily
            WHERE robot_id = :rid
              AND trade_date >= :d_from
              AND trade_date <= :d_to
              AND LOWER(COALESCE(filter_result, '')) IN ('accepted', 'accept')
            ORDER BY trade_date, symbol
            """
        ),
        {
            "rid": int(robot_id),
            "d_from": trade_dates[0],
            "d_to": trade_dates[-1],
        },
    ).fetchall()
    out: Dict[str, List[str]] = {}
    for row in rows:
        d_val = row[0]
        d_key = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        sym = str(row[1] or "").strip().upper()
        if sym:
            out.setdefault(d_key, []).append(sym)
    for key in out:
        out[key] = sorted(set(out[key]))
    return out


def _resolve_candidate_pool(
    config: Dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]],
) -> Optional[Set[str]]:
    explicit = resolve_crypto_symbols(config)
    if explicit:
        return set(explicit)
    if allowed_tickers_whitelist:
        return set(allowed_tickers_whitelist)
    return None


def _apply_candidate_pool(symbols: List[str], candidate_pool: Optional[Set[str]]) -> List[str]:
    if not candidate_pool:
        return sorted(set(symbols))
    return sorted(s for s in symbols if s in candidate_pool)


def _score_symbols_for_trade_date(
    db: Session,
    *,
    trade_date: date,
    config: Dict[str, Any],
    candidate_pool: Optional[Set[str]],
) -> tuple[List[str], List[Dict[str, Any]], int]:
    """
    Point-in-time crypto screening from candles_cache + historical ByBit tables.
    """
    filters = resolve_crypto_universe_filters(config)
    lookback = max(filters.lookback_days, volume_lookback_days(config, default=filters.lookback_days))
    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    category = str(bybit.get("instrument_category") or filters.category or "linear")
    pool = list(candidate_pool) if candidate_pool else list_bybit_symbols_from_cache(db)
    if not pool:
        return [], [], 0

    ticker_rows: List[Dict[str, Any]] = []
    for sym in pool:
        if is_dated_bybit_contract(sym):
            continue

        def _load_metrics(symbol: str = sym) -> Optional[Dict[str, Any]]:
            return crypto_metrics_as_of_date(
                db,
                symbol=symbol,
                trade_date=trade_date,
                lookback_days=lookback,
                instrument_category=category,
                funding_lookback_hours=filters.funding_lookback_hours,
                atr_period=filters.atr_period,
                include_derivatives=True,
            )

        metrics = run_db_read_with_retry(db, _load_metrics)
        if metrics:
            ticker_rows.append(metrics)

    accepted_rows: List[ScreeningRow] = []
    decisions: List[Dict[str, Any]] = []
    for metrics in ticker_rows:
        basic_ok, basic_rejected = apply_basic_filters([metrics], filters=filters)
        for row in basic_rejected:
            decisions.append(
                screening_row_to_reject_decision(
                    row,
                    trade_date=trade_date.isoformat(),
                    stage="crypto_universe",
                )
            )
        for row in basic_ok:
            row.avg_funding_rate = metrics.get("avg_funding_rate")
            row.open_interest_usd = metrics.get("open_interest_usd")
            row.lsr = metrics.get("lsr")
            row.rvol = metrics.get("rvol")
            row.atr_percent = metrics.get("atr_percent")
            if not apply_derivative_filters(row, filters=filters):
                decisions.append(
                    screening_row_to_reject_decision(
                        row,
                        trade_date=trade_date.isoformat(),
                        stage="crypto_universe",
                    )
                )
                continue
            if not apply_volatility_filters(row, filters=filters):
                decisions.append(
                    screening_row_to_reject_decision(
                        row,
                        trade_date=trade_date.isoformat(),
                        stage="crypto_universe",
                    )
                )
                continue
            accepted_rows.append(row)

    accepted_rows.sort(key=lambda x: x.score, reverse=True)
    capped = accepted_rows[: max(1, int(filters.limit))]
    symbols = _apply_candidate_pool([r.symbol for r in capped], candidate_pool)

    for row in capped:
        if row.symbol not in symbols:
            continue
        decisions.append(
            {
                "stage": "crypto_universe",
                "ticker": row.symbol,
                "result": "ACCEPT",
                "reason": "crypto_screening_pass",
                "turnover24h": row.turnover24h,
                "spreadPercent": row.spreadPercent,
                "dailyRangePercent": row.dailyRangePercent,
                "avg_funding_rate": row.avg_funding_rate,
                "open_interest_usd": row.open_interest_usd,
                "lsr": row.lsr,
                "rvol": row.rvol,
                "atr_percent": row.atr_percent,
                "source": "candles_cache",
                "trade_date": trade_date.isoformat(),
            }
        )
    return symbols, decisions, len(pool)


async def run_history_crypto_universe_scoring(
    *,
    db: Session,
    trade_dates: List[date],
    config: Dict[str, Any],
    user_id: int,
    robot_id: Optional[int],
    run_id: int,
    allowed_tickers_whitelist: Optional[Set[str]] = None,
    bybit_token_id: Optional[int] = None,
    is_cancelled: Callable[[], bool],
    flush_progress: Optional[ProgressFlush] = None,
) -> CryptoUniverseScoringResult:
    """Отбор crypto-символов по дням: crypto_universe_daily → candles_cache (per day)."""
    del user_id, bybit_token_id  # historical path does not use live API token
    out = CryptoUniverseScoringResult()
    td_total = len(trade_dates)
    if td_total == 0:
        return out

    cached_by_date = _load_cached_symbols_by_date(db, robot_id, trade_dates)
    candidate_pool = _resolve_candidate_pool(config, allowed_tickers_whitelist)
    filters = resolve_crypto_universe_filters(config)
    lookback = max(filters.lookback_days, volume_lookback_days(config, default=filters.lookback_days))

    narrative_section("Отбор торгуемых монет (crypto universe scoring)", run_id=run_id)

    async with _scoring_heartbeat(run_id):
        with backtest_narrative(run_id):
            for day_ord, d in enumerate(trade_dates):
                await asyncio.sleep(0)
                if is_cancelled():
                    out.cancelled = True
                    break

                rem_day = max(0, td_total - day_ord - 1)
                d_key = d.isoformat()

                def _flush(substep: int) -> None:
                    if flush_progress is None:
                        return
                    flush_progress(
                        day_ord * SCORING_PROGRESS_SUBSTEPS + substep,
                        current_trade_date=d,
                        trade_dates_remaining=rem_day,
                    )

                _flush(0)

                narrative_step(f"Скоринг торгуемых монет на {format_trade_date(d)}")
                symbols: List[str] = []
                if d_key in cached_by_date and cached_by_date[d_key]:
                    narrative_sub(
                        f"Источник: crypto_universe_daily (robot_id={robot_id}) — "
                        f"готовый список на дату"
                    )
                    symbols = _apply_candidate_pool(cached_by_date[d_key], candidate_pool)
                    narrative_result(
                        f"На {format_trade_date(d)} торгуются монеты: {format_symbol_list(symbols)}"
                    )
                    _flush(1)
                    _flush(2)
                    _flush(3)
                else:
                    pool_size = (
                        len(candidate_pool)
                        if candidate_pool
                        else len(list_bybit_symbols_from_cache(db))
                    )
                    narrative_sub(
                        f"Загрузка метрик из candles_cache и исторических таблиц ByBit "
                        f"(пул кандидатов: {pool_size}, lookback={lookback} дн.)"
                    )
                    symbols, day_decisions, scanned = _score_symbols_for_trade_date(
                        db,
                        trade_date=d,
                        config=config,
                        candidate_pool=candidate_pool,
                    )
                    out.scanned_tickers = max(out.scanned_tickers, scanned)
                    accepted_n = len(symbols)
                    rejected_n = sum(
                        1 for dr in day_decisions if str(dr.get("result") or "").upper() != "ACCEPT"
                    )
                    narrative_sub(
                        f"Применены фильтры crypto_universe: базовые, деривативные, волатильность; "
                        f"лимит топ-{filters.limit}"
                    )
                    narrative_result(
                        f"На {format_trade_date(d)} прошли отбор {accepted_n} из {scanned} монет "
                        f"(отклонено {rejected_n}): {format_symbol_list(symbols)}"
                    )
                    for row in day_decisions:
                        out.decisions_rows.append(row)
                    if not symbols and scanned == 0:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=(
                                f"Нет исторических D1-свечей ByBit для отбора на {d_key}. "
                                "Загрузите candles_cache или включите robot_id с crypto_universe_daily."
                            ),
                        )
                    _flush(1)
                    _flush(2)
                    _flush(3)

                for sym in symbols:
                    if any(
                        dr.get("ticker") == sym
                        and dr.get("trade_date") == d_key
                        and dr.get("result") == "ACCEPT"
                        for dr in out.decisions_rows
                    ):
                        continue
                    out.decisions_rows.append(
                        {
                            "trade_date": d_key,
                            "stage": "crypto_universe",
                            "ticker": sym,
                            "result": "ACCEPT",
                            "reason": "cached_daily" if d_key in cached_by_date else "crypto_screening_pass",
                        }
                    )

                out.allowed_figis_by_date[d_key] = symbols
                out.processed_days += 1
                _flush(4)

    out.selected_tickers = sorted(
        {sym for syms in out.allowed_figis_by_date.values() for sym in syms}
    )
    narrative_result(
        f"Итого за период: {out.processed_days} дн., уникальных монет {len(out.selected_tickers)} — "
        f"{format_symbol_list(out.selected_tickers)}",
        run_id=run_id,
    )
    return out
