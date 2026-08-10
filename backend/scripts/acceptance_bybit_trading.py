#!/usr/bin/env python3
"""
Full Bybit trading acceptance (mainnet, token 25):
  1) create type=2 robot
  2) history-backtest (sync worker)
  3) one live trading cycle (no infinite session)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots import schemas
from app.modules.robots.router import _continue_history_backtest_async
from app.modules.robots.service import robot_service
from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.core.trading_core import run_single_trading_cycle
from app.modules.robots.trading.indicators.service import indicator_service
from app.modules.robots.trading.session_factory import create_trading_session


def load_repo_env() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ[key.strip()] = val.strip()
    os.environ.setdefault("DB_SSL_MODE", "require")


def bybit_trading_config() -> dict[str, Any]:
    return {
        "config_version": 3,
        "schema_profile": "type2_bybit",
        "broker_type": "bybit",
        "market_profile": "crypto",
        "instrument_id_type": "symbol",
        "universe_mode": "fixed",
        "allowed_symbols": ["BTCUSDT"],
        "instruments": ["BTCUSDT"],
        "bybit": {
            "testnet": False,
            "instrument_category": "linear",
            "leverage": 1,
            "position_mode": "one_way",
        },
        "signal_generation": {
            "strategy": "reversion_to_ma",
            "params": {
                "interval": "1h",
                "ma_period": 8,
                "rsi_period": 7,
                "deviation_pct": 1.0,
                "rsi_oversold": 45,
                "rsi_overbought": 55,
                "use_volume_filter": False,
            },
            "data_source": "bybit",
        },
        "risk": {
            "max_position_percent": 10.0,
            "risk_per_trade_pct": 2.0,
            "max_drawdown_percent": 20.0,
            "max_daily_loss": 3.0,
            "max_leverage": 1,
            "allow_short": False,
        },
        "costs": {
            "maker_fee_rate": 0.0002,
            "taker_fee_rate": 0.00055,
            "funding_rate_enabled": True,
        },
    }


async def create_acceptance_robot(*, user_id: int, token_id: int, name: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        robot = await robot_service.create_robot(
            db,
            user_id,
            schemas.RobotCreate(
                name=name,
                type=2,
                token_id=token_id,
                config=bybit_trading_config(),
                poll_interval_hours=0.05,
                trading_hours_start="00:00",
                trading_hours_end="23:59",
                allowed_weekdays=127
            )
        )
        return robot
    finally:
        db.close()


async def run_backtest(*, robot_id: int, user_id: int, days: int) -> dict[str, Any]:
    from datetime import timedelta

    db = SessionLocal()
    try:
        to_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        from_dt = to_dt - timedelta(days=max(14, days))
        req = schemas.RobotHistoryBacktestRequest(
            robot_id=robot_id,
            from_date=from_dt,
            to_date=to_dt,
            initial_capital=1000.0,
            async_execution=True
        )
        payload = await robot_service.run_robot_history_backtest(db, user_id, req)
        if not isinstance(payload, dict) or not payload.get("__async_enqueue__"):
            return {"phase": "backtest", "result": payload}
        run_id = int(payload["run_id"])
        await _continue_history_backtest_async(run_id, user_id, req.model_dump(mode="json"))
        row = db.execute(
            text(
                f"""
                SELECT br.id, br.status, br.run_phase, br.error_message,
                       bm.total_return_percent, bm.trades_total
                FROM backtest_runs br
                LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
                WHERE br.id = :rid
                """
            ),
            {"rid": run_id}
        ).mappings().first()
        out = dict(row) if row else {"run_id": run_id}
        out["phase"] = "backtest"
        out["run_id"] = run_id
        return out
    finally:
        db.close()


async def run_live_single_cycle(*, robot_id: int, user_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT r.id, r.user_id, r.token_id, r.config, at.token, at.extra_data
                FROM robots r
                JOIN api_tokens at ON r.token_id = at.id
                WHERE r.id = :rid AND r.user_id = :uid
                """
            ),
            {"rid": robot_id, "uid": user_id}
        ).mappings().first()
        if not row:
            raise SystemExit(f"robot_id={robot_id} not found")

        extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
        config = row["config"] if isinstance(row["config"], dict) else {}

        def log_func(msg: str) -> None:
            print(f"[live] {msg}")

        session = create_trading_session(
            ExecutionMode.LIVE,
            db=db,
            schema=settings.DB_SCHEMA,
            robot_id=int(row["id"]),
            user_id=int(row["user_id"]),
            token_id=int(row["token_id"]),
            token=str(row["token"] or ""),
            config=config,
            log_func=log_func,
            token_extra_data=extra
        )
        session.running = True
        out: dict[str, Any] = {"phase": "live_cycle", "robot_id": robot_id, "ok": False}

        try:
            await session._create_execution_log()
            await session._ensure_account_id()
            if not session.account_id:
                out["error"] = "account_id missing"
                return out
            await session._sync_portfolio_updater_snapshot()
            await session._refresh_account_positions()
            session._ensure_allowed_instruments_or_raise()
            await indicator_service.register_robot(
                session.robot_id, session.broker, session.allowed_figis, session.strategy_params
            )
            await indicator_service.bootstrap_candles_at_startup(
                session.robot_id,
                session.broker,
                session.allowed_figis,
                session.strategy_params,
                log_func=session._write_log,
                api_log_func=session._log_api_call
            )
            await run_single_trading_cycle(session, 1)
            out["ok"] = session.stats.get("errors", 0) == 0
            out["signals_generated"] = session.stats.get("signals_generated", 0)
            out["orders_placed"] = session.stats.get("orders_placed", 0)
            out["errors"] = session.stats.get("errors", 0)
            return out
        finally:
            session.running = False
            await indicator_service.unregister_robot(session.robot_id)
            await session.broker.close()
            if session._execution_log_id:
                await session._complete_execution_log(
                    status=1 if session.stats.get("errors", 0) == 0 else 2,
                    message=(
                        f"Acceptance single cycle. Signals: {session.stats.get('signals_generated', 0)}, "
                        f"Orders: {session.stats.get('orders_placed', 0)}"
                    ),
                    execution_time_ms=int(session.stats.get("execution_time", 0) or 0)
                )
            db.commit()
    finally:
        db.close()


