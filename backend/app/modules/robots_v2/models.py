"""SQLAlchemy models for robots v2 greenfield contour."""

from __future__ import annotations

import uuid
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


class RobotV2(Base):
    """Greenfield robots table (parallel to legacy `robots`)."""

    __tablename__ = "robots_v2"
    __table_args__ = (
        Index("ix_robots_v2_user_id", "user_id"),
        Index("ix_robots_v2_token_id", "token_id"),
        Index("ix_robots_v2_type", "type"),
        Index("ix_robots_v2_status", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token_id = Column(BigInteger, ForeignKey("api_tokens.id", ondelete="SET NULL"), nullable=True)
    type = Column(Integer, nullable=False)
    status = Column(Integer, nullable=False, default=0)
    config_version = Column(Integer, nullable=False, default=4)
    config = Column(JSON, nullable=False, default=dict)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    last_started = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    usercre = Column(BigInteger, nullable=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    usermod = Column(BigInteger, nullable=True)
    date_modification = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    token = relationship("ApiToken", foreign_keys=[token_id])
    config_history = relationship(
        "RobotConfigHistory",
        back_populates="robot",
        cascade="all, delete-orphan",
    )


class RobotConfigHistory(Base):
    """Immutable config snapshots (ADR-08)."""

    __tablename__ = "robot_config_history"
    __table_args__ = (
        Index("ix_robot_config_history_robot_id", "robot_id"),
        Index("ix_robot_config_history_robot_version", "robot_id", "version", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id = Column(BigInteger, ForeignKey("robots_v2.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    config = Column(JSON, nullable=False)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    robot = relationship("RobotV2", back_populates="config_history")
