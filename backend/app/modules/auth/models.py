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


class User(Base):
    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    login = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

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

    user = relationship("User", back_populates="tokens")


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String(128), primary_key=True)
    value = Column(String(512), nullable=False)
    description = Column(String(1024), nullable=True)