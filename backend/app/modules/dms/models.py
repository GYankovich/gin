from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)

from app.core.config import settings
from app.core.database import Base

SCHEMA = settings.DB_SCHEMA


class SecurityStatic(Base):
    __tablename__ = "securities_static"
    __table_args__ = (
        {"schema": SCHEMA},
    )

    ticker = Column(String(20), primary_key=True)
    shortname = Column(String(100), nullable=True)
    lot_size = Column(Integer, nullable=True)
    min_step = Column(Numeric(10, 6), nullable=True)
    isin = Column(String(20), nullable=True)
    status = Column(String(10), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)


class DmsSubscription(Base):
    __tablename__ = "dms_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "robot_id",
            "subscription_key",
            "request_date",
            "snapshot_hour",
            name="uq_dms_subscriptions_robot_key_date_hour",
        ),
        Index("ix_dms_subscriptions_status", "status"),
        Index("ix_dms_subscriptions_requested_at", "requested_at"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)
    subscription_key = Column(String(100), nullable=False)
    board = Column(String(20), nullable=False, default="TQBR")
    include_candles = Column(Boolean, nullable=False, default=False)
    candle_interval = Column(String(10), nullable=True)
    candle_depth = Column(Integer, nullable=False, default=14)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    request_date = Column(Date, nullable=False, default=datetime.utcnow)
    snapshot_hour = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    snapshot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.market_snapshot.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshot"
    __table_args__ = (
        Index("ix_market_snapshot_board_time", "board", "snapshot_time"),
        Index("ix_market_snapshot_status", "status"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_time = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    board = Column(String(20), nullable=False, default="TQBR")
    status = Column(String(20), nullable=False, default="SUCCESS")
    error_message = Column(Text, nullable=True)
    is_manual = Column(Boolean, nullable=False, default=False)
    ttl_minutes = Column(Integer, nullable=False, default=5)
    moex_timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MarketSnapshotData(Base):
    __tablename__ = "market_snapshot_data"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "ticker", name="uq_market_snapshot_data_snapshot_ticker"),
        Index("idx_snapshot_data_ticker_time", "ticker", "snapshot_id"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.market_snapshot.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String(20), nullable=False)
    board_id = Column(String(12), nullable=True)
    short_name = Column(String(255), nullable=True)
    sec_name = Column(String(255), nullable=True)
    isin = Column(String(20), nullable=True)
    lot_size = Column(Integer, nullable=True)
    last_price = Column(Numeric(12, 4), nullable=True)
    open_price = Column(Numeric(12, 4), nullable=True)
    low_price = Column(Numeric(12, 4), nullable=True)
    high_price = Column(Numeric(12, 4), nullable=True)
    prev_price = Column(Numeric(12, 4), nullable=True)
    close_price = Column(Numeric(12, 4), nullable=True)
    value_today = Column(BigInteger, nullable=True)
    volume_lots = Column(BigInteger, nullable=True)
    security_status = Column(String(10), nullable=True)
    trading_status = Column(String(20), nullable=True)
    num_trades = Column(BigInteger, nullable=True)
    min_step = Column(Numeric(12, 6), nullable=True)
    issue_size = Column(Numeric(20, 4), nullable=True)
    bid = Column(Numeric(12, 4), nullable=True)
    ask = Column(Numeric(12, 4), nullable=True)
    spread = Column(Numeric(12, 4), nullable=True)
    market_update_time = Column(String(20), nullable=True)
    securities_payload = Column(JSON, nullable=True)
    marketdata_payload = Column(JSON, nullable=True)


class CandleCache(Base):
    __tablename__ = "candles_cache"
    __table_args__ = (
        UniqueConstraint("ticker", "interval", "candle_time", name="uq_candles_cache_ticker_interval_time"),
        Index("idx_candles_ticker_interval_time", "ticker", "interval", "candle_time"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    interval = Column(String(10), nullable=False)
    candle_time = Column(DateTime(timezone=True), nullable=False)
    open = Column(Numeric(12, 4), nullable=True)
    high = Column(Numeric(12, 4), nullable=True)
    low = Column(Numeric(12, 4), nullable=True)
    close = Column(Numeric(12, 4), nullable=True)
    volume = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class DailyUniverse(Base):
    __tablename__ = "daily_universe"
    __table_args__ = (
        UniqueConstraint("robot_id", "trade_date", "ticker", name="uq_daily_universe_robot_date_ticker"),
        Index("idx_daily_universe_robot_date", "robot_id", "trade_date"),
        Index("idx_daily_universe_result", "filter_result"),
        Index("idx_daily_universe_snapshot", "snapshot_id"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.robots.id", ondelete="CASCADE"), nullable=False)
    trade_date = Column(Date, nullable=False)
    ticker = Column(String(20), nullable=False)
    source = Column(String(30), nullable=False)
    filter_result = Column(String(20), nullable=True)
    reject_reason = Column(Text, nullable=True)
    snapshot_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.market_snapshot.id", ondelete="SET NULL"), nullable=True)
    price_at_filter = Column(Numeric(12, 4), nullable=True)
    volume_at_filter = Column(BigInteger, nullable=True)
    atr_value = Column(Numeric(12, 4), nullable=True)
    gap_percent = Column(Numeric(6, 3), nullable=True)
    applied_filters = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
