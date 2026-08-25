import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.robots.trading.contracts import Candle
from app.modules.robots_v2.backtest.host import BacktestHost, build_bar_timeline, max_drawdown_percent
from app.modules.robots_v2.backtest.service import v4_timeframe_to_interval_raw
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4


def _sample_config() -> TradingRobotConfigV4:
    return TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, True, True],
                "timeFrom": "00:00",
                "timeTo": "23:59",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 5},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["AAA"],
            "excluded": [],
            "maxAssets": 5,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 50,
            "stopLossPct": 5,
            "takeProfitPct": 10,
            "maxDailyLoss": 50_000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    })


def _synthetic_uptrend(n: int = 30, start: float = 100.0) -> list[Candle]:
    base = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(n):
        px = start + i * 2.0
        out.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=px,
            high=px + 1,
            low=px - 1,
            close=px,
            volume=10_000 + i * 100,
            secid="AAA",
        ))
    return out


def test_v4_timeframe_mapping():
    assert v4_timeframe_to_interval_raw("5m") == "CANDLE_INTERVAL_5_MIN"
    assert v4_timeframe_to_interval_raw("1h") == "CANDLE_INTERVAL_HOUR"


def test_bar_timeline_sorted():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    series = {
        "A": [
            Candle("1h", t0, 1, 1, 1, 1, secid="A"),
            Candle("1h", t1, 2, 2, 2, 2, secid="A"),
        ],
        "B": [Candle("1h", t1, 3, 3, 3, 3, secid="B")],
    }
    assert build_bar_timeline(series) == [t0, t1]


def test_max_drawdown():
    curve = [
        {"equity": 100},
        {"equity": 110},
        {"equity": 88},
    ]
    assert max_drawdown_percent(curve) == 20.0


def test_backtest_host_replay_runs():
    config = _sample_config()
    candles = {"AAA": _synthetic_uptrend(40)}
    host = BacktestHost()
    result = asyncio.run(host.run(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_001,
    ))
    assert result.initial_capital == 100_000
    assert len(result.equity_curve) == 40
    assert result.history_stats["bars"] == 40


def test_backtest_host_run_sync_no_event_loop():
    config = _sample_config()
    candles = {"AAA": _synthetic_uptrend(40)}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_011,
    )
    assert result.history_stats["bars"] == 40
    assert len(result.equity_curve) == 40


def test_backtest_warmup_skips_trading_before_from():
    config = _sample_config()
    candles = {"AAA": _synthetic_uptrend(40)}
    trade_from = candles["AAA"][20].time
    host = BacktestHost()
    result = asyncio.run(host.run(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_002,
        trade_from=trade_from,
    ))
    assert result.history_stats["warmup_bars"] == 20
    assert result.history_stats["traded_bars"] == 20
    assert len(result.equity_curve) == 20
    assert result.equity_curve[0]["time"] == trade_from.isoformat()


def test_backtest_skips_bars_outside_schedule():
    config = _sample_config()
    config.core.schedule.weekdays = [True, True, True, True, True, False, False]
    config.core.schedule.time_from = "10:00"
    config.core.schedule.time_to = "18:30"
    # Thursday 2025-01-02: 07:00 UTC = 10:00 MSK (in), 16:00 UTC = 19:00 MSK (out)
    t_in = datetime(2025, 1, 2, 7, 0, tzinfo=timezone.utc)
    t_out = datetime(2025, 1, 2, 16, 0, tzinfo=timezone.utc)
    candles = {
        "AAA": [
            Candle("CANDLE_INTERVAL_HOUR", t_in, 100, 101, 99, 100, volume=10_000, secid="AAA"),
            Candle("CANDLE_INTERVAL_HOUR", t_out, 110, 111, 109, 110, volume=10_000, secid="AAA"),
        ],
    }
    host = BacktestHost()
    result = asyncio.run(host.run(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_003,
    ))
    assert result.history_stats["traded_bars"] == 1
    assert result.history_stats["skipped_schedule"] == 1
    assert len(result.equity_curve) == 1


def test_backtest_run_store_request_cancel():
    from app.modules.robots_v2.backtest.store import BacktestRunStore

    store = BacktestRunStore()

    async def _run() -> None:
        rec = await store.create(
            user_id=1,
            robot_id=3,
            requested_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            requested_to=datetime(2025, 1, 31, tzinfo=timezone.utc),
            initial_capital=100_000,
            config_snapshot={},
        )
        await store.update(rec.run_id, status="RUNNING")
        cancelled = await store.request_cancel(rec.run_id, user_id=1)
        assert cancelled is not None
        assert cancelled.cancel_requested is True
        missing = await store.request_cancel(rec.run_id, user_id=99)
        assert missing is None

    asyncio.run(_run())


