import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots import schemas
from app.modules.robots.trading import queries as trading_queries


def test_grain_seed_config_allows_supported_non_tinvest_brokers():
    cfg = schemas.GrainSeedConfig.model_validate(
        {
            "broker_type": "vtb",
            "strategy": "grain_seed",
            "strategy_params": {"ma_fast_period": 5, "ma_slow_period": 20},
        }
    )
    assert cfg.broker_type == "vtb"


def test_robot_update_request_patch_shape():
    req = schemas.RobotUpdateRequest.model_validate(
        {"robotId": 11, "patch": {"name": "My Robot", "type": 2}}
    )
    assert req.robotId == 11
    assert req.patch.name == "My Robot"
    assert req.patch.type == 2


def test_trade_update_query_uses_new_columns():
    sql = trading_queries.build_update_trade_status_query()
    assert "filled_quantity" in sql
    assert "avg_fill_price" in sql
    assert "updated_at" in sql
