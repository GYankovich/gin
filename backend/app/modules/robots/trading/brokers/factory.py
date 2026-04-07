from __future__ import annotations

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.stub import StubBrokerFacade
from app.modules.robots.trading.brokers.tinvest import TInvestBrokerFacade


def create_broker_facade(broker_type: str, token: str) -> BrokerFacade:
    normalized = (broker_type or "tinvest").lower()
    if normalized == "tinvest":
        return TInvestBrokerFacade(token)
    if normalized in {"vtb", "alfa"}:
        return StubBrokerFacade(normalized)
    return StubBrokerFacade(normalized)
