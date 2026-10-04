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
    assert isinstance(result.signals, list)
    assert isinstance(result.daily_summary, list)


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
             "qty": 10, "price": 250.0, "pnl": None, "cycle_id": "cid-1",
             "signal_time": "2025-01-02T09:00:00+00:00"},
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
    assert trades[0]["cycle_id"] == "cid-1"
    assert trades[0]["signal_time"] == "2025-01-02T09:00:00+00:00"
    assert orders[0]["cycle_id"] == "cid-1"
    assert trades[1]["reason"] == "stop_loss"
    assert "cycle_id" not in trades[1]
    assert orders[1]["reason"] == "stop_loss"


def test_build_observability_reject_and_status_counts():
    from app.modules.robots_v2.backtest.persist import REJECT_REASON_TOP_N, build_observability

    signals = [
        {"status": "rejected", "reject_reason": "RISK_BLOCK", "was_executed": 0},
        {"status": "rejected", "reject_reason": "RISK_BLOCK", "was_executed": 0},
        {"status": "rejected", "reject_reason": "ZERO_QTY", "was_executed": 0},
        {"status": "deferred", "was_executed": 0},
        {"status": "filled", "was_executed": 1},
        {"status": "submitted", "was_executed": 1},
        # Spurious reject_reason on filled must not enter reject lens.
        {"status": "filled", "reject_reason": "SHOULD_IGNORE", "was_executed": 1},
        # Unknown status buckets into rejected.
        {"status": "cancelled", "reject_reason": "USER_CANCEL", "was_executed": 0},
    ]
    for i in range(10):
        signals.append({
            "status": "rejected",
            "reject_reason": f"CODE_{i}",
            "was_executed": 0,
        })
    obs = build_observability(
        signals,
        history_stats={"signals": len(signals), "signals_truncated": 1},
    )
    assert obs["execution_model"]["code"] == "NEXT_BAR_OPEN"
    assert obs["execution_model"]["look_ahead"] is False
    assert obs["signals_truncated"] is True
    assert obs["signals_logged"] == len(signals)
    assert obs["signal_log_cap"] == 25_000
    assert obs["status_counts"]["filled"] == 3
    assert obs["status_counts"]["deferred"] == 1
    assert obs["status_counts"]["rejected"] == 14
    assert sum(obs["status_counts"].values()) == len(signals)
    assert len(obs["reject_reason_counts"]) == REJECT_REASON_TOP_N
    assert obs["reject_reason_counts"][0]["code"] == "RISK_BLOCK"
    assert obs["reject_reason_counts"][0]["count"] == 2
    assert all(row["code"] != "SHOULD_IGNORE" for row in obs["reject_reason_counts"])


