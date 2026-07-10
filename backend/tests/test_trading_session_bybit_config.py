from __future__ import annotations

from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.session import TradingSession


class _DummyDb:
    def execute(self, *args, **kwargs):  # pragma: no cover - not used
        raise RuntimeError("not expected")


def test_trading_session_reads_bybit_symbols_and_signal_generation():
    cfg = {
        "broker_type": "bybit",
        "allowed_symbols": ["btcusdt", "ethusdt"],
        "signal_generation": {
            "strategy": "reversion_to_ma",
            "params": {"interval": "5m", "ma_period": 20},
            "update_interval_seconds": 12,
        },
    }
    s = TradingSession(
        db=_DummyDb(),
        schema="ganaly",
        robot_id=1,
        user_id=1,
        token_id=1,
        token="demo",
        config=cfg,
        log_func=lambda *_: None,
        mode=ExecutionMode.LIVE,
    )
    assert s.broker_type == "bybit"
    assert s.allowed_figis == ["BTCUSDT", "ETHUSDT"]
    assert s.strategy_name == "reversion_to_ma"
    assert s.strategy_params["interval"] == "5m"
    assert s.update_interval == 12


def test_trading_session_bybit_empty_symbols_has_ws4005_analog_error():
    cfg = {
        "broker_type": "bybit",
        "allowed_symbols": [],
    }
    s = TradingSession(
        db=_DummyDb(),
        schema="ganaly",
        robot_id=2,
        user_id=1,
        token_id=1,
        token="demo",
        config=cfg,
        log_func=lambda *_: None,
        mode=ExecutionMode.LIVE,
    )
    try:
        s._ensure_allowed_instruments_or_raise()
        assert False, "expected missing instruments exception"
    except Exception as exc:
        msg = str(exc)
        assert "WS_4005_ANALOG" in msg
        assert "allowed_symbols" in msg

