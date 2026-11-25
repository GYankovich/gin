"""ORM models still used after Wave 3 (Dictionary + shared backtest_* tables).

Legacy Robot* tables were dropped in alembic 0091 — do not reintroduce them here.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsModels [1]

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)

from app.core.config import settings
from app.core.database import Base

SCHEMA = settings.DB_SCHEMA


class Dictionary(Base):
    __tablename__ = "dictionary"
    __table_args__ = (
        Index("ix_dictionary_table_column", "table_name", "column_name"),
        Index("ix_dictionary_num_value", "num_value"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    num_value = Column(Integer, nullable=True)
    string_value = Column(String(255), nullable=True)
    hide_from_ui = Column(Integer, nullable=False, default=0)

    usercre = Column(String(128), nullable=True)
    creation_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(String(128), nullable=True)
    modification_date = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("ix_backtest_runs_robot_created", "robot_id", "started_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Soft-bind to robots.id (FK to legacy robots dropped in 0062/0091).
    robot_id = Column(BigInteger, nullable=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    requested_from = Column(DateTime(timezone=True), nullable=False)
    requested_to = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)
    board = Column(String(20), nullable=False, default="TQBR")
    initial_capital = Column(Numeric(20, 4), nullable=False)
    config_snapshot = Column(JSON, nullable=False, default=dict)
    execution_model = Column(JSON, nullable=False, default=dict)
    metrics_summary = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)


class BacktestSignal(Base):
    __tablename__ = "backtest_signals"
    __table_args__ = (Index("ix_backtest_signals_run_id", "run_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    signal_time = Column(DateTime(timezone=True), nullable=True)
    figi = Column(String(20), nullable=False)
    signal_type = Column(String(20), nullable=False)
    price = Column(Numeric(20, 6), nullable=True)
    was_executed = Column(Integer, nullable=False, default=0)
    payload = Column(JSON, nullable=False, default=dict)


class BacktestOrder(Base):
    __tablename__ = "backtest_orders"
    __table_args__ = (Index("ix_backtest_orders_run_id", "run_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    signal_time = Column(DateTime(timezone=True), nullable=True)
    figi = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False)
    quantity = Column(Numeric(20, 4), nullable=False)
    requested_price = Column(Numeric(20, 6), nullable=True)
    executed_price = Column(Numeric(20, 6), nullable=True)
    slippage_pct = Column(Numeric(10, 6), nullable=False, default=0)
    commission = Column(Numeric(20, 6), nullable=True)
    tax = Column(Numeric(20, 6), nullable=True)
    pnl_net = Column(Numeric(20, 6), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)


class BacktestPortfolioSnapshot(Base):
    __tablename__ = "backtest_portfolio_snapshots"
    __table_args__ = (Index("ix_backtest_portfolio_run_id", "run_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    cash_balance = Column(Numeric(20, 4), nullable=False)
    equity = Column(Numeric(20, 4), nullable=False)
    positions_payload = Column(JSON, nullable=False, default=list)


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"
    __table_args__ = (Index("uq_backtest_metrics_run_id", "run_id", unique=True),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    total_return_percent = Column(Numeric(12, 6), nullable=True)
    max_drawdown_percent = Column(Numeric(12, 6), nullable=True)
    sharpe_ratio = Column(Numeric(12, 6), nullable=True)
    trades_total = Column(BigInteger, nullable=False, default=0)
    win_rate_percent = Column(Numeric(12, 6), nullable=True)
    avg_pnl_per_trade = Column(Numeric(20, 6), nullable=True)
    final_equity = Column(Numeric(20, 6), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)


class BacktestUniverseMembership(Base):
    __tablename__ = "backtest_universe_membership"
    __table_args__ = (
        Index("ix_backtest_universe_membership_run_date", "run_id", "trade_date"),
    )

    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    ticker = Column(String(32), primary_key=True)
    source = Column(String(64), nullable=True)
    filter_result = Column(String(32), nullable=True)
    reject_reason = Column(Text, nullable=True)


class BacktestExecutionEvent(Base):
    __tablename__ = "backtest_execution_events"
    __table_args__ = (
        Index("ix_backtest_execution_events_run_id", "run_id"),
        Index("ix_backtest_execution_events_run_cycle", "run_id", "cycle_id"),
        Index("ix_backtest_execution_events_run_intent", "run_id", "intent_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False)
    intent_id = Column(String(64), nullable=False)
    cycle_id = Column(String(64), nullable=True)
    ticker = Column(String(32), nullable=False)
    side = Column(String(10), nullable=True)
    kind = Column(String(32), nullable=True)
    status = Column(String(20), nullable=False)
    reason = Column(String(64), nullable=True)
    reject_reason = Column(String(64), nullable=True)
    quantity = Column(Numeric(20, 4), nullable=True)
    price = Column(Numeric(20, 8), nullable=True)
    trade_id = Column(BigInteger, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