def test_filter_and_paginate_signals():
    from app.modules.robots_v2.backtest.persist import (
        DETAILS_SIGNALS_INLINE_CAP,
        apply_signals_page_to_details,
        enrich_run_observability,
        filter_signals,
        paginate_signals,
    )

    signals = [
        {"figi": "SBER", "status": "rejected", "reject_reason": "RISK_BLOCK", "cycle_id": "a"},
        {"figi": "GAZP", "status": "filled", "reject_reason": None, "cycle_id": "b"},
        {"figi": "SBER", "status": "deferred", "reject_reason": None, "cycle_id": "c"},
        {"figi": "VTBR", "status": "submitted", "reject_reason": None, "cycle_id": "d"},
    ]
    filtered = filter_signals(signals, status="rejected", reject_reason="RISK_BLOCK")
    assert len(filtered) == 1
    assert filtered[0]["figi"] == "SBER"
    # submitted normalizes to filled — filter must match both.
    filled = filter_signals(signals, status="submitted")
    assert {s["figi"] for s in filled} == {"GAZP", "VTBR"}
    page, total = paginate_signals(signals, limit=2, offset=1)
    assert total == 4
    assert len(page) == 2
    assert page[0]["figi"] == "GAZP"

    # Soft-degrade: details still returns when cycle_id absent on old rows.
    legacy = {
        "signals": [{"figi": "X", "status": "rejected", "reject_reason": "RISK_BLOCK"}],
        "result_payload": {"trades": [{"id": 1, "figi": "X"}], "history_stats": {}},
        "orders": [],
        "execution_model": {"model": "BAR_CLOSE", "look_ahead": True},
    }
    apply_signals_page_to_details(legacy)
    assert legacy["observability"]["execution_model"]["code"] == "NEXT_BAR_OPEN"
    assert legacy["observability"]["execution_model"]["look_ahead"] is False
    assert legacy["execution_model"]["model"] == "NEXT_BAR_OPEN"
    assert legacy["signals"][0].get("linked_trade_ids") == []

    # Stored observability with dishonest banner is rewritten on read.
    dishonest = {
        "signals": [],
        "result_payload": {
            "trades": [],
            "history_stats": {},
            "observability": {
                "execution_model": {"code": "BAR_CLOSE", "label": "bar close", "look_ahead": True},
                "signals_logged": 0,
                "signals_truncated": False,
                "signal_log_cap": 25000,
                "reject_reason_counts": [],
                "status_counts": {"filled": 0, "rejected": 0, "deferred": 0},
            },
        },
        "orders": [],
        "execution_model": {"model": "BAR_CLOSE"},
    }
    enrich_run_observability(dishonest)
    assert dishonest["observability"]["execution_model"]["code"] == "NEXT_BAR_OPEN"
    assert dishonest["execution_model"]["model"] == "NEXT_BAR_OPEN"

    big = {
        "signals": [
            {"figi": "T", "status": "rejected", "reject_reason": "RISK_BLOCK", "cycle_id": f"c{i}"}
            for i in range(DETAILS_SIGNALS_INLINE_CAP + 3)
        ],
        "result_payload": {
            "trades": [],
            "history_stats": {"signals": DETAILS_SIGNALS_INLINE_CAP + 3},
            "observability": {
                "execution_model": {"code": "NEXT_BAR_OPEN", "label": "x", "look_ahead": False},
                "signals_logged": DETAILS_SIGNALS_INLINE_CAP + 3,
                "signals_truncated": False,
                "signal_log_cap": 25000,
                "reject_reason_counts": [{"code": "RISK_BLOCK", "count": DETAILS_SIGNALS_INLINE_CAP + 3}],
                "status_counts": {"filled": 0, "rejected": DETAILS_SIGNALS_INLINE_CAP + 3, "deferred": 0},
            },
        },
        "orders": [],
    }
    apply_signals_page_to_details(big)
    assert big["signals"] == []
    assert big["signals_total"] == DETAILS_SIGNALS_INLINE_CAP + 3
    assert big["signals_truncated_inline"] is True

    # Restore full signal list for filtered page (details would re-load from DB in prod).
    big["signals"] = [
        {"figi": "T", "status": "rejected", "reject_reason": "RISK_BLOCK", "cycle_id": f"c{i}"}
        for i in range(DETAILS_SIGNALS_INLINE_CAP + 3)
    ]
    apply_signals_page_to_details(
        big,
        signals_limit=10,
        signals_offset=0,
        reject_reason="RISK_BLOCK",
    )
    assert len(big["signals"]) == 10
    assert big["signals_total"] == DETAILS_SIGNALS_INLINE_CAP + 3


def test_deferred_reject_not_requeued():
    """Priced deferred intents that reject must not stay in the leftover queue."""
    from app.modules.trading_core.contracts import OrderIntent
    from app.modules.robots_v2.backtest.host import _apply_deferred_intents
    from app.modules.robots_v2.engine.execution import ExecutionService
    from app.modules.robots_v2.engine.paper_ledger import PaperLedger
    from app.modules.robots_v2.risk.engine import RiskEngine
    from app.modules.robots_v2.strategy.runtime import StrategyRuntime

    config = _sample_config()
    ledger = PaperLedger(cash=100_000, commission_rate=0.0005, allow_short=False)
    risk = RiskEngine(config.risk, allow_short=False)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, quiet=True)
    intent = OrderIntent(
        kind="entry",
        figi="SBER",
        side="BUY",
        quantity=0,  # INVALID_QTY → rejected
        price=100.0,
        reason="momentum_breakout",
        meta={"cycle_id": "cid-x", "signal_time": "2025-01-02T10:00:00+00:00"},
    )
    fills, leftover, events = _apply_deferred_intents(
        [intent],
        opens={"SBER": 100.0},
        exec_svc=exec_svc,
        risk=risk,
        runtime=StrategyRuntime(),
        session_id=1,
        archetype="momentum",
        clock=datetime(2025, 1, 2, 11, 0, tzinfo=timezone.utc),
    )
    assert fills == []
    assert leftover == []
    assert any(e.get("status") == "rejected" for e in events)


def test_entry_fills_stamp_cycle_id_across_next_open():
    config = _sample_config()
    candles = {"AAA": _breakout_then_gap_open()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_021,
    )
    entries = [t for t in result.trades if t.get("kind") == "entry"]
    assert entries, "expected a momentum breakout entry"
    fill = entries[0]
    assert fill.get("cycle_id"), "next-open fill must carry originating cycle_id"
    assert fill.get("signal_time"), "next-open fill should keep intent signal_time"
    # After next-open fill, originating deferred signal is promoted to filled.
    filled_signals = [
        s for s in result.signals
        if s.get("kind") == "entry" and s.get("status") == "filled" and s.get("cycle_id") == fill["cycle_id"]
    ]
    assert filled_signals, "deferred entry signal must promote to filled after next-open fill"
    assert not any(
        s.get("kind") == "entry"
        and s.get("status") == "deferred"
        and s.get("cycle_id") == fill["cycle_id"]
        for s in result.signals
    )


