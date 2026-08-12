import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.validator import validate_trading_config


def _sample_trading_config() -> dict:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:30",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["SBER", "GAZP"],
            "excluded": [],
            "maxAssets": 20,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    }


def test_trading_config_v4_validates():
    cfg = TradingRobotConfigV4.model_validate(_sample_trading_config())
    assert cfg.strategy.archetype == "momentum"
    assert cfg.config_version == 4


def test_scalper_requires_advanced_mode():
    raw = _sample_trading_config()
    raw["strategy"] = {
        "archetype": "scalper",
        "timeframe": "1m",
        "params": {"deltaThresholdPct": 5, "requiresWebSocket": True},
    }
    _, issues = validate_trading_config(raw)
    assert issues
    assert any("advancedMode" in issue.message for issue in issues)


def test_stop_loss_must_be_below_take_profit():
    raw = _sample_trading_config()
    raw["risk"]["stopLossPct"] = 5
    raw["risk"]["takeProfitPct"] = 4
    _, issues = validate_trading_config(raw)
    assert issues
