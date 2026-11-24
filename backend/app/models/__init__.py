#///EPIC Platform.ITEM App.TOPIC BackendAppModelsInit [1]
#/// Исходный модуль `backend/app/models/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

"""
Единая точка импорта всех моделей SQLAlchemy.
Legacy Robot* / DailyUniverse / DmsSubscription ORM removed after 0091.
"""

from app.modules.auth.models import (
    User,
    UserEmail,
    UserPhone,
    UserToken,
    AppConfig,
)

from app.modules.portfolio.models import (
    PortfolioAccount,
    PortfolioSnapshot,
    PortfolioPosition,
    PortfolioOperation,
    PortfolioOrder,
    ExternalApiLog,
    InstrumentCache,
)

from app.modules.tinvest.models import ApiToken

from app.modules.dms.models import (
    SecurityStatic,
    MarketSnapshot,
    MarketSnapshotData,
    CandleCache,
)

__all__ = [
    "User",
    "UserEmail",
    "UserPhone",
    "UserToken",
    "AppConfig",
    "ApiToken",
    "PortfolioAccount",
    "PortfolioSnapshot",
    "PortfolioPosition",
    "PortfolioOperation",
    "PortfolioOrder",
    "ExternalApiLog",
    "InstrumentCache",
    "SecurityStatic",
    "MarketSnapshot",
    "MarketSnapshotData",
    "CandleCache",
]