def test_status_counts_filled_after_next_open_and_enrich():
    """Reject-lens «Исполнено» must count next-open fills, not stuck deferred signals."""
    from app.modules.robots_v2.backtest.persist import (
        build_observability,
        enrich_run_observability,
        promote_deferred_signals_to_filled,
    )

    config = _sample_config()
    candles = {"AAA": _breakout_then_gap_open()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_032,
    )
    n_trades = len(result.trades)
    assert n_trades >= 1
    obs = build_observability(result.signals, history_stats=result.history_stats)
    assert obs["status_counts"]["filled"] >= n_trades
    assert obs["status_counts"]["deferred"] == 0 or obs["status_counts"]["filled"] >= 1

    # Legacy payload: signals still say deferred while execution_events show filled.
    legacy_signals = [
        {
            "figi": "AAA",
            "status": "deferred",
            "kind": "entry",
            "cycle_id": "c-legacy",
            "intent_id": "i-legacy",
            "was_executed": 0,
        },
        {
            "figi": "AAA",
            "status": "rejected",
            "reject_reason": "RISK_BLOCK",
            "kind": "entry",
            "cycle_id": "c-rej",
            "was_executed": 0,
        },
    ]
    assert promote_deferred_signals_to_filled(
        legacy_signals,
        execution_events=[
            {"intent_id": "i-legacy", "cycle_id": "c-legacy", "ticker": "AAA", "status": "filled"},
        ],
    ) == 1
    assert legacy_signals[0]["status"] == "filled"
    assert legacy_signals[0]["was_executed"] == 1

    stuck = {
        "signals": [
            {
                "figi": "AAA",
                "status": "deferred",
                "kind": "entry",
                "cycle_id": "c1",
                "was_executed": 0,
            },
        ],
        "execution_events": [
            {"intent_id": "x", "cycle_id": "c1", "ticker": "AAA", "kind": "entry", "status": "filled"},
        ],
        "result_payload": {
            "trades": [{"id": 1, "figi": "AAA", "side": "BUY", "price": 1, "quantity": 1, "cycle_id": "c1", "kind": "entry"}],
            "history_stats": {"signals": 1},
            "observability": {
                "execution_model": {"code": "NEXT_BAR_OPEN", "label": "x", "look_ahead": False},
                "signals_logged": 1,
                "signals_truncated": False,
                "signal_log_cap": 25000,
                "reject_reason_counts": [],
                "status_counts": {"filled": 0, "rejected": 0, "deferred": 1},
            },
        },
        "execution_model": {"model": "NEXT_BAR_OPEN", "look_ahead": False},
        "orders": [],
    }
    enrich_run_observability(stuck)
    assert stuck["signals"][0]["status"] == "filled"
    assert stuck["observability"]["status_counts"]["filled"] == 1
    assert stuck["observability"]["status_counts"]["deferred"] == 0


def test_create_db_run_execution_model_is_next_bar_open():
    from app.modules.robots_v2.backtest.persist import NEXT_BAR_OPEN_EXECUTION_MODEL

    assert NEXT_BAR_OPEN_EXECUTION_MODEL["model"] == "NEXT_BAR_OPEN"
    assert NEXT_BAR_OPEN_EXECUTION_MODEL["look_ahead"] is False
    assert NEXT_BAR_OPEN_EXECUTION_MODEL["fill_on"] == "NEXT_BAR_OPEN"


def test_fee_summary_and_holdings_on_host_result():
    from app.modules.robots_v2.backtest.host import build_fee_summary

    fee = build_fee_summary(
        [{"commission": 1.5}, {"commission": 2.5}, {"commission": None}],
        funding_total=3.25,
        funding_events=2,
        tax_total=0.1,
    )
    assert fee["commission_total"] == 4.0
    assert fee["funding_total"] == 3.25
    assert fee["funding_events"] == 2
    assert fee["tax_total"] == 0.1

    config = _sample_config()
    candles = {"AAA": _breakout_then_gap_open()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_022,
    )
    assert isinstance(result.fee_summary, dict)
    assert "commission_total" in result.fee_summary
    assert result.fee_summary["funding_events"] == 0
    assert result.portfolio_snapshots, "expected equity/holdings snapshots"
    last = result.portfolio_snapshots[-1]
    assert isinstance(last["positions"], list)
    assert "positions_count" in last
    if last["positions"]:
        h = last["positions"][0]
        assert {"ticker", "qty", "side", "avg_entry", "mark"} <= set(h.keys())


