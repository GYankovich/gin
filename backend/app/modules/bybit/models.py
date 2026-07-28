"""SQLAlchemy models for ByBit market data cache."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint

from app.core.config import settings
from app.core.database import Base

SCHEMA = settings.DB_SCHEMA


class BybitFundingHistory(Base):
    __tablename__ = "bybit_funding_history"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "funding_time",
            "instrument_category",
            name="uq_bybit_funding_history_symbol_time_category",
        ),
        Index("idx_bybit_funding_history_symbol_time", "symbol", "funding_time"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    funding_time = Column(DateTime(timezone=True), nullable=False)
    funding_rate = Column(Numeric(12, 8), nullable=False)
    instrument_category = Column(String(16), nullable=False, default="linear")
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)


class BybitOpenInterestHistory(Base):
    __tablename__ = "bybit_open_interest_history"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_time",
            "instrument_category",
            name="uq_bybit_oi_history_symbol_time_category",
        ),
        Index("idx_bybit_oi_history_symbol_time", "symbol", "snapshot_time"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    open_interest_usd = Column(Numeric(20, 4), nullable=False)
    instrument_category = Column(String(16), nullable=False, default="linear")
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)


class BybitLsrHistory(Base):
    __tablename__ = "bybit_lsr_history"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_time",
            "instrument_category",
            name="uq_bybit_lsr_history_symbol_time_category",
        ),
        Index("idx_bybit_lsr_history_symbol_time", "symbol", "snapshot_time"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    long_ratio = Column(Numeric(12, 8), nullable=False)
    short_ratio = Column(Numeric(12, 8), nullable=False)
    instrument_category = Column(String(16), nullable=False, default="linear")
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)


__all__ = ["BybitFundingHistory", "BybitOpenInterestHistory", "BybitLsrHistory"]
