"""
Модели для торговых роботов
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, ForeignKey,
    Integer, Numeric, JSON, Boolean, Text, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


class TradingRobot(Base):
    """
    Торговый робот
    """
    __tablename__ = "trading_robots"
    __table_args__ = (
        Index("ix_trading_robots_user", "user_id"),
        Index("ix_trading_robots_status", "status"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)

    # Привязка к токену (может быть NULL, если робот временно отключен)
    token_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.api_tokens.id", ondelete="SET NULL"), nullable=True)

    # Основные данные робота
    name = Column(String(255), nullable=False)  # Название робота
    description = Column(Text, nullable=True)   # Описание стратегии
    robot_type = Column(String(50), nullable=False)  # Тип: 'grid', 'trend', 'arbitrage', etc.

    # Статус и настройки
    status = Column(String(20), nullable=False, default="stopped")  # active, stopped, error
    is_active = Column(Integer, nullable=False, default=0)  # 0/1 для быстрых фильтров

    # Параметры стратегии (храним в JSON для гибкости)
    strategy_params = Column(JSON, nullable=False, default={})

    # Ограничения и риск-менеджмент
    max_daily_loss = Column(Numeric(10, 2), nullable=True)  # Максимальный дневной убыток (%)
    max_position_size = Column(Numeric(20, 2), nullable=True)  # Максимальный размер позиции
    allowed_instruments = Column(JSON, nullable=True)  # Разрешенные инструменты (FIGI list)

    # Статистика
    total_trades = Column(Integer, nullable=False, default=0)
    successful_trades = Column(Integer, nullable=False, default=0)
    total_profit = Column(Numeric(20, 4), nullable=False, default=0)
    total_profit_percent = Column(Numeric(10, 4), nullable=False, default=0)

    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

    # Связи
    user = relationship("User", back_populates="trading_robots")
    token = relationship("ApiToken", back_populates="robots")
    trades = relationship("RobotTrade", back_populates="robot", cascade="all, delete-orphan")
    logs = relationship("RobotLog", back_populates="robot", cascade="all, delete-orphan")
    signals = relationship("RobotSignal", back_populates="robot", cascade="all, delete-orphan")


class RobotTrade(Base):
    """
    Сделки робота
    """
    __tablename__ = "robot_trades"
    __table_args__ = (
        Index("ix_robot_trades_robot_date", "robot_id", "created_at"),
        Index("ix_robot_trades_figi", "figi"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.trading_robots.id", ondelete="CASCADE"), nullable=False)

    # Данные сделки
    figi = Column(String(20), nullable=False)
    ticker = Column(String(50), nullable=True)
    instrument_type = Column(String(30), nullable=False)

    # Направление
    side = Column(String(10), nullable=False)  # buy, sell

    # Количество и цена
    quantity = Column(Numeric(20, 4), nullable=False)
    price = Column(Numeric(20, 4), nullable=False)
    total_amount = Column(Numeric(20, 4), nullable=False)  # quantity * price

    # Комиссия
    commission = Column(Numeric(20, 4), nullable=True)
    commission_currency = Column(String(10), nullable=True)

    # ID ордера в T-Invest
    order_id = Column(String(50), nullable=True, unique=True)

    # Результат сделки (для закрытых позиций)
    profit = Column(Numeric(20, 4), nullable=True)
    profit_percent = Column(Numeric(10, 4), nullable=True)

    # Статус
    status = Column(String(20), nullable=False, default="open")  # open, closed, cancelled

    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Связи
    robot = relationship("TradingRobot", back_populates="trades")


class RobotLog(Base):
    """
    Логи работы робота
    """
    __tablename__ = "robot_logs"
    __table_args__ = (
        Index("ix_robot_logs_robot_date", "robot_id", "created_at"),
        Index("ix_robot_logs_level", "level"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.trading_robots.id", ondelete="CASCADE"), nullable=False)

    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("TradingRobot", back_populates="logs")


class RobotSignal(Base):
    """
    Сигналы робота (для анализа)
    """
    __tablename__ = "robot_signals"
    __table_args__ = (
        Index("ix_robot_signals_robot_date", "robot_id", "created_at"),
        Index("ix_robot_signals_figi", "figi"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.trading_robots.id", ondelete="CASCADE"), nullable=False)

    figi = Column(String(20), nullable=False)
    ticker = Column(String(50), nullable=True)

    signal_type = Column(String(30), nullable=False)  # buy, sell, hold, alert
    signal_strength = Column(Integer, nullable=True)  # 0-100

    # Данные, на основе которых принято решение
    indicators = Column(JSON, nullable=True)
    price_at_signal = Column(Numeric(20, 4), nullable=True)

    # Было ли сигнал исполнен
    was_executed = Column(Integer, nullable=False, default=0)
    executed_trade_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robot_trades.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("TradingRobot", back_populates="signals")
    executed_trade = relationship("RobotTrade")