def test_cycle_inspector_bundle_and_snapshot_normalize():
    from app.modules.robots_v2.backtest.persist import (
        build_cycle_inspector_bundle,
        _normalize_snapshot_positions,
    )
    from app.modules.robots_v2.backtest.schemas import (
        RobotV2BacktestCycleBundleResponse,
        RobotV2BacktestStatusResponse,
    )

    run = {
        "signals": [
            {"cycle_id": "c1", "figi": "SBER", "status": "deferred", "kind": "entry"},
            {"cycle_id": "c2", "figi": "GAZP", "status": "rejected"},
        ],
        "orders": [{"cycle_id": "c1", "ticker": "SBER", "id": 9}],
        "result_payload": {
            "trades": [{"id": 9, "cycle_id": "c1", "figi": "SBER", "side": "BUY", "price": 1, "quantity": 1}],
        },
        "config_snapshot": {
            "strategy": {"archetype": "momentum", "timeframe": "1h"},
            "risk": {"stopLossPct": 5, "takeProfitPct": 10, "maxPositionSharePct": 20},
        },
    }
    bundle = build_cycle_inspector_bundle(run, "c1")
    assert bundle is not None
    assert len(bundle["signals"]) == 1
    assert len(bundle["trades"]) == 1
    assert len(bundle["orders"]) == 1
    assert bundle["config_risk_excerpt"]["archetype"] == "momentum"
    assert bundle["config_risk_excerpt"]["stopLossPct"] == 5
    assert build_cycle_inspector_bundle(run, "missing") is None
    RobotV2BacktestCycleBundleResponse.model_validate(bundle)

    holdings, count = _normalize_snapshot_positions({
        "positions": [{"ticker": "SBER", "qty": 10, "side": "long", "avg_entry": 1, "mark": 2}],
        "positions_count": 1,
    })
    assert count == 1
    assert holdings[0]["ticker"] == "SBER"
    holdings2, count2 = _normalize_snapshot_positions({"positions": 3})
    assert holdings2 == []
    assert count2 == 3

    status = RobotV2BacktestStatusResponse.model_validate({
        "run_id": 1,
        "status": "CANCELLED",
        "requested_from": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "requested_to": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "started_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "partial_result": True,
    })
    assert status.partial_result is True


def test_persist_universe_membership_sql_params():
    from datetime import date
    from unittest.mock import MagicMock

    from app.modules.robots_v2.backtest.persist import persist_universe_membership

    db = MagicMock()
    db.execute.return_value = MagicMock()
    persist_universe_membership(
        db,
        42,
        {
            date(2025, 1, 2): ["sber", "GAZP"],
            "2025-01-03": ["VTBR"],
        },
    )
    # DELETE + 3 INSERTs + commits
    assert db.execute.call_count >= 4
    inserted = [
        call.kwargs if call.kwargs else call.args[1]
        for call in db.execute.call_args_list
        if call.args and "INSERT INTO backtest_universe_membership" in str(call.args[0])
    ]
    assert len(inserted) == 3
    tickers = {row["ticker"] for row in inserted}
    assert tickers == {"SBER", "GAZP", "VTBR"}


