"""
RuntimeRecorder — единое журналирование решений и сделок в БД.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §10.

Две реализации:
- `BacktestRecorder` — пишет в `{DB_SCHEMA}.backtest_*` таблицы
  (decisions, signals, orders, portfolio_snapshots, risk_events).
- `LiveRecorder` — пишет в `{DB_SCHEMA}.robot_*` таблицы
  (decisions, signals, trades, order_events, risk_events).

Базовый класс `MemoryRecorder` (no-op + сохранение в памяти) — для тестов и
случая, когда БД недоступна.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingRecorder [1]
#/// Исходный модуль `backend/app/modules/robots/trading/recorder.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.robots.trading.contracts import (
    Fill,
    Order,
    Position,
    Signal
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Базовый интерфейс
# ---------------------------------------------------------------------------

class RuntimeRecorder(ABC):
    """Единый интерфейс журналирования.

    Все методы async, чтобы было можно встроить в любой движок без блокировок.
    Реализации могут писать пачками — это деталь конкретного класса.
    """

    @abstractmethod
    async def record_universe(
        self,
        trade_date: date,
        accepted: List[str],
        rejected: List[Tuple[str, str]],
        *,
        source: str = "pipeline"
    ) -> None: ...

    @abstractmethod
    async def record_signal(self, signal: Signal) -> None: ...

    @abstractmethod
    async def record_risk_reject(self, signal: Signal, reason: str) -> None: ...

    @abstractmethod
    async def record_order(self, order: Order) -> None: ...

    @abstractmethod
    async def record_fill(self, fill: Fill) -> None: ...

    @abstractmethod
    async def record_position_snapshot(
        self,
        ts: datetime,
        positions: List[Position],
        cash: float,
        equity: float
    ) -> None: ...

    @abstractmethod
    async def record_daily_pnl(
        self,
        trade_date: date,
        pnl: float,
        return_pct: float
    ) -> None: ...


# ---------------------------------------------------------------------------
# MemoryRecorder — для тестов
# ---------------------------------------------------------------------------

@dataclass
class MemoryRecorder(RuntimeRecorder):
    universe: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    risk_rejects: List[Tuple[Signal, str]] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    daily_pnl: List[Dict[str, Any]] = field(default_factory=list)

    async def record_universe(self, trade_date, accepted, rejected, *, source="pipeline"):
        self.universe.append({"date": trade_date, "accepted": list(accepted),
                              "rejected": list(rejected), "source": source})

    async def record_signal(self, signal):
        self.signals.append(signal)

    async def record_risk_reject(self, signal, reason):
        self.risk_rejects.append((signal, reason))

    async def record_order(self, order):
        self.orders.append(order)

    async def record_fill(self, fill):
        self.fills.append(fill)

    async def record_position_snapshot(self, ts, positions, cash, equity):
        self.snapshots.append({"ts": ts, "positions": list(positions),
                               "cash": cash, "equity": equity})

    async def record_daily_pnl(self, trade_date, pnl, return_pct):
        self.daily_pnl.append({"date": trade_date, "pnl": pnl, "return_pct": return_pct})


# ---------------------------------------------------------------------------
# BacktestRecorder — пишет в {DB_SCHEMA}.backtest_*
# ---------------------------------------------------------------------------

class BacktestRecorder(RuntimeRecorder):
    """Recorder, пишущий в схему приложения (`{DB_SCHEMA}.backtest_*`)."""

    def __init__(self, db: Session, *, run_id: int, schema: str):
        self.db = db
        self.run_id = int(run_id)
        self.schema = schema

    async def record_universe(self, trade_date, accepted, rejected, *, source="pipeline"):
        rows = []
        for t in accepted:
            rows.append({"ticker": t.upper(), "result": "success", "reason": None})
        for t, reason in rejected:
            rows.append({"ticker": t.upper(), "result": "unsuccess", "reason": reason})
        if not rows:
            return
        try:
            for r in rows:
                self.db.execute(
                    text(f"""
                        INSERT INTO backtest_decisions
                            (run_id, trade_date, ticker, source, result, reason, payload)
                        VALUES (:run_id, :trade_date, :ticker, :source, :result, :reason, :payload)
                    """),
                    {
                        "run_id": self.run_id,
                        "trade_date": trade_date,
                        "ticker": r["ticker"],
                        "source": source.upper(),
                        "result": r["result"],
                        "reason": r["reason"],
                        "payload": json.dumps({}),
                    }
                )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_universe failed: %s", e)
            self.db.rollback()

    async def record_signal(self, signal):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO backtest_signals
                        (run_id, signal_time, figi, signal_type, price, was_executed, payload)
                    VALUES (:run_id, :ts, :figi, :stype, :price, :exec, :payload)
                """),
                {
                    "run_id": self.run_id,
                    "ts": signal.created_at,
                    "figi": signal.figi or signal.secid,
                    "stype": signal.side.lower(),
                    "price": signal.target_price or signal.price_at_signal,
                    "exec": 0,
                    "payload": json.dumps({"reason": signal.reason, "rule": signal.rule,
                                            "strategy": signal.strategy, **signal.meta}),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_signal failed: %s", e)
            self.db.rollback()

    async def record_risk_reject(self, signal, reason):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO backtest_risk_events
                        (run_id, ts, secid, figi, signal_id, reason_code, payload)
                    VALUES (:run_id, :ts, :secid, :figi, :sid, :reason, :payload)
                """),
                {
                    "run_id": self.run_id,
                    "ts": datetime.now(timezone.utc),
                    "secid": signal.secid,
                    "figi": signal.figi,
                    "sid": str(signal.signal_id),
                    "reason": reason,
                    "payload": json.dumps({"signal_meta": signal.meta}),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_risk_reject failed: %s", e)
            self.db.rollback()

    async def record_order(self, order):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO backtest_orders
                        (run_id, signal_time, figi, side, status, quantity, requested_price, executed_price,
                         slippage_pct, commission, tax, pnl_net, payload)
                    VALUES (:run_id, :ts, :figi, :side, :status, :qty, :rp, :ep, 0, 0, 0, NULL, :payload)
                """),
                {
                    "run_id": self.run_id,
                    "ts": order.created_at,
                    "figi": order.figi or order.secid,
                    "side": order.side.lower(),
                    "status": order.status.lower(),
                    "qty": int(order.quantity),
                    "rp": order.price,
                    "ep": order.price,
                    "payload": json.dumps({"signal_id": str(order.signal_id) if order.signal_id else None,
                                            "order_id": str(order.order_id), **order.meta}),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_order failed: %s", e)
            self.db.rollback()

    async def record_fill(self, fill):
        try:
            self.db.execute(
                text(f"""
                    UPDATE backtest_orders
                    SET status = 'filled', executed_price = :px, commission = :comm,
                        slippage_pct = :sl, payload = COALESCE(payload, '{{}}'::jsonb) || :patch::jsonb
                    WHERE payload->>'order_id' = :oid
                """),
                {
                    "px": float(fill.fill_price),
                    "comm": float(fill.commission),
                    "sl": float(fill.slippage),
                    "patch": json.dumps({"fill_ts": fill.ts.isoformat() if fill.ts else None}),
                    "oid": str(fill.order_id),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_fill failed: %s", e)
            self.db.rollback()

    async def record_position_snapshot(self, ts, positions, cash, equity):
        try:
            pl = [
                {
                    "secid": p.secid, "figi": p.figi, "qty": int(p.quantity),
                    "avg_entry": float(p.avg_entry_price), "price": float(p.current_price),
                }
                for p in positions
            ]
            self.db.execute(
                text(f"""
                    INSERT INTO backtest_portfolio_snapshots
                        (run_id, snapshot_time, cash_balance, equity, positions_payload)
                    VALUES (:run_id, :ts, :cash, :eq, :payload)
                """),
                {
                    "run_id": self.run_id,
                    "ts": ts,
                    "cash": float(cash),
                    "eq": float(equity),
                    "payload": json.dumps({"positions": pl}),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_position_snapshot failed: %s", e)
            self.db.rollback()

    async def record_daily_pnl(self, trade_date, pnl, return_pct):
        # Дневной P&L уже считается из equity_curve в metrics; отдельной таблицы не
        # требуем, но логируем как payload в `backtest_runs.metrics_summary`.
        try:
            self.db.execute(
                text(f"""
                    UPDATE backtest_runs
                    SET metrics_summary = COALESCE(metrics_summary, '{{}}'::jsonb) ||
                        jsonb_build_object('daily_pnl_' || :d, jsonb_build_object('pnl', :pnl, 'return_pct', :rp))
                    WHERE id = :run_id
                """),
                {
                    "run_id": self.run_id,
                    "d": trade_date.isoformat(),
                    "pnl": float(pnl),
                    "rp": float(return_pct),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("BacktestRecorder.record_daily_pnl failed: %s", e)
            self.db.rollback()


# ---------------------------------------------------------------------------
# LiveRecorder — пишет в {DB_SCHEMA}.robot_*
# ---------------------------------------------------------------------------

class LiveRecorder(RuntimeRecorder):
    """Recorder, пишущий в таблицы реального робота."""

    def __init__(
        self,
        db: Session,
        *,
        robot_id: int,
        schema: str,
        execution_log_id: Optional[int] = None,
        cycle_id: Optional[int] = None
    ):
        self.db = db
        self.robot_id = int(robot_id)
        self.schema = schema
        self.execution_log_id = execution_log_id
        self.cycle_id = cycle_id

    async def record_universe(self, trade_date, accepted, rejected, *, source="pipeline"):
        try:
            for t in accepted:
                self.db.execute(
                    text(f"""
                        INSERT INTO robot_decisions
                            (robot_id, execution_log_id, cycle_id, figi, stage, decision_type, decision, reason_code, payload)
                        VALUES (:robot_id, :elog, :cycle, :figi, 'universe', 'pipeline_filter', 'accepted', NULL, :payload)
                    """),
                    {
                        "robot_id": self.robot_id, "elog": self.execution_log_id, "cycle": self.cycle_id,
                        "figi": t.upper(),
                        "payload": json.dumps({"source": source}),
                    }
                )
            for t, reason in rejected:
                self.db.execute(
                    text(f"""
                        INSERT INTO robot_decisions
                            (robot_id, execution_log_id, cycle_id, figi, stage, decision_type, decision, reason_code, payload)
                        VALUES (:robot_id, :elog, :cycle, :figi, 'universe', 'pipeline_filter', 'rejected', :reason, :payload)
                    """),
                    {
                        "robot_id": self.robot_id, "elog": self.execution_log_id, "cycle": self.cycle_id,
                        "figi": t.upper(),
                        "reason": reason,
                        "payload": json.dumps({"source": source}),
                    }
                )
            self.db.commit()
        except Exception as e:
            logger.warning("LiveRecorder.record_universe failed: %s", e)
            self.db.rollback()

    async def record_signal(self, signal):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO robot_signals
                        (robot_id, figi, ticker, signal_type, signal_strength, indicators, price_at_signal, was_executed)
                    VALUES (:robot_id, :figi, :ticker, :stype, :strength, :ind, :px, 0)
                """),
                {
                    "robot_id": self.robot_id,
                    "figi": signal.figi or signal.secid,
                    "ticker": signal.secid,
                    "stype": signal.side.lower(),
                    "strength": int(signal.confidence * 100) if signal.confidence is not None else None,
                    "ind": json.dumps({"reason": signal.reason, "rule": signal.rule, **signal.meta}),
                    "px": signal.price_at_signal or signal.target_price,
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("LiveRecorder.record_signal failed: %s", e)
            self.db.rollback()

    async def record_risk_reject(self, signal, reason):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO robot_risk_events
                        (robot_id, ts, secid, figi, signal_id, reason_code, payload)
                    VALUES (:robot_id, :ts, :secid, :figi, :sid, :reason, :payload)
                """),
                {
                    "robot_id": self.robot_id,
                    "ts": datetime.now(timezone.utc),
                    "secid": signal.secid,
                    "figi": signal.figi,
                    "sid": str(signal.signal_id),
                    "reason": reason,
                    "payload": json.dumps({"signal_meta": signal.meta}),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("LiveRecorder.record_risk_reject failed: %s", e)
            self.db.rollback()

    async def record_order(self, order):
        # В live `robot_trades` запись делается через TradePersistenceMixin при
        # фактическом fill; пока — просто событие в `robot_order_events`.
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO robot_order_events
                        (robot_id, order_id, status, event_type, payload)
                    VALUES (:robot_id, :oid, :status, :etype, :payload)
                """),
                {
                    "robot_id": self.robot_id,
                    "oid": order.broker_order_id or str(order.order_id),
                    "status": order.status,
                    "etype": "submitted",
                    "payload": json.dumps({
                        "figi": order.figi, "side": order.side, "qty": order.quantity,
                        "price": order.price, "type": order.type,
                    }),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("LiveRecorder.record_order failed: %s", e)
            self.db.rollback()

    async def record_fill(self, fill):
        try:
            self.db.execute(
                text(f"""
                    INSERT INTO robot_order_events
                        (robot_id, order_id, status, event_type, payload)
                    VALUES (:robot_id, :oid, 'FILLED', 'fill', :payload)
                """),
                {
                    "robot_id": self.robot_id,
                    "oid": str(fill.order_id),
                    "payload": json.dumps({
                        "fill_price": fill.fill_price, "quantity": fill.quantity,
                        "commission": fill.commission, "ts": fill.ts.isoformat() if fill.ts else None,
                    }),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning("LiveRecorder.record_fill failed: %s", e)
            self.db.rollback()

    async def record_position_snapshot(self, ts, positions, cash, equity):
        # Для live портфельные снимки пишет отдельный механизм (`portfolio_updater`),
        # здесь — no-op.
        return

    async def record_daily_pnl(self, trade_date, pnl, return_pct):
        return


__all__ = [
    "RuntimeRecorder",
    "MemoryRecorder",
    "BacktestRecorder",
    "LiveRecorder",
]
