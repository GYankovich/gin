"""
ORM-модели портфельных данных (брокер-независимые).

Таблицы portfolio_* используются T-Invest, Bybit и другими интеграциями.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesPortfolioModels [1]

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base

SCHEMA = settings.DB_SCHEMA


class PortfolioAccount(Base):
    """Счёт пользователя у брокера (T-Invest, Bybit и др.)."""

    __tablename__ = "portfolio_accounts"
    __table_args__ = (
        Index("ix_portfolio_accounts_user_account", "user_id", "account_id", unique=True),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)

    # Unique only together with user_id (see uq_user_account / ix_portfolio_accounts_user_account).
    # ByBit external ids are stable per user: bybit:UNIFIED|FUND|COPY.
    account_id = Column(String(80), nullable=False)
    account_type = Column(String(50), nullable=False)
    account_name = Column(String(255), nullable=True)
    account_status = Column(String(50), nullable=False)
    opened_date = Column(DateTime(timezone=True), nullable=True)
    closed_date = Column(DateTime(timezone=True), nullable=True)
    access_level = Column(String(50), nullable=True)

    is_active = Column(Integer, nullable=False, default=1)
    # 1 = скрыт из сводки/структуры дашборда (сам счёт остаётся OPEN)
    dashboard_hidden = Column(Integer, nullable=False, default=0)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_token_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="portfolio_accounts")
    snapshots = relationship("PortfolioSnapshot", back_populates="account", cascade="all, delete-orphan")
    operations = relationship("PortfolioOperation", back_populates="account", cascade="all, delete-orphan")
    orders = relationship("PortfolioOrder", back_populates="account", cascade="all, delete-orphan")


class PortfolioSnapshot(Base):
    """Снимок портфеля на определённый момент времени."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_account_date", "account_id", "snapshot_date"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    total_amount_portfolio = Column(Numeric(20, 4), nullable=False)
    total_amount_shares = Column(Numeric(20, 4), nullable=True)
    total_amount_bonds = Column(Numeric(20, 4), nullable=True)
    total_amount_etf = Column(Numeric(20, 4), nullable=True)
    total_amount_currencies = Column(Numeric(20, 4), nullable=True)
    total_amount_futures = Column(Numeric(20, 4), nullable=True)
    total_amount_options = Column(Numeric(20, 4), nullable=True)
    total_amount_sp = Column(Numeric(20, 4), nullable=True)

    expected_yield = Column(Numeric(10, 4), nullable=True)
    daily_yield = Column(Numeric(20, 4), nullable=True)
    daily_yield_relative = Column(Numeric(10, 4), nullable=True)

    currency = Column(String(10), nullable=False, default="RUB")

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    account = relationship("PortfolioAccount", back_populates="snapshots")
    positions = relationship("PortfolioPosition", back_populates="snapshot", cascade="all, delete-orphan")