def test_p2_lifecycle_narrative_and_price_window():
    from unittest.mock import MagicMock, patch

    from app.modules.robots_v2.backtest.host import build_run_narrative
    from app.modules.robots_v2.backtest.persist import (
        build_cycle_inspector_bundle,
        persist_execution_events,
    )
    from app.modules.robots_v2.backtest.price_window import fetch_price_window
    from app.modules.robots_v2.backtest.schemas import (
        RobotV2BacktestExecutionEventsResponse,
        RobotV2BacktestNarrativeResponse,
        RobotV2BacktestPriceWindowResponse,
    )

    config = _sample_config()
    candles = {"AAA": _breakout_then_gap_open()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_030,
    )
    assert result.narrative, "P2 narrative must be non-empty for new runs"
    assert any(s.get("section") == "итог" for s in result.narrative)
    assert any("без заглядывания" in (s.get("text") or "") for s in result.narrative)

    statuses = {e.get("status") for e in result.execution_events}
    assert "deferred" in statuses
    assert "filled" in statuses
    assert result.execution_events
    assert all(e.get("intent_id") for e in result.execution_events)

    # Lifecycle linkage: deferred and fill share intent_id for same cycle.
    fill_ev = next(e for e in result.execution_events if e.get("status") == "filled")
    deferred_ev = [
        e for e in result.execution_events
        if e.get("status") == "deferred" and e.get("intent_id") == fill_ev["intent_id"]
    ]
    assert deferred_ev, "fill must link back to deferred intent via intent_id"

    narrative = build_run_narrative(
        initial_capital=100_000,
        final_equity=101_000,
        total_return_percent=1.0,
        max_drawdown_percent=0.5,
        history_stats={"bars": 10, "tickers": 1, "trades": 1, "signals": 2, "dropped_deferred": 1},
        fee_summary={"commission_total": 1.0, "funding_total": 0.0},
    )
    RobotV2BacktestNarrativeResponse.model_validate({"run_id": 1, "items": narrative, "total": len(narrative)})

    db = MagicMock()
    db.execute.return_value = MagicMock()
    persist_execution_events(db, 7, result.execution_events[:3])
    assert any(
        call.args and "INSERT INTO backtest_execution_events" in str(call.args[0])
        for call in db.execute.call_args_list
    )

    bundle = build_cycle_inspector_bundle(
        {
            "signals": [{"cycle_id": fill_ev["cycle_id"], "figi": "AAA"}],
            "orders": [],
            "result_payload": {"trades": []},
            "execution_events": [fill_ev, *deferred_ev],
            "config_snapshot": {},
        },
        str(fill_ev["cycle_id"]),
    )
    assert bundle is not None
    assert bundle["execution_events"]

    RobotV2BacktestExecutionEventsResponse.model_validate({
        "run_id": 1,
        "items": result.execution_events[:2],
        "total": 2,
    })

    fake_series = [
        {
            "time": (datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat(),
            "open": {"units": 100 + i, "nano": 0},
            "high": {"units": 101 + i, "nano": 0},
            "low": {"units": 99 + i, "nano": 0},
            "close": {"units": 100 + i, "nano": 0},
            "volume": 1000,
        }
        for i in range(20)
    ]
    with patch(
        "app.modules.robots_v2.backtest.price_window.load_candles_by_symbol_from_cache",
        return_value={"AAA": fake_series},
    ):
        win = fetch_price_window(
            MagicMock(),
            config_snapshot=config.model_dump(by_alias=True),
            ticker="AAA",
            around=datetime(2025, 1, 2, 15, 0, tzinfo=timezone.utc),
            bars=5,
        )
    assert win["gap"] is None
    assert win["ticker"] == "AAA"
    assert len(win["candles"]) > 0
    RobotV2BacktestPriceWindowResponse.model_validate({"run_id": 1, **win})

    with patch(
        "app.modules.robots_v2.backtest.price_window.load_candles_by_symbol_from_cache",
        return_value={},
    ):
        empty = fetch_price_window(
            MagicMock(),
            config_snapshot=config.model_dump(by_alias=True),
            ticker="ZZZ",
            around=datetime(2025, 1, 2, 15, 0, tzinfo=timezone.utc),
            bars=5,
        )
    assert empty["candles"] == []
    assert empty["gap"] and "no_candles" in empty["gap"]


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


def _breakout_on_last_bar() -> list[Candle]:
    """Warmup + breakout close on the final bar (no next open → DROPPED_DEFERRED)."""
    bars = _breakout_then_gap_open()
    return bars[:-1]


def test_dropped_deferred_lifecycle_at_run_end():
    """P2: deferred intents without a next bar emit DROPPED_DEFERRED + status=dropped."""
    config = _sample_config()
    candles = {"AAA": _breakout_on_last_bar()}
    result = BacktestHost().run_sync(
        config=config,
        universe=["AAA"],
        candles_by_ticker=candles,
        initial_capital=100_000,
        session_id=999_031,
    )
    assert int(result.history_stats.get("dropped_deferred") or 0) >= 1
    dropped_signals = [
        s for s in result.signals
        if s.get("reject_reason") == "DROPPED_DEFERRED"
    ]
    assert dropped_signals, "end-of-run must surface DROPPED_DEFERRED reject signals"
    assert all(s.get("status") == "rejected" for s in dropped_signals)

    dropped_events = [
        e for e in result.execution_events
        if e.get("status") == "dropped" and e.get("reject_reason") == "DROPPED_DEFERRED"
    ]
    assert dropped_events, "execution_events must include dropped lifecycle rows"
    assert all(e.get("intent_id") for e in dropped_events)

    # Reject lens must count DROPPED_DEFERRED.
    from app.modules.robots_v2.backtest.persist import build_observability

    obs = build_observability(result.signals, history_stats=result.history_stats)
    codes = {row["code"]: row["count"] for row in obs["reject_reason_counts"]}
    assert codes.get("DROPPED_DEFERRED", 0) >= 1


def test_filter_signals_by_ticker_and_cycle_id():
    from app.modules.robots_v2.backtest.persist import filter_signals

    signals = [
        {"figi": "SBER", "status": "rejected", "reject_reason": "RISK_BLOCK", "cycle_id": "a"},
        {"figi": "gazp", "status": "filled", "cycle_id": "b"},
        {"ticker": "SBER", "status": "deferred", "cycle_id": "c"},
    ]
    by_ticker = filter_signals(signals, ticker="sber")
    assert len(by_ticker) == 2
    by_cycle = filter_signals(signals, cycle_id="b")
    assert len(by_cycle) == 1
    assert by_cycle[0]["figi"] == "gazp"
    combo = filter_signals(signals, ticker="SBER", status="deferred")
    assert len(combo) == 1
    assert combo[0]["cycle_id"] == "c"


def test_load_universe_membership_date_filters():
    from datetime import date
    from unittest.mock import MagicMock

    from app.modules.robots_v2.backtest.persist import load_universe_membership
    from app.modules.robots_v2.backtest.schemas import RobotV2BacktestUniverseResponse

    db = MagicMock()
    mapping_rows = [
        {
            "trade_date": date(2025, 1, 2),
            "ticker": "SBER",
            "source": "fixed",
            "filter_result": "kept",
            "reject_reason": None,
        },
        {
            "trade_date": date(2025, 1, 3),
            "ticker": "GAZP",
            "source": "fixed",
            "filter_result": "kept",
            "reject_reason": None,
        },
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = mapping_rows
    db.execute.return_value = result

    items = load_universe_membership(
        db, 9, from_date=date(2025, 1, 2), to_date=date(2025, 1, 3),
    )
    assert len(items) == 2
    assert items[0]["trade_date"] == "2025-01-02"
    assert items[0]["ticker"] == "SBER"
    sql = str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert "trade_date >= :from_d" in sql
    assert "trade_date <= :to_d" in sql
    assert params["from_d"] == date(2025, 1, 2)
    assert params["to_d"] == date(2025, 1, 3)
    assert params["rid"] == 9

    RobotV2BacktestUniverseResponse.model_validate({
        "run_id": 9,
        "items": items,
        "days": [date(2025, 1, 2), date(2025, 1, 3)],
        "total": len(items),
    })

    # Soft-degrade: missing table → empty list.
    db.execute.side_effect = RuntimeError("relation missing")
    assert load_universe_membership(db, 9) == []


def test_load_execution_events_cycle_filter_and_shape():
    from unittest.mock import MagicMock

    from app.modules.robots_v2.backtest.persist import load_execution_events
    from app.modules.robots_v2.backtest.schemas import RobotV2BacktestExecutionEventsResponse

    db = MagicMock()
    ts = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "id": 1,
            "event_time": ts,
            "intent_id": "i1",
            "cycle_id": "c9",
            "ticker": "AAA",
            "side": "BUY",
            "kind": "entry",
            "status": "dropped",
            "reason": "momentum_breakout",
            "reject_reason": "DROPPED_DEFERRED",
            "quantity": 10,
            "price": 110.5,
            "trade_id": None,
            "payload": {"event_id": "e1", "signal_time": "2025-01-02T11:00:00+00:00"},
        },
    ]
    db.execute.return_value = result

    items = load_execution_events(db, 11, cycle_id="c9", limit=100)
    assert len(items) == 1
    assert items[0]["status"] == "dropped"
    assert items[0]["reject_reason"] == "DROPPED_DEFERRED"
    assert items[0]["intent_id"] == "i1"
    assert items[0]["ts"] == ts.isoformat()
    assert items[0]["signal_time"] == "2025-01-02T11:00:00+00:00"
    sql = str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert "cycle_id = :cid" in sql
    assert params["cid"] == "c9"
    assert params["lim"] == 100

    RobotV2BacktestExecutionEventsResponse.model_validate({
        "run_id": 11, "items": items, "total": 1,
    })


