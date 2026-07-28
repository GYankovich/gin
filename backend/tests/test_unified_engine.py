"""Тесты унифицированной архитектуры BRD-ARCH-03.

Покрывают новые модули:
- `contracts.py` (Candle, Position, RiskParams normalize)
- `risk.manager.RiskManager`
- `pipeline.runner.PipelineRunner`
- `engines.backtest.BacktestEngine` + `engines.live.LiveTradingEngine` (parity)
- стратегии momentum_breakout, reversion_to_ma
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List

import pytest

from app.modules.robots.trading.contracts import (
    Candle,
    MarketSnapshot,
    Position,
    Signal,
    SnapshotRow,
)
from app.modules.robots.trading.data_provider.base import DataProvider
from app.modules.robots.trading.engines.backtest import BacktestEngine
from app.modules.robots.trading.engines.context import RuntimeContext
from app.modules.robots.trading.engines.live import LiveTradingEngine
from app.modules.robots.trading.execution.sim import SimExecution
from app.modules.robots.trading.pipeline.runner import PipelineRunner
from app.modules.robots.trading.recorder import MemoryRecorder
from app.modules.robots.trading.risk import RiskManager, RiskParams
from app.modules.robots.trading.strategies.momentum_breakout import MomentumBreakoutStrategy
from app.modules.robots.trading.strategies.reversion_to_ma import ReversionToMaStrategy


# ---------------------------------------------------------------------------
# Контракты
# ---------------------------------------------------------------------------

def test_candle_from_moex_row():
    row = {"bucket_start": datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
           "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000}
    c = Candle.from_moex_row(row, interval="M5", secid="SBER")
    assert c.open == 100.0 and c.close == 105.0
    assert c.secid == "SBER"


def test_candle_from_tinvest_dict():
    raw = {"time": "2024-01-01T10:00:00+00:00",
           "open": {"units": 100, "nano": 500_000_000},
           "high": {"units": 110, "nano": 0},
           "low": {"units": 95, "nano": 0},
           "close": {"units": 105, "nano": 0},
           "volume": 1000}
    c = Candle.from_tinvest_dict(raw, interval="M5", figi="BBG")
    assert c.open == 100.5
    assert c.figi == "BBG"


def test_risk_params_normalize_legacy_fields():
    rp = RiskParams.from_legacy_dict({
        "stop_loss_percent": 1.5,
        "take_profit_percent": 2.5,
        "max_position_percent": 25.0,
        "max_daily_loss": 5000.0,
    })
    assert rp.effective_stop_loss_pct == 1.5
    assert rp.effective_take_profit_pct == 2.5
    assert rp.effective_max_position_pct == 25.0
    assert rp.effective_max_daily_loss_rub == 5000.0


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

def test_risk_manager_compute_quantity_respects_max_position_pct():
    rm = RiskManager(RiskParams(max_position_pct=20.0, max_position_rub=0.0,
                                  free_funds_reserve_pct=0.0))
    sig = Signal(secid="SBER", side="BUY", target_price=100.0)
    qty = rm.compute_quantity(sig, cash=100_000, equity=100_000, entry_price=100.0)
    assert qty == 200  # 20% от 100k / 100 = 200


def test_risk_manager_pre_trade_check_blocks_when_too_many_positions():
    rm = RiskManager(RiskParams(max_concurrent_positions=1, max_position_pct=50.0))
    rm.begin_day(equity_at_open=100_000)
    sig = Signal(secid="GAZP", side="BUY", target_price=200.0)
    positions = {"SBER": Position(secid="SBER", quantity=10, avg_entry_price=100.0, side="LONG",
                                    opened_at=datetime.now(timezone.utc))}
    res = rm.pre_trade_check(sig, cash=50_000, equity=100_000, positions=positions)
    assert not res.allow
    assert res.reason == "max_concurrent_positions"


def test_risk_manager_fixed_stop_loss():
    rm = RiskManager(RiskParams(stop_loss_pct=2.0, stop_loss_mode="fixed"))
    pos = Position(secid="SBER", side="LONG", quantity=10, avg_entry_price=100.0,
                    opened_at=datetime.now(timezone.utc))
    bar = Candle(interval="M5", time=datetime.now(timezone.utc),
                  open=99.0, high=99.5, low=97.5, close=98.0, volume=100)
    sig = rm.evaluate_exits(pos, bar)
    assert sig is not None and sig.side == "CLOSE"
    assert sig.reason == "stop_loss"
    assert abs(sig.target_price - 98.0) < 1e-6  # SL = 100 * 0.98


def test_risk_manager_force_close_at_eod():
    rm = RiskManager(RiskParams(force_close_time="18:45"))
    pos = Position(secid="SBER", side="LONG", quantity=10, avg_entry_price=100.0,
                    current_price=100.0, opened_at=datetime.now(timezone.utc))
    now_msk = datetime(2024, 1, 1, 18, 50, tzinfo=timezone.utc)
    sigs = rm.force_close_signals(now_msk, {"SBER": pos})
    assert len(sigs) == 1 and sigs[0].reason == "force_market_flatten_eod"

    earlier = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert rm.force_close_signals(earlier, {"SBER": pos}) == []


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------

def test_pipeline_runner_filters_by_volume_and_gap():
    runner = PipelineRunner([
        {"type": "volume", "min": 1_000_000},
        {"type": "gap", "max_percent": 2.5},
    ], mode="ALL")
    rows = [
        {"ticker": "SBER", "open_price": 100, "prev_price": 100, "value_today": 5_000_000,
         "security_status": "A", "trading_status": "T"},
        {"ticker": "GAZP", "open_price": 110, "prev_price": 100, "value_today": 5_000_000,
         "security_status": "A", "trading_status": "T"},  # gap 10%
        {"ticker": "LKOH", "open_price": 100, "prev_price": 100, "value_today": 500,
         "security_status": "A", "trading_status": "T"},  # volume < 1M
    ]
    res = runner.run(rows)
    assert res.accepted == ["SBER"]
    assert {t for t, _ in res.rejected} == {"GAZP", "LKOH"}


def test_pipeline_runner_accepts_market_snapshot():
    rows = {
        "SBER": SnapshotRow(secid="SBER", last_price=100, volume_rub=10_000_000,
                              security_status="A", trading_status="T"),
    }
    snap = MarketSnapshot(as_of=datetime.now(timezone.utc), trade_date=date.today(),
                            board="TQBR", rows=rows)
    runner = PipelineRunner([
        {"type": "volume", "min": 1_000_000},
        {"type": "security_status", "eq": "A"},
        {"type": "trading_status", "eq": "T"},
    ])
    res = runner.run(snap)
    assert res.accepted == ["SBER"]


# ---------------------------------------------------------------------------
# Стратегии
# ---------------------------------------------------------------------------

def _build_quotation(v: float) -> Dict[str, int]:
    units = int(v)
    return {"units": units, "nano": int(round((v - units) * 1e9))}


def _mk_candle(t: datetime, o: float, h: float, l: float, c: float, v: int) -> Dict[str, Any]:
    return {"time": t.isoformat(), "open": _build_quotation(o), "high": _build_quotation(h),
            "low": _build_quotation(l), "close": _build_quotation(c), "volume": v}


def test_momentum_breakout_emits_buy_on_breakout():
    candles: List[Dict[str, Any]] = []
    t0 = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    for d in range(5):
        candles.append(_mk_candle(t0 + timedelta(days=d), 100, 105, 95, 100, 1000))
    for i in range(3):
        ts = datetime(2024, 1, 7, 10, i * 10, tzinfo=timezone.utc)
        candles.append(_mk_candle(ts, 108 + i, 112 + i, 107, 110 + i, 1000 if i == 0 else 3000))
    strat = MomentumBreakoutStrategy(client=None, params={
        "figis": ["F1"], "lookback_days": 5,
        "entry_minutes_from_open": 30, "volume_multiplier": 1.2,
    })
    out = asyncio.run(strat.generate_signals({"F1": candles}))
    assert out["F1"] == "BUY"


def test_reversion_to_ma_emits_buy_on_dip():
    candles: List[Dict[str, Any]] = []
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(40):
        candles.append(_mk_candle(base + timedelta(minutes=i * 5), 100, 101, 99, 100, 1000))
    candles[-1] = _mk_candle(base + timedelta(minutes=39 * 5), 100, 100, 94, 95, 1000)
    strat = ReversionToMaStrategy(client=None, params={
        "figis": ["F1"], "ma_period": 20, "deviation_pct": 2,
        "rsi_period": 14, "rsi_oversold": 50, "use_volume_filter": False,
    })
    out = asyncio.run(strat.generate_signals({"F1": candles}))
    assert out["F1"] == "BUY"


# ---------------------------------------------------------------------------
# BacktestEngine end-to-end
# ---------------------------------------------------------------------------

class _FakeData(DataProvider):
    def __init__(self, secid: str = "SBER"):
        self.secid = secid

    async def list_universe(self, trade_date):
        return [self.secid]

    async def get_daily_summary(self, secids, trade_date):
        rows = {
            s: SnapshotRow(secid=s, last_price=100, volume_rub=10_000_000,
                             security_status="A", trading_status="T")
            for s in secids
        }
        return MarketSnapshot(
            as_of=datetime.combine(trade_date, time(10, 0), tzinfo=timezone.utc),
            trade_date=trade_date, board="TQBR", rows=rows,
        )

    async def get_daily_candles(self, secid, from_d, to_d):
        return []

    async def get_intraday_candles(self, secid, day, interval):
        base = datetime.combine(day, time(10, 0), tzinfo=timezone.utc)
        out = [
            Candle(interval="M5", time=base + timedelta(minutes=5 * i),
                    open=100, high=101, low=99, close=100, volume=1000, secid=secid)
            for i in range(40)
        ]
        out[-1] = Candle(
            interval="M5", time=out[-1].time,
            open=100, high=100, low=94, close=95, volume=1000, secid=secid,
        )
        return out


def test_backtest_engine_executes_buy_on_dip():
    risk = RiskManager(RiskParams(
        stop_loss_pct=2.0, take_profit_pct=3.0,
        max_concurrent_positions=2, max_daily_loss_rub=10_000,
        max_position_pct=20.0, day_loss_streak_limit=0,
    ))
    ctx = RuntimeContext(
        mode="BACKTEST",
        data=_FakeData(),
        pipeline=PipelineRunner([
            {"type": "volume", "min": 1_000_000},
            {"type": "security_status", "eq": "A"},
            {"type": "trading_status", "eq": "T"},
        ]),
        strategy=ReversionToMaStrategy(client=None, params={
            "figis": ["SBER"], "ma_period": 20, "deviation_pct": 2.0,
            "rsi_period": 14, "rsi_oversold": 50, "use_volume_filter": False,
        }),
        risk=risk,
        execution=SimExecution(execution_model="CURRENT_BAR_CLOSE",
                                slippage_pct=0.0, commission_rate=0.0005),
        recorder=MemoryRecorder(),
    )
    engine = BacktestEngine(ctx)
    res = asyncio.run(
        engine.run(from_date=date(2024, 1, 2), to_date=date(2024, 1, 2),
                    initial_capital=100_000, intraday_interval="M5")
    )
    assert len(res.trades) >= 1
    t = res.trades[0]
    assert t["side"] == "BUY"
    assert t["price"] == 95.0
    assert "SBER" in ctx.positions


def test_engine_mode_guard_enforced():
    rm = RiskManager(RiskParams())
    ctx = RuntimeContext(
        mode="LIVE",
        data=_FakeData(),
        pipeline=PipelineRunner([]),
        strategy=ReversionToMaStrategy(client=None, params={"figis": ["SBER"]}),
        risk=rm,
        execution=SimExecution(),
        recorder=MemoryRecorder(),
    )
    with pytest.raises(ValueError):
        BacktestEngine(ctx)

    ctx2 = RuntimeContext(
        mode="BACKTEST",
        data=_FakeData(),
        pipeline=PipelineRunner([]),
        strategy=ReversionToMaStrategy(client=None, params={"figis": ["SBER"]}),
        risk=rm,
        execution=SimExecution(),
        recorder=MemoryRecorder(),
    )
    with pytest.raises(ValueError):
        LiveTradingEngine(ctx2)
