from app.modules.robots.trading.brokers.routing import broker_from_token_type


def test_broker_from_token_type_tinvest():
    assert broker_from_token_type(1) == "tinvest"


def test_broker_from_token_type_bybit():
    assert broker_from_token_type(2) == "bybit"


def test_broker_from_token_type_unknown_defaults_tinvest():
    assert broker_from_token_type(99) == "tinvest"
