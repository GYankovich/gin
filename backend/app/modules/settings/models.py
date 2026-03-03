from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False)
    token = Column(Text, nullable=False)
    token_type = Column(String(50), nullable=False, default="tinvest")  # 'tinvest', 'telegram', etc.
    name = Column(String(100), nullable=True)  # Опциональное название
    is_active = Column(Integer, nullable=False, default=1)  # 1 - active, 0 - inactive
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Связь с пользователем
    user = relationship("User", back_populates="api_tokens")