"""DEPRECATED: см. docs/BRD-ARCH-03-unified-engine-architecture.md §11.

Этот модуль остаётся как обратно совместимый адаптер для текущего
`backtest/engine.py:run_backtest_simulation`. Новые места кода должны
использовать единый контур market-data через
`app.modules.robots.trading.data.get_market_data_facade()` (`MarketDataFacade.ensure_*`),
который читает те же снапшоты из
`market_snapshot_history` и `market_snapshot_data_history`.
"""
from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestDmsEmulator [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/dms_emulator.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import date, datetime, time, timezone, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings


class DmsEmulator:
    """History-only snapshot resolver for backtesting."""

    def __init__(self, db: Session, board: str = "TQBR"):
        self.db = db
        self.board = board

    def get_snapshot_id_for_date(self, trade_date: date, *, min_rows: int = 1) -> Optional[int]:
        day_start = datetime.combine(trade_date, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        row = self.db.execute(
            text(
                f"""
                SELECT h.id
                FROM market_snapshot_history h
                WHERE h.board=:board
                  AND h.status='SUCCESS'
                  AND h.snapshot_time >= :day_start
                  AND h.snapshot_time < :day_end
                  AND (
                      SELECT COUNT(*)
                      FROM market_snapshot_data_history d
                      WHERE d.snapshot_id=h.id
                  ) >= :min_rows
                ORDER BY h.snapshot_time ASC
                LIMIT 1
                """
            ),
            {"board": self.board, "day_start": day_start, "day_end": day_end, "min_rows": min_rows},
        ).first()
        if row:
            return int(row[0])
        prev = self.db.execute(
            text(
                f"""
                SELECT h.id
                FROM market_snapshot_history h
                WHERE h.board=:board
                  AND h.status='SUCCESS'
                  AND h.snapshot_time < :day_start
                ORDER BY h.snapshot_time DESC
                LIMIT 1
                """
            ),
            {"board": self.board, "day_start": day_start},
        ).first()
        return int(prev[0]) if prev else None