async def main_async(args: argparse.Namespace) -> int:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = args.name or f"Bybit-Acceptance-{ts}"
    results: dict[str, Any] = {}

    if args.robot_id:
        robot_id = int(args.robot_id)
        user_id = int(args.user_id)
        results["robot"] = {"id": robot_id, "reused": True}
        print(f"=== Reuse robot_id={robot_id} ===")
    else:
        print(f"=== Create robot '{name}' ===")
        robot = await create_acceptance_robot(
            user_id=int(args.user_id),
            token_id=int(args.token_id),
            name=name
        )
        robot_id = int(robot["id"])
        user_id = int(args.user_id)
        results["robot"] = {"id": robot_id, "name": name}
        print(json.dumps(results["robot"], ensure_ascii=False, indent=2))

    if not args.skip_backtest:
        print("=== History backtest ===")
        results["backtest"] = await run_backtest(
            robot_id=robot_id,
            user_id=user_id,
            days=int(args.days)
        )
        print(json.dumps(results["backtest"], ensure_ascii=False, indent=2, default=str))

    if not args.skip_live:
        print("=== Live single cycle ===")
        results["live_cycle"] = await run_live_single_cycle(robot_id=robot_id, user_id=user_id)
        print(json.dumps(results["live_cycle"], ensure_ascii=False, indent=2, default=str))

    ok_robot = bool(results.get("robot", {}).get("id"))
    bt = results.get("backtest", {})
    ok_bt = args.skip_backtest or str(bt.get("status", "")).upper() in ("SUCCESS", "COMPLETED")
    ok_live = args.skip_live or bool(results.get("live_cycle", {}).get("ok"))
    trades = int(bt.get("trades_total") or 0) if bt else 0

    results["summary"] = {
        "robot_created": ok_robot,
        "backtest_ok": ok_bt,
        "backtest_trades": trades,
        "live_cycle_ok": ok_live,
        "all_ok": ok_robot and ok_bt and ok_live,
    }
    print("=== Summary ===")
    print(json.dumps(results["summary"], ensure_ascii=False, indent=2))
    return 0 if results["summary"]["all_ok"] else 1


def main() -> int:
    load_repo_env()
    parser = argparse.ArgumentParser(description="Bybit trading acceptance")
    parser.add_argument("--token-id", type=int, default=25)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--robot-id", type=int, default=None, help="Skip create, reuse robot")
    parser.add_argument("--name", default=None)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