def test_details_response_glass_box_observability_narrative_holdings():
    """GET details contract: observability, fee_summary, narrative, rich holdings."""
    from app.modules.robots_v2.backtest.persist import apply_signals_page_to_details
    from app.modules.robots_v2.backtest.schemas import RobotV2BacktestDetailsResponse

    started = datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc)
    finished = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    details = {
        "run_id": 55,
        "status": "COMPLETED",
        "requested_from": started,
        "requested_to": finished,
        "started_at": started,
        "finished_at": finished,
        "initial_capital": 100_000.0,
        "total_return_percent": 1.25,
        "max_drawdown_percent": 0.5,
        "final_equity": 101_250.0,
        "trades_total": 1,
        "execution_model": {"model": "NEXT_BAR_OPEN", "look_ahead": False},
        "signals": [
            {
                "id": 1,
                "figi": "AAA",
                "status": "rejected",
                "reject_reason": "DROPPED_DEFERRED",
                "cycle_id": "c-drop",
                "kind": "entry",
                "was_executed": 0,
            },
            {
                "id": 2,
                "figi": "AAA",
                "status": "filled",
                "cycle_id": "c-fill",
                "kind": "entry",
                "was_executed": 1,
            },
        ],
        "orders": [],
        "portfolio_snapshots": [
            {
                "time": started.isoformat(),
                "equity": 100_000.0,
                "cash": 90_000.0,
                "positions_count": 1,
                "positions": [
                    {
                        "ticker": "AAA",
                        "qty": 10,
                        "side": "long",
                        "avg_entry": 100.0,
                        "mark": 101.0,
                    },
                ],
            },
        ],
        "daily_summary": [],
        "result_payload": {
            "trades": [{"id": 2, "figi": "AAA", "side": "BUY", "price": 110, "quantity": 1, "cycle_id": "c-fill"}],
            "equity_curve": [{"time": started.isoformat(), "equity": 100_000}],
            "history_stats": {"signals": 2, "dropped_deferred": 1},
            "fee_summary": {
                "commission_total": 1.5,
                "funding_total": 0.0,
                "funding_events": 0,
                "tax_total": None,
            },
            "narrative": [
                {"section": "итог", "step": 1, "text": "Fills at next bar open, без заглядывания", "ts": finished.isoformat()},
            ],
            "observability": {
                "execution_model": {"code": "NEXT_BAR_OPEN", "label": "Fills at next bar open", "look_ahead": False},
                "signals_logged": 2,
                "signals_truncated": False,
                "signal_log_cap": 25000,
                "reject_reason_counts": [{"code": "DROPPED_DEFERRED", "count": 1}],
                "status_counts": {"filled": 1, "rejected": 1, "deferred": 0},
            },
        },
        "fee_summary": {
            "commission_total": 1.5,
            "funding_total": 0.0,
            "funding_events": 0,
        },
        "narrative": [
            {"section": "итог", "step": 1, "text": "Fills at next bar open, без заглядывания", "ts": finished.isoformat()},
        ],
        "execution_events": [
            {
                "intent_id": "i-drop",
                "cycle_id": "c-drop",
                "status": "dropped",
                "reject_reason": "DROPPED_DEFERRED",
                "ticker": "AAA",
            },
        ],
    }
    apply_signals_page_to_details(
        details,
        signals_limit=1,
        signals_offset=0,
        signals_status="rejected",
        reject_reason="DROPPED_DEFERRED",
    )
    assert details["signals_total"] == 1
    assert len(details["signals"]) == 1
    assert details["signals"][0]["reject_reason"] == "DROPPED_DEFERRED"
    assert details["observability"]["execution_model"]["code"] == "NEXT_BAR_OPEN"
    assert details["fee_summary"]["commission_total"] == 1.5
    assert details["narrative"][0]["section"] == "итог"
    holdings = details["portfolio_snapshots"][0]["positions"]
    assert holdings[0]["ticker"] == "AAA"
    assert {"qty", "side", "avg_entry", "mark"} <= set(holdings[0].keys())

    validated = RobotV2BacktestDetailsResponse.model_validate(details)
    assert validated.observability is not None
    assert validated.observability.reject_reason_counts[0].code == "DROPPED_DEFERRED"
    assert validated.fee_summary is not None
    assert validated.narrative
    assert validated.signals_total == 1