class PortfolioPosition(Base):
    """Позиция в снимке портфеля."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        Index("ix_portfolio_positions_snapshot", "snapshot_id"),
        Index("ix_portfolio_positions_figi", "figi"),
        Index("ix_portfolio_positions_ticker", "ticker"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_snapshots.id", ondelete="CASCADE"), nullable=False)

    figi = Column(String(20), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)
    ticker = Column(String(50), nullable=True)
    class_code = Column(String(20), nullable=True)

    instrument_type = Column(String(30), nullable=False)

    quantity = Column(Numeric(20, 4), nullable=False)
    quantity_lots = Column(Numeric(20, 4), nullable=True)

    average_position_price = Column(Numeric(20, 4), nullable=True)
    average_position_price_fifo = Column(Numeric(20, 4), nullable=True)
    current_price = Column(Numeric(20, 4), nullable=True)
    average_position_price_pt = Column(Numeric(20, 4), nullable=True)

    expected_yield = Column(Numeric(10, 4), nullable=True)
    expected_yield_fifo = Column(Numeric(10, 4), nullable=True)
    daily_yield = Column(Numeric(20, 4), nullable=True)
    var_margin = Column(Numeric(20, 4), nullable=True)

    current_nkd = Column(Numeric(20, 4), nullable=True)

    blocked = Column(Integer, nullable=False, default=0)
    blocked_lots = Column(Numeric(20, 4), nullable=True)

    extra_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    snapshot = relationship("PortfolioSnapshot", back_populates="positions")


class PortfolioOperation(Base):
    """Операция по счёту (история сделок, пополнений и т.д.)."""

    __tablename__ = "portfolio_operations"
    __table_args__ = (
        Index("ix_portfolio_operations_account_date", "account_id", "operation_date"),
        Index("ix_portfolio_operations_operation_id", "operation_id", unique=True),
        Index("ix_portfolio_operations_figi", "figi"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)

    operation_id = Column(String(120), nullable=False, unique=True)
    parent_operation_id = Column(String(50), nullable=True)

    figi = Column(String(20), nullable=True)
    instrument_type = Column(String(30), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)

    operation_type = Column(String(50), nullable=False)
    operation_date = Column(DateTime(timezone=True), nullable=False)

    quantity = Column(Numeric(20, 4), nullable=False)
    quantity_rest = Column(Numeric(20, 4), nullable=True)
    price = Column(Numeric(20, 4), nullable=False)
    price_currency = Column(String(10), nullable=False)

    payment = Column(Numeric(20, 4), nullable=False)
    payment_currency = Column(String(10), nullable=False)

    commission = Column(Numeric(20, 4), nullable=True)
    commission_currency = Column(String(10), nullable=True)

    status = Column(String(128), nullable=False)

    trades = Column(JSON, nullable=True)

    extra_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    account = relationship("PortfolioAccount", back_populates="operations")


class PortfolioOrder(Base):
    """Заявка (ордер) по счёту."""

    __tablename__ = "portfolio_orders"
    __table_args__ = (
        Index("ix_portfolio_orders_account_date", "account_id", "order_date"),
        Index("uq_portfolio_orders_account_order_id", "account_id", "order_id", unique=True),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)

    order_id = Column(String(120), nullable=False)
    figi = Column(String(32), nullable=True)
    instrument_uid = Column(String(50), nullable=True)

    order_type = Column(String(30), nullable=False)
    order_direction = Column(String(20), nullable=False)
    order_date = Column(DateTime(timezone=True), nullable=False)

    lots_requested = Column(Numeric(20, 4), nullable=False)
    lots_executed = Column(Numeric(20, 4), nullable=True)
    price = Column(Numeric(20, 4), nullable=True)
    execution_price = Column(Numeric(20, 4), nullable=True)

    status = Column(String(30), nullable=False)

    commission = Column(Numeric(20, 4), nullable=True)
    commission_currency = Column(String(10), nullable=True)

    extra_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    account = relationship("PortfolioAccount", back_populates="orders")


class ExternalApiLog(Base):
    """Логи вызовов внешних брокерских API (любой брокер)."""

    __tablename__ = "external_api_logs"
    __table_args__ = (
        Index("ix_external_api_logs_user_created", "user_id", "created_at"),
        Index("ix_external_api_logs_endpoint", "endpoint"),
        Index("ix_external_api_logs_success", "success"),
        Index("ix_external_api_logs_broker", "broker"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="SET NULL"), nullable=True)
    token_id = Column(BigInteger, nullable=True)

    broker = Column(String(32), nullable=False, default="tinvest")
    context_type = Column(String(64), nullable=True)
    context_ref = Column(String(128), nullable=True)

    endpoint = Column(String(500), nullable=False)
    request_data = Column(JSON, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_data = Column(JSON, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    success = Column(Integer, nullable=False, default=1)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class InstrumentCache(Base):
    """Кэш информации об инструментах."""

    __tablename__ = "instrument_cache"
    __table_args__ = (
        Index("ix_instrument_cache_figi", "figi", unique=True),
        Index("ix_instrument_cache_ticker", "ticker"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    figi = Column(String(20), nullable=False, unique=True)
    ticker = Column(String(50), nullable=True)
    isin = Column(String(20), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)

    name = Column(String(255), nullable=True)
    instrument_type = Column(String(30), nullable=False)
    currency = Column(String(10), nullable=True)
    lot = Column(Integer, nullable=True)

    nominal = Column(Numeric(20, 4), nullable=True)
    nominal_currency = Column(String(10), nullable=True)
    maturity_date = Column(DateTime(timezone=True), nullable=True)

    sector = Column(String(100), nullable=True)

    extra_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
