"""Sandbox broker writes v3 type2_tinvest profile."""

from app.modules.robots.config.profiles import validate_robot_config, dump_robot_config


def test_sandbox_broker_type2_v3_roundtrip():
    raw = {
        "config_version": 3,
        "schema_profile": "type2_tinvest",
        "broker_type": "sandbox",
        "instrument_id_type": "figi",
        "strategy": "momentum_breakout",
        "signal_generation": {
            "strategy": "momentum_breakout",
            "params": {"interval": "CANDLE_INTERVAL_5_MIN"},
        },
        "risk": {},
        "costs": {},
    }
    model = validate_robot_config(robot_type=2, raw=raw, broker_type="sandbox")
    dumped = dump_robot_config(model)
    assert dumped["broker_type"] == "sandbox"
    assert dumped["config_version"] == 3
    assert dumped["schema_profile"] == "type2_tinvest"
