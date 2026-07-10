from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBrokersFactory [1]
#/// Исходный модуль `backend/app/modules/robots/trading/brokers/factory.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, Optional

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade
from app.modules.robots.trading.brokers.routing import (
    STUB_BROKERS,
    normalize_broker_type,
    resolve_bybit_api_secret,
    resolve_bybit_instrument_category,
)
from app.modules.robots.trading.brokers.stub import StubBrokerFacade
from app.modules.robots.trading.brokers.tinvest import TInvestBrokerFacade


def create_broker_facade(
    broker_type: str,
    token: str,
    *,
    api_secret: str | None = None,
    token_extra_data: Optional[Dict[str, Any]] = None,
    instrument_category: str | None = None,
    robot_config: Optional[Dict[str, Any]] = None,
    user_id: int | None = None,
    token_id: int | None = None,
    context_type: str | None = None,
    context_ref: str | None = None,
) -> BrokerFacade:
    normalized = normalize_broker_type(broker_type)
    if normalized == "tinvest":
        return TInvestBrokerFacade(token)
    if normalized == "bybit":
        secret = resolve_bybit_api_secret(
            api_secret=api_secret,
            token_extra_data=token_extra_data,
        )
        category = instrument_category or resolve_bybit_instrument_category(robot_config)
        return ByBitBrokerFacade(
            token,
            testnet=False,
            api_secret=secret,
            instrument_category=category,
            user_id=user_id,
            token_id=token_id,
            context_type=context_type,
            context_ref=context_ref,
        )
    if normalized in STUB_BROKERS:
        return StubBrokerFacade(normalized)
    return StubBrokerFacade(normalized)
