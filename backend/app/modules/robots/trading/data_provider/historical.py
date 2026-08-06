"""
HistoricalDataProvider — DataProvider для бэктеста.

Читает данные из:
- `{DB_SCHEMA}.shared_market_candles` через `market_data_v1.repository.list_candles`
  для дневных и внутридневных свечей;
- DMS / `market_snapshot_data` для дневных снапшотов (`get_daily_summary`);
- `{DB_SCHEMA}.tqbr_securities` для `list_universe`.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §4.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingDataProviderHistorical [1]
#/// Исходный модуль `backend/app/modules/robots/trading/data_provider/historical.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.market_data_v1 import repository as md_repo
from app.modules.robots.trading.contracts import Candle, MarketSnapshot, SnapshotRow
from app.modules.robots.trading.data_provider.base import DataProvider


class HistoricalDataProvider(DataProvider):
    """Реализация DataProvider поверх shared_market_candles + DMS snapshots.

    Конструктор принимает SQLAlchemy `Session` — провайдер не открывает соединение
    сам, чтобы оркестратор контролировал транзакцию.
    """

    def __init__(self, db: Session, *, board: str = "TQBR"):
        self.db = db
        self.board = board.upper()

    # ---------------------- universe ----------------------

    async def list_universe(self, trade_date: date) -> List[str]:
        from app.modules.robots.moex_securities_updater import queries as moex_q

        sql, params = moex_q.build_equity_universe_query(board=self.board, active_only=True)
        rows = self.db.execute(text(sql), params).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]

    # ---------------------- snapshot --------------------

    async def get_daily_summary(self, secids: List[str], trade_date: date) -> MarketSnapshot:
        schema = settings.DB_SCHEMA
        if not secids:
            return MarketSnapshot(as_of=datetime.combine(trade_date, time(10, 0), tzinfo=timezone.utc),
                                  trade_date=trade_date, board=self.board, rows={})
        # Ищем самый свежий снапшот на/до trade_date с указанным board.
        snap_id_row = self.db.execute(
            text(f"""
                SELECT id, snapshot_time
                FROM market_snapshot_history
                WHERE board = :board
                  AND status = 'SUCCESS'
                  AND snapshot_time >= :day_start
                  AND snapshot_time < :day_end
                ORDER BY snapshot_time ASC
                LIMIT 1
            """),
            {
                "board": self.board,
                "day_start": datetime.combine(trade_date, time.min, tzinfo=timezone.utc),
                "day_end": datetime.combine(trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc),
            }
        ).fetchone()
        rows_map: Dict[str, SnapshotRow] = {}
        as_of: datetime = datetime.combine(trade_date, time(10, 0), tzinfo=timezone.utc)
        if snap_id_row:
            snap_id = int(snap_id_row[0])
            as_of = snap_id_row[1] or as_of
            data_rows = self.db.execute(
                text(f"""
                    SELECT ticker, open_price, prev_price, last_price, high_price, low_price,
                           value_today, volume_lots, num_trades, issue_size, bid, ask,
                           security_status, trading_status, atr_percent
                    FROM market_snapshot_data_history
                    WHERE snapshot_id = :sid
                      AND UPPER(ticker) = ANY(:tickers)
                """),
                {"sid": snap_id, "tickers": [s.upper() for s in secids]}
            ).fetchall()
            for r in data_rows:
                t = str(r[0] or "").upper()
                if not t:
                    continue
                rows_map[t] = SnapshotRow(
                    secid=t,
                    open=_safe_float(r[1]),
                    prev_close=_safe_float(r[2]),
                    last_price=_safe_float(r[3]),
                    high=_safe_float(r[4]),
                    low=_safe_float(r[5]),
                    volume_rub=_safe_float(r[6]),
                    volume_lots=_safe_float(r[7]),
                    num_trades=int(r[8]) if r[8] is not None else None,
                    issue_size=_safe_float(r[9]),
                    bid=_safe_float(r[10]),
                    ask=_safe_float(r[11]),
                    security_status=(str(r[12]) if r[12] is not None else None),
                    trading_status=(str(r[13]) if r[13] is not None else None),
                    atr_pct=_safe_float(r[14])
                )
        return MarketSnapshot(as_of=as_of, trade_date=trade_date, board=self.board, rows=rows_map)

    # ---------------------- candles ----------------------

    async def get_daily_candles(self, secid: str, from_d: date, to_d: date) -> List[Candle]:
        from_ts = datetime.combine(from_d, time(0, 0), tzinfo=timezone.utc)
        to_ts = datetime.combine(to_d, time(23, 59, 59), tzinfo=timezone.utc)
        rows = md_repo.list_candles(
            self.db,
            tickers=[secid],
            board=self.board,
            interval="D1",
            from_ts=from_ts,
            to_ts=to_ts
        )
        return [Candle.from_moex_row(r, interval="D1", secid=secid.upper()) for r in rows]

    async def get_intraday_candles(self, secid: str, day: date, interval: str) -> List[Candle]:
        norm = _normalize_interval(interval)
        from_ts = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
        to_ts = datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
        rows = md_repo.list_candles(
            self.db,
            tickers=[secid],
            board=self.board,
            interval=norm,
            from_ts=from_ts,
            to_ts=to_ts
        )
        return [Candle.from_moex_row(r, interval=norm, secid=secid.upper()) for r in rows]


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_INTERVAL_MAP = {
    "CANDLE_INTERVAL_5_MIN": "M5",
    "CANDLE_INTERVAL_10_MIN": "M10",
    "CANDLE_INTERVAL_15_MIN": "M15",
    "CANDLE_INTERVAL_30_MIN": "M30",
    "CANDLE_INTERVAL_HOUR": "H1",
    "CANDLE_INTERVAL_DAY": "D1",
    "M5": "M5",
    "M10": "M10",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "D1": "D1",
}


def _normalize_interval(interval: str) -> str:
    return _INTERVAL_MAP.get(str(interval), str(interval))


__all__ = ["HistoricalDataProvider"]
