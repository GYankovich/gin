"""
Модели T-Invest API (токены).

Портфельные ORM-модели — в app.modules.portfolio.models.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestModels [1]

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base

SCHEMA = settings.DB_SCHEMA


class ApiToken(Base):
    """API-токены пользователей (T-Invest, Bybit и др.)."""

    __tablename__ = "api_tokens"
    __table_args__ = (
        Index("ix_api_tokens_user_type", "user_id", "token_type"),
        Index("ix_api_tokens_token", "token"),
        {"schema": SCHEMA, "extend_existing": True},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)

    token_type = Column(String(50), nullable=False)
    token = Column(Text, nullable=False)
    token_name = Column(String(255), nullable=True)

    status = Column(Integer, nullable=False, default=1)
    refresh_interval_minutes = Column(Integer, nullable=False, default=60)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    extra_data = Column(JSON, nullable=True)
    account_id = Column(String(50), nullable=True)

    user = relationship("User", back_populates="api_tokens")
    robots = relationship("Robot", back_populates="token")
