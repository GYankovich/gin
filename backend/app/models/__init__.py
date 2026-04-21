# app/models/__init__.py
"""
Единая точка импорта всех моделей SQLAlchemy
Импортируем в правильном порядке, чтобы избежать циклических зависимостей
"""

# Сначала базовые модели auth
from app.modules.auth.models import (
    User,
    UserEmail,
    UserPhone,
    UserToken,
    AppConfig
)

# Затем модели tinvest
from app.modules.tinvest.models import (
    ApiToken,
    PortfolioAccount,
    PortfolioSnapshot,
    PortfolioPosition,
    PortfolioOperation,
    PortfolioOrder,
    ExternalApiLog,
    InstrumentCache
)

# Затем модели robots
from app.modules.robots.models import (
    Robot,
    RobotTrade,
    RobotLog,
    RobotSignal,
    RobotSchedule,
    RobotStrategy,
    RobotExecutionLog,
    RobotRunCycle,
    RobotDecision,
    RobotOrderEvent,
)
from app.modules.dms.models import (
    SecurityStatic,
    DmsSubscription,
    MarketSnapshot,
    MarketSnapshotData,
    CandleCache,
    DailyUniverse,
)

# Для обратной совместимости
__all__ = [
    'User',
    'UserEmail',
    'UserPhone',
    'UserToken',
    'AppConfig',
    'ApiToken',
    'PortfolioAccount',
    'PortfolioSnapshot',
    'PortfolioPosition',
    'PortfolioOperation',
    'PortfolioOrder',
    'ExternalApiLog',
    'InstrumentCache',
    'Robot',
    'RobotTrade',
    'RobotLog',
    'RobotSignal',
    'RobotSchedule',
    'RobotStrategy',
    'RobotExecutionLog',
    'RobotRunCycle',
    'RobotDecision',
    'RobotOrderEvent',
    'SecurityStatic',
    'DmsSubscription',
    'MarketSnapshot',
    'MarketSnapshotData',
    'CandleCache',
    'DailyUniverse',
]