def test_service_glass_box_read_apis_with_mocks():
    """Service layer: details pagination, cycle bundle, universe, narrative, events, price-window."""
    import copy
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.robots_v2.backtest.service import BacktestService
    from app.modules.robots_v2.backtest.schemas import (
        RobotV2BacktestCycleBundleResponse,
        RobotV2BacktestDetailsResponse,
        RobotV2BacktestExecutionEventsResponse,
        RobotV2BacktestNarrativeResponse,
        RobotV2BacktestPriceWindowResponse,
        RobotV2BacktestSignalsPageResponse,
        RobotV2BacktestUniverseResponse,
    )

    started = datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc)
    finished = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    run_row = {
        "run_id": 77,
        "status": "COMPLETED",
        "requested_from": started,
        "requested_to": finished,
        "started_at": started,
        "finished_at": finished,
        "initial_capital": 100_000.0,
        "trades_total": 0,
        "config_snapshot": _sample_config().model_dump(by_alias=True),
        "execution_model": {"model": "NEXT_BAR_OPEN", "look_ahead": False},
        "signals": [
            {"figi": "SBER", "status": "rejected", "reject_reason": "RISK_BLOCK", "cycle_id": "c1"},
            {"figi": "GAZP", "status": "filled", "cycle_id": "c2", "was_executed": 1},
            {"figi": "SBER", "status": "deferred", "cycle_id": "c1"},
        ],
        "orders": [{"id": 1, "cycle_id": "c1", "ticker": "SBER"}],
        "portfolio_snapshots": [],
        "daily_summary": [],
        "result_payload": {
            "trades": [{"id": 1, "cycle_id": "c1", "figi": "SBER", "side": "BUY", "price": 1, "quantity": 1}],
            "history_stats": {"signals": 3},
            "observability": {
                "execution_model": {"code": "NEXT_BAR_OPEN", "label": "x", "look_ahead": False},
                "signals_logged": 3,
                "signals_truncated": False,
                "signal_log_cap": 25000,
                "reject_reason_counts": [{"code": "RISK_BLOCK", "count": 1}],
                "status_counts": {"filled": 1, "rejected": 1, "deferred": 1},
            },
            "fee_summary": {"commission_total": 0.5, "funding_total": 0.0, "funding_events": 0},
            "narrative": [{"section": "старт", "step": 1, "text": "ok", "ts": started.isoformat()}],
        },
        "fee_summary": {"commission_total": 0.5, "funding_total": 0.0, "funding_events": 0},
        "narrative": [{"section": "старт", "step": 1, "text": "ok", "ts": started.isoformat()}],
        "execution_events": [
            {"intent_id": "i1", "cycle_id": "c1", "status": "deferred", "ticker": "SBER"},
            {"intent_id": "i1", "cycle_id": "c1", "status": "dropped", "reject_reason": "DROPPED_DEFERRED", "ticker": "SBER"},
        ],
        "observability": {
            "execution_model": {"code": "NEXT_BAR_OPEN", "label": "x", "look_ahead": False},
            "signals_logged": 3,
            "signals_truncated": False,
            "signal_log_cap": 25000,
            "reject_reason_counts": [{"code": "RISK_BLOCK", "count": 1}],
            "status_counts": {"filled": 1, "rejected": 1, "deferred": 1},
        },
    }

    svc = BacktestService()
    db = MagicMock()

    def _fresh_run(*_a, **_k):
        return copy.deepcopy(run_row)

    async def _run():
        with patch(
            "app.modules.robots_v2.backtest.service.fetch_db_run",
            side_effect=_fresh_run,
        ), patch(
            "app.modules.robots_v2.backtest.service.backtest_run_store.get",
            new=AsyncMock(return_value=None),
        ):
            details = await svc.get_details(
                77,
                user_id=1,
                db=db,
                signals_limit=10,
                signals_offset=0,
                signals_status="rejected",
                reject_reason="RISK_BLOCK",
            )
            assert isinstance(details, RobotV2BacktestDetailsResponse)
            assert details.observability is not None
            assert details.observability.execution_model.code == "NEXT_BAR_OPEN"
            assert details.signals_total == 1
            assert len(details.signals) == 1
            assert details.fee_summary is not None
            assert details.narrative

            page = await svc.get_signals_page(
                77,
                user_id=1,
                db=db,
                limit=1,
                offset=0,
                status_filter="deferred",
                ticker="SBER",
                cycle_id="c1",
            )
            assert isinstance(page, RobotV2BacktestSignalsPageResponse)
            assert page.total == 1
            assert page.items[0]["status"] == "deferred"

            bundle = await svc.get_cycle_bundle(77, "c1", user_id=1, db=db)
            assert isinstance(bundle, RobotV2BacktestCycleBundleResponse)
            assert bundle.cycle_id == "c1"
            assert bundle.signals
            assert bundle.trades

        with patch(
            "app.modules.robots_v2.backtest.service.fetch_db_run",
            side_effect=_fresh_run,
        ), patch(
            "app.modules.robots_v2.backtest.service.load_universe_membership",
            return_value=[
                {
                    "trade_date": "2025-01-02",
                    "ticker": "SBER",
                    "source": "fixed",
                    "filter_result": None,
                    "reject_reason": None,
                },
            ],
        ):
            uni = await svc.get_universe_membership(
                77, user_id=1, db=db, from_date=date(2025, 1, 1), to_date=date(2025, 1, 31),
            )
            assert isinstance(uni, RobotV2BacktestUniverseResponse)
            assert uni.total == 1
            assert uni.days == [date(2025, 1, 2)]

        with patch(
            "app.modules.robots_v2.backtest.service.fetch_db_run",
            side_effect=_fresh_run,
        ), patch(
            "app.modules.robots_v2.backtest.service.load_execution_events",
            return_value=[],
        ):
            # Falls back to row.execution_events and filters by cycle_id.
            events = await svc.get_execution_events(77, user_id=1, db=db, cycle_id="c1")
            assert isinstance(events, RobotV2BacktestExecutionEventsResponse)
            assert events.total == 2
            assert any(e.get("reject_reason") == "DROPPED_DEFERRED" for e in events.items)

        with patch(
            "app.modules.robots_v2.backtest.service.fetch_db_run",
            side_effect=_fresh_run,
        ):
            narr = await svc.get_narrative(77, user_id=1, db=db)
            assert isinstance(narr, RobotV2BacktestNarrativeResponse)
            assert narr.total == 1
            assert narr.items[0].section == "старт"

        with patch(
            "app.modules.robots_v2.backtest.service.fetch_db_run",
            side_effect=_fresh_run,
        ), patch(
            "app.modules.robots_v2.backtest.service.fetch_price_window",
            return_value={
                "ticker": "SBER",
                "around": started.isoformat(),
                "bars": 5,
                "interval": "1h",
                "market": "osengine",
                "candles": [
                    {"time": started.isoformat(), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                ],
                "source": "cache",
                "gap": None,
            },
        ):
            win = await svc.get_price_window(
                77,
                user_id=1,
                db=db,
                ticker="SBER",
                around=started,
                bars=5,
            )
            assert isinstance(win, RobotV2BacktestPriceWindowResponse)
            assert win.ticker == "SBER"
            assert len(win.candles) == 1
            assert win.gap is None

    asyncio.run(_run())
