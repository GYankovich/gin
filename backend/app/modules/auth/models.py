"""
Модели для модуля авторизации
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesAuthModels [1]
#/// Исходный модуль `backend/app/modules/auth/models.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime,
    ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings


SCHEMA = settings.DB_SCHEMA


# Seeded in 0076_package_feature — «Полный» package id=1
DEFAULT_PACKAGE_ID = 1

STATUS_OFF = 0
STATUS_ON = 1

TAB_DASHBOARD = "dashboard"
TAB_PORTFOLIO = "portfolio"
TAB_ROBOTS = "robots"
TAB_BACKTEST = "backtest"
PACKAGE_TAB_CODES = (TAB_DASHBOARD, TAB_PORTFOLIO, TAB_ROBOTS, TAB_BACKTEST)


class User(Base):
    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    login = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    # Numeric FK to package.id (column name kept as package_code per product contract)
    package_code = Column(
        BigInteger,
        ForeignKey("package.id"),
        nullable=False,
        default=DEFAULT_PACKAGE_ID,
    )

    # Relationships - используем строки с именами классов (без полных путей)
    emails = relationship("UserEmail", back_populates="user", cascade="all, delete-orphan")
    phones = relationship("UserPhone", back_populates="user", cascade="all, delete-orphan")
    tokens = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")

    # Убираем дублирующуюся связь tinvest_settings (она конфликтует с api_tokens)
    # Используем только одну связь с токенами
    api_tokens = relationship(
        "ApiToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    portfolio_accounts = relationship(
        "PortfolioAccount",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    trading_robots = relationship(
        "Robot",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Package(Base):
    __tablename__ = "package"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    status = Column(Integer, nullable=False, default=STATUS_ON)
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True)

    features = relationship(
        "PackageFeature",
        back_populates="package",
        cascade="all, delete-orphan",
    )


class PackageFeature(Base):
    """Per-package tab visibility. robots and backtest are independent rows."""

    __tablename__ = "package_feature"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    package_id = Column(BigInteger, ForeignKey("package.id", ondelete="CASCADE"), nullable=False)
    feature = Column(String(64), nullable=False)
    status = Column(Integer, nullable=False, default=STATUS_OFF)
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True)

    package = relationship("Package", back_populates="features")


class UserEmail(Base):
    __tablename__ = "user_email"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="emails")


class UserPhone(Base):
    __tablename__ = "user_phone"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    phone = Column(String(32), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="phones")


class UserTokenStatus:
    ACTIVE = 1
    BLOCKED = 2
    COMPLETED = 3


class UserToken(Base):
    __tablename__ = "user_token"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token = Column(Text, nullable=False, unique=True)
    status = Column(Integer, nullable=False, default=UserTokenStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    device_label = Column(String(128), nullable=True)
    geo_label = Column(String(255), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="tokens")


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String(128), primary_key=True)
    value = Column(String(512), nullable=False)
    description = Column(String(1024), nullable=True)