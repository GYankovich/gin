import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.bybit.environment import bybit_use_testnet


def test_bybit_use_testnet_is_always_false():
    assert bybit_use_testnet() is False
    assert bybit_use_testnet(True) is False
