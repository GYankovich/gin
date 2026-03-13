"""
Модели для хранения данных из T-Invest API
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, ForeignKey,
    Integer, Numeric, JSON, Boolean, Index, Text
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


class ApiToken(Base):
    """
    API токены пользователей
    """
    __tablename__ = "api_tokens"
    __table_args__ = (
        Index("ix_api_tokens_user_type", "user_id", "token_type"),
        Index("ix_api_tokens_token", "token"),
        {"schema": SCHEMA, "extend_existing": True}  # ← ВАЖНО: добавляем extend_existing
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)

    token_type = Column(String(50), nullable=False)  # 'tinvest', 'telegram', etc.
    token = Column(Text, nullable=False)
    token_name = Column(String(255), nullable=True)  # Название токена (например "Основной", "Тестовый")

    # Статус
    is_active = Column(Integer, nullable=False, default=1)  # 1 - активен, 0 - отключен

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Если токен имеет срок действия

    # Дополнительные данные
    extra_data = Column(JSON, nullable=True)

    # Связи
    user = relationship("User", back_populates="api_tokens")
    robots = relationship("TradingRobot", back_populates="token")

    def mask_token(self, preview_length: int = 8) -> str:
        """Возвращает замаскированный токен для отображения"""
        if len(self.token) > preview_length * 2:
            return f"{self.token[:preview_length]}...{self.token[-preview_length:]}"
        return "***"

class PortfolioAccount(Base):
    """
    Счета пользователя в T-Invest
    """
    __tablename__ = "portfolio_accounts"
    __table_args__ = (
        Index("ix_portfolio_accounts_user_account", "user_id", "account_id", unique=True),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)

    # Данные из API
    account_id = Column(String(50), nullable=False, unique=True)
    account_type = Column(String(50), nullable=False)
    account_name = Column(String(255), nullable=True)
    account_status = Column(String(50), nullable=False)
    opened_date = Column(DateTime(timezone=True), nullable=True)
    closed_date = Column(DateTime(timezone=True), nullable=True)
    access_level = Column(String(50), nullable=True)

    # Локальные поля
    is_active = Column(Integer, nullable=False, default=1)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="portfolio_accounts")
    snapshots = relationship("PortfolioSnapshot", back_populates="account", cascade="all, delete-orphan")
    operations = relationship("PortfolioOperation", back_populates="account", cascade="all, delete-orphan")
    orders = relationship("PortfolioOrder", back_populates="account", cascade="all, delete-orphan")


class PortfolioSnapshot(Base):
    """
    Снимок портфеля на определенный момент времени
    """
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_account_date", "account_id", "snapshot_date"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Общие показатели
    total_amount_portfolio = Column(Numeric(20, 4), nullable=False)
    total_amount_shares = Column(Numeric(20, 4), nullable=True)
    total_amount_bonds = Column(Numeric(20, 4), nullable=True)
    total_amount_etf = Column(Numeric(20, 4), nullable=True)
    total_amount_currencies = Column(Numeric(20, 4), nullable=True)
    total_amount_futures = Column(Numeric(20, 4), nullable=True)
    total_amount_options = Column(Numeric(20, 4), nullable=True)
    total_amount_sp = Column(Numeric(20, 4), nullable=True)

    # Доходность
    expected_yield = Column(Numeric(10, 4), nullable=True)
    daily_yield = Column(Numeric(20, 4), nullable=True)
    daily_yield_relative = Column(Numeric(10, 4), nullable=True)

    # Валюта
    currency = Column(String(10), nullable=False, default="RUB")

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    account = relationship("PortfolioAccount", back_populates="snapshots")
    positions = relationship("PortfolioPosition", back_populates="snapshot", cascade="all, delete-orphan")


class PortfolioPosition(Base):
    """
    Позиция в снимке портфеля
    """
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        Index("ix_portfolio_positions_snapshot", "snapshot_id"),
        Index("ix_portfolio_positions_figi", "figi"),
        Index("ix_portfolio_positions_ticker", "ticker"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_snapshots.id", ondelete="CASCADE"), nullable=False)

    # Идентификаторы инструмента
    figi = Column(String(20), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)
    ticker = Column(String(50), nullable=True)
    class_code = Column(String(20), nullable=True)

    # Тип инструмента
    instrument_type = Column(String(30), nullable=False)  # share, bond, etf, currency, future, option

    # Количество
    quantity = Column(Numeric(20, 4), nullable=False)
    quantity_lots = Column(Numeric(20, 4), nullable=True)

    # Цены
    average_position_price = Column(Numeric(20, 4), nullable=True)
    average_position_price_fifo = Column(Numeric(20, 4), nullable=True)
    current_price = Column(Numeric(20, 4), nullable=True)
    average_position_price_pt = Column(Numeric(20, 4), nullable=True)

    # Доходность
    expected_yield = Column(Numeric(10, 4), nullable=True)
    expected_yield_fifo = Column(Numeric(10, 4), nullable=True)
    daily_yield = Column(Numeric(20, 4), nullable=True)
    var_margin = Column(Numeric(20, 4), nullable=True)

    # НКД для облигаций
    current_nkd = Column(Numeric(20, 4), nullable=True)

    # Блокировки
    blocked = Column(Integer, nullable=False, default=0)
    blocked_lots = Column(Numeric(20, 4), nullable=True)

    # Дополнительные данные
    extra_data = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    snapshot = relationship("PortfolioSnapshot", back_populates="positions")


class PortfolioOperation(Base):
    """
    Операции по счету (история сделок)
    """
    __tablename__ = "portfolio_operations"
    __table_args__ = (
        Index("ix_portfolio_operations_account_date", "account_id", "operation_date"),
        Index("ix_portfolio_operations_operation_id", "operation_id", unique=True),
        Index("ix_portfolio_operations_figi", "figi"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)

    # Идентификаторы
    operation_id = Column(String(50), nullable=False, unique=True)
    parent_operation_id = Column(String(50), nullable=True)

    # Инструмент
    figi = Column(String(20), nullable=True)
    instrument_type = Column(String(30), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)

    # Данные операции
    operation_type = Column(String(50), nullable=False)
    operation_date = Column(DateTime(timezone=True), nullable=False)

    # Количество и цена
    quantity = Column(Numeric(20, 4), nullable=False)
    quantity_rest = Column(Numeric(20, 4), nullable=True)
    price = Column(Numeric(20, 4), nullable=False)
    price_currency = Column(String(10), nullable=False)

    # Сумма операции
    payment = Column(Numeric(20, 4), nullable=False)
    payment_currency = Column(String(10), nullable=False)

    # Комиссии
    commission = Column(Numeric(20, 4), nullable=True)
    commission_currency = Column(String(10), nullable=True)

    # Статус
    status = Column(String(20), nullable=False)

    # Связи с другими операциями (для сделок)
    trades = Column(JSON, nullable=True)  # Массив связанных сделок

    # Дополнительно
    extra_data = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    account = relationship("PortfolioAccount", back_populates="operations")


class PortfolioOrder(Base):
    """
    Заявки (ордера) по счету
    """
    __tablename__ = "portfolio_orders"
    __table_args__ = (
        Index("ix_portfolio_orders_account_date", "account_id", "order_date"),
        Index("ix_portfolio_orders_order_id", "order_id", unique=True),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.portfolio_accounts.id", ondelete="CASCADE"), nullable=False)

    # Идентификаторы
    order_id = Column(String(50), nullable=False, unique=True)
    figi = Column(String(20), nullable=True)
    instrument_uid = Column(String(50), nullable=True)

    # Данные заявки
    order_type = Column(String(30), nullable=False)  # limit, market
    order_direction = Column(String(20), nullable=False)  # buy, sell
    order_date = Column(DateTime(timezone=True), nullable=False)

    # Количество и цена
    lots_requested = Column(Numeric(20, 4), nullable=False)
    lots_executed = Column(Numeric(20, 4), nullable=True)
    price = Column(Numeric(20, 4), nullable=True)  # для лимитных заявок
    execution_price = Column(Numeric(20, 4), nullable=True)  # средняя цена исполнения

    # Статус
    status = Column(String(30), nullable=False)  # new, partiallyfilled, filled, cancelled, rejected

    # Комиссии
    commission = Column(Numeric(20, 4), nullable=True)
    commission_currency = Column(String(10), nullable=True)

    # Дополнительно
    extra_data = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    account = relationship("PortfolioAccount", back_populates="orders")


class InstrumentCache(Base):
    """
    Кэш информации об инструментах (чтобы не запрашивать каждый раз)
    """
    __tablename__ = "instrument_cache"
    __table_args__ = (
        Index("ix_instrument_cache_figi", "figi", unique=True),
        Index("ix_instrument_cache_ticker", "ticker"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Идентификаторы
    figi = Column(String(20), nullable=False, unique=True)
    ticker = Column(String(50), nullable=True)
    isin = Column(String(20), nullable=True)
    instrument_uid = Column(String(50), nullable=True)
    position_uid = Column(String(50), nullable=True)

    # Данные инструмента
    name = Column(String(255), nullable=True)
    instrument_type = Column(String(30), nullable=False)
    currency = Column(String(10), nullable=True)
    lot = Column(Integer, nullable=True)

    # Для облигаций
    nominal = Column(Numeric(20, 4), nullable=True)
    nominal_currency = Column(String(10), nullable=True)
    maturity_date = Column(DateTime(timezone=True), nullable=True)

    # Для акций
    sector = Column(String(100), nullable=True)

    # Дополнительно
    extra_data = Column(JSON, nullable=True)

    # Метаданные
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)