def test_nested_config_diff_leaf_paths():
    from app.modules.robots_v2.backtest.persist import nested_config_diff

    diff = nested_config_diff(
        {"strategy": {"params": {"maPeriod": 50}}, "risk": {"stopLossPct": 2}},
        {"strategy": {"params": {"maPeriod": 20}}, "risk": {"stopLossPct": 2}},
    )
    assert "strategy.params.maPeriod" in diff
    assert diff["strategy.params.maPeriod"]["base"] == 50
    assert diff["strategy.params.maPeriod"]["compare"] == 20
    assert "risk.stopLossPct" not in diff


def test_record_fills_copies_reason():
    from app.modules.robots_v2.backtest.host import _record_fills

    trades: list[dict] = []
    orders: list[dict] = []
    t = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    n = _record_fills(
        [
            {"ticker": "SBER", "kind": "entry", "side": "BUY", "reason": "momentum_breakout",
             "qty": 10, "price": 250.0, "pnl": None},
            {"ticker": "SBER", "kind": "exit_sl_tp", "side": "SELL", "reason": "stop_loss",
             "qty": 10, "price": 240.0, "pnl": -110.0},
        ],
        bar_time=t,
        prices={"SBER": 240.0},
        commission=0.0005,
        trade_id=0,
        trades=trades,
        orders=orders,
    )
    assert n == 2
    assert trades[0]["reason"] == "momentum_breakout"
    assert trades[0]["kind"] == "entry"
    assert trades[1]["reason"] == "stop_loss"
    assert orders[1]["reason"] == "stop_loss"


def _breakout_then_gap_open() -> list[Candle]:
    """25 flat bars, then a breakout close, then a lower open (look-ahead trap)."""
    base = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for i in range(30):
        out.append(Candle(
            interval="CANDLE_INTERVAL_HOUR",
            time=base + timedelta(hours=i),
            open=100, high=101, low=99, close=100,
            volume=1_000, secid="AAA",
        ))
    out.append(Candle(
        interval="CANDLE_INTERVAL_HOUR",
        time=base + timedelta(hours=30),
        open=100, high=132, low=100, close=130,
        volume=50_000, secid="AAA",
    ))
    out.append(Candle(
        interval="CANDLE_INTERVAL_HOUR",
        time=base + timedelta(hours=31),
        open=110, high=112, low=109, close=111,
        volume=1_000, secid="AAA",
    ))
    return out


def test_entry_fills_at_next_open_not_signal_close():
    config = _sample_config()
    candles = {"AAA": _breakout_then_gap_open()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_020,
    )
    entries = [t for t in result.trades if t.get("kind") == "entry"]
    assert entries, "expected a momentum breakout entry"
    fill = entries[0]
    signal_close = 130.0
    next_open = 110.0
    expected = next_open * (1.0 + config.risk.slippage_pct / 100.0)
    assert abs(float(fill["price"]) - expected) < 1e-6
    assert abs(float(fill["price"]) - signal_close) > 1.0
    assert fill["bar_time"] == candles["AAA"][-1].time.isoformat()


def test_fetch_moex_index_tickers_sends_as_of_date():
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.robots_v2.universe.index_provider import fetch_moex_index_tickers

    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"tickers": {"columns": ["ticker"], "data": [["SBER"], ["GAZP"]]}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            captured["params"] = params
            return _Resp()

    class _Gate:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    with patch("app.modules.robots_v2.universe.index_provider.httpx.AsyncClient", return_value=_Client()), patch(
        "app.modules.robots_v2.universe.index_provider.moex_http_acquire", return_value=_Gate(),
    ):
        out = asyncio.run(fetch_moex_index_tickers("IMOEX", as_of=date(2024, 3, 1)))
    assert captured["params"]["date"] == "2024-03-01"
    assert out == ["GAZP", "SBER"]


def test_point_in_time_screen_drops_names_without_history():
    from datetime import date
    from unittest.mock import MagicMock, patch

    from app.modules.robots_v2.universe.service import _apply_point_in_time_screen

    rows = [{"ticker": "OLD", "last_price": 999}, {"ticker": "NEW", "last_price": 999}]
    with patch(
        "app.modules.robots.trading.pipeline.historical_liquidity.point_in_time_metrics",
        return_value={"OLD": {"last_close": 12.5, "avg_value": 8_000_000}},
    ):
        kept, rejected = _apply_point_in_time_screen(
            MagicMock(), rows, as_of=date(2024, 6, 1), market="moex",
        )
    assert [r["ticker"] for r in kept] == ["OLD"]
    assert kept[0]["last_price"] == 12.5
    assert rejected[0].code == "NO_HISTORY"
    assert rejected[0].ticker == "NEW"
