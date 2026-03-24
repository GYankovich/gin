"""
Модели для роботов
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, ForeignKey,
    Integer, Numeric, JSON, Text, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


class Dictionary(Base):
    """
    Справочная таблица для всех enumerations в системе
    """
    __tablename__ = "dictionary"
    __table_args__ = (
        Index("ix_dictionary_table_column", "table_name", "column_name"),
        Index("ix_dictionary_num_value", "num_value"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    num_value = Column(Integer, nullable=True)
    string_value = Column(String(255), nullable=True)
    hide_from_ui = Column(Integer, nullable=False, default=0)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)


class Robot(Base):
    """
    Основная таблица роботов
    """
    __tablename__ = "robots"
    __table_args__ = (
        Index("ix_robots_user_id", "user_id"),
        Index("ix_robots_token_id", "token_id"),
        Index("ix_robots_type", "type"),
        Index("ix_robots_status", "status"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=True)  # Теперь может быть NULL
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)
    token_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.api_tokens.id", ondelete="SET NULL"), nullable=True)

    # Ссылки на dictionary
    type = Column(Integer, nullable=False)  # ссылка на dictionary (ROBOT.TYPE)
    status = Column(Integer, nullable=False, default=0)  # ссылка на dictionary (ROBOT.STATUS)

    # JSON конфигурация (все параметры робота)
    config = Column(JSON, nullable=False, default={})

    # Временные метки
    last_started = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", foreign_keys=[user_id])
    token = relationship("ApiToken", foreign_keys=[token_id])
    logs = relationship("RobotLog", back_populates="robot", foreign_keys="RobotLog.robot_id")
    trades = relationship("RobotTrade", back_populates="robot", cascade="all, delete-orphan")
    signals = relationship("RobotSignal", back_populates="robot", cascade="all, delete-orphan")


class RobotConfig(Base):
    """
    Шаблоны конфигурации для разных типов роботов
    """
    __tablename__ = "robot_configs"
    __table_args__ = (
        Index("ix_robot_configs_type", "robot_type"),
        Index("ix_robot_configs_key", "config_key"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_type = Column(Integer, nullable=False)  # ссылка на dictionary (ROBOT.TYPE)
    config_key = Column(String(100), nullable=False)
    config_value = Column(JSON, nullable=False)  # схема параметра
    description = Column(String(500), nullable=True)
    is_required = Column(Integer, nullable=False, default=0)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)


class RobotTrade(Base):
    """
    Сделки робота
    """
    __tablename__ = "robot_trades"
    __table_args__ = (
        Index("ix_robot_trades_robot_date", "robot_id", "created_at"),
        Index("ix_robot_trades_figi", "figi"),
        Index("ix_robot_trades_status", "status"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)

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

    # Статус (можно сделать ссылкой на dictionary, но пока оставим как есть)
    status = Column(String(20), nullable=False, default="open")  # open, closed, cancelled

    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("Robot", back_populates="trades")
    signals = relationship("RobotSignal", back_populates="executed_trade")


class RobotLog(Base):
    """
    Логи работы робота
    """
    __tablename__ = "robot_logs"
    __table_args__ = (
        Index("ix_robot_logs_robot_date", "robot_id", "created_at"),
        Index("ix_robot_logs_robot_name", "robot_name"),
        Index("ix_robot_logs_user_token", "user_id", "token_id"),
        Index("ix_robot_logs_success", "success"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=True)

    # Поля для логов без привязки к конкретному роботу
    robot_name = Column(String(255), nullable=False)
    robot_version = Column(String(20), nullable=True)

    token_id = Column(BigInteger, nullable=True)
    user_id = Column(BigInteger, nullable=True)

    endpoint = Column(String(500), nullable=False)

    request_data = Column(JSON, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_data = Column(JSON, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    success = Column(Integer, nullable=False, default=1)  # 1 - успешно, 0 - ошибка
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("Robot", back_populates="logs")


class RobotSignal(Base):
    """
    Сигналы робота (для анализа)
    """
    __tablename__ = "robot_signals"
    __table_args__ = (
        Index("ix_robot_signals_robot_date", "robot_id", "created_at"),
        Index("ix_robot_signals_figi", "figi"),
        Index("ix_robot_signals_type", "signal_type"),
        Index("ix_robot_signals_executed", "was_executed"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)

    figi = Column(String(20), nullable=False)
    ticker = Column(String(50), nullable=True)

    signal_type = Column(String(30), nullable=False)  # buy, sell, hold, alert
    signal_strength = Column(Integer, nullable=True)  # 0-100

    # Данные, на основе которых принято решение
    indicators = Column(JSON, nullable=True)
    price_at_signal = Column(Numeric(20, 4), nullable=True)

    # Было ли сигнал исполнен
    was_executed = Column(Integer, nullable=False, default=0)  # 0 - нет, 1 - да
    executed_trade_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robot_trades.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("Robot", back_populates="signals")
    executed_trade = relationship("RobotTrade", back_populates="signals")



class RobotSchedule(Base):
    """
    Расписание работы робота
    """
    __tablename__ = "robot_schedules"
    __table_args__ = (
        Index("ix_robot_schedules_robot_id", "robot_id"),
        Index("ix_robot_schedules_active", "is_active"),
        Index("ix_robot_schedules_type", "schedule_type"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)

    # Тип расписания: 1=interval, 2=time_range, 3=market_hours
    schedule_type = Column(Integer, nullable=False)

    # Для interval-режима (в секундах)
    interval_seconds = Column(Integer, nullable=True)

    # Для time_range-режима (работа в определенные часы)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)

    # Дни недели (битовая маска: 1=пн, 2=вт, 4=ср, 8=чт, 16=пт, 32=сб, 64=вс)
    weekdays = Column(Integer, nullable=True)

    # Общие поля
    is_active = Column(Integer, nullable=False, default=1)
    priority = Column(Integer, nullable=False, default=0)
    description = Column(String(500), nullable=True)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    # Связи
    robot = relationship("Robot", foreign_keys=[robot_id])


class RobotStrategy(Base):
    """
    Стратегии роботов (версионированные)
    """
    __tablename__ = "robot_strategies"
    __table_args__ = (
        Index("ix_robot_strategies_robot_id", "robot_id"),
        Index("ix_robot_strategies_type", "strategy_type"),
        Index("ix_robot_strategies_active", "is_active"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)

    # Тип стратегии (ссылка на dictionary)
    strategy_type = Column(Integer, nullable=False)

    # Параметры стратегии в JSON (гибкая структура)
    parameters = Column(JSON, nullable=False, default={})

    # Валидация параметров (JSON Schema)
    validation_schema = Column(JSON, nullable=True)

    # Версионирование
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Integer, nullable=False, default=1)
    is_default = Column(Integer, nullable=False, default=0)

    # Аудит
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    # Связи
    robot = relationship("Robot", foreign_keys=[robot_id])


class RobotExecutionLog(Base):
    """
    Логи выполнения роботов (детальные)
    """
    __tablename__ = "robot_execution_logs"
    __table_args__ = (
        Index("ix_robot_exec_logs_robot_id", "robot_id"),
        Index("ix_robot_exec_logs_created_at", "created_at"),
        Index("ix_robot_exec_logs_status", "status"),
        Index("ix_robot_exec_logs_action_type", "action_type"),
        {"schema": SCHEMA}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robot_strategies.id", ondelete="SET NULL"), nullable=True)

    # Тип действия: 1=start, 2=stop, 3=error, 4=signal, 5=trade
    action_type = Column(Integer, nullable=False)

    # Статус: 0=success, 1=failed, 2=pending
    status = Column(Integer, nullable=False)

    # Сообщение и детали
    message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)

    # Метрики выполнения
    execution_time_ms = Column(Integer, nullable=True)
    error_stack = Column(Text, nullable=True)

    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Связи
    robot = relationship("Robot", foreign_keys=[robot_id])
    strategy = relationship("RobotStrategy", foreign_keys=[strategy_id])