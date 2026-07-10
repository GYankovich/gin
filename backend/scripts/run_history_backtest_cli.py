#!/usr/bin/env python3
"""
CLI: синхронный history-backtest (прогон через новый стек ARCH-04).

Пример:
  set PYTHONPATH=backend
  python backend/scripts/run_history_backtest_cli.py --robot-id 10 --days 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots import schemas
from app.modules.robots.service import RobotService


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run history-backtest synchronously")
    p.add_argument("--robot-id", type=int, default=10)
    p.add_argument("--days", type=int, default=5, help="Calendar days in range (UTC)")
    p.add_argument("--to", type=str, default=None, help="End date YYYY-MM-DD (UTC), default yesterday")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--user-id", type=int, default=None, help="Override user_id (default from robot row)")
    p.add_argument(
        "--fixed-tickers",
        type=str,
        default=None,
        help="Comma-separated SECIDs; sets universe_mode=fixed for this run only",
    )
    p.add_argument(
        "--interval",
        type=str,
        default=None,
        help="Override strategy_params.interval (execution / T-Invest)",
    )
    p.add_argument(
        "--moex-interval",
        type=str,
        default=None,
        help="Override strategy_params.moex_analysis_interval (MOEX prefetch only)",
    )
    return p.parse_args()


def _config_overrides(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    overrides: Dict[str, Any] = {}
    if args.fixed_tickers:
        tickers = [t.strip().upper() for t in args.fixed_tickers.split(",") if t.strip()]
        if tickers:
            overrides["universe_mode"] = "fixed"
            overrides["fixed_tickers"] = tickers
    if args.interval:
        overrides.setdefault("strategy_params", {})["interval"] = args.interval.strip()
    if args.moex_interval:
        overrides.setdefault("strategy_params", {})["moex_analysis_interval"] = args.moex_interval.strip()
    return overrides or None


def _load_robot(db, robot_id: int) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT id, user_id, type, status, config
            FROM {settings.DB_SCHEMA}.robots
            WHERE id = :rid
            """
        ),
        {"rid": robot_id},
    ).mappings().first()
    return dict(row) if row else None


async def _run(args: argparse.Namespace) -> int:
    db = SessionLocal()
    svc = RobotService()
    try:
        robot = _load_robot(db, args.robot_id)
        if not robot:
            print(f"Robot id={args.robot_id} not found", file=sys.stderr)
            return 1
        user_id = int(args.user_id or robot["user_id"])
        cfg = robot.get("config") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        strategy = (cfg.get("strategy") or "momentum_breakout")
        interval = (cfg.get("strategy_params") or {}).get("interval", "?")
        print(f"robot_id={args.robot_id} user_id={user_id} type={robot.get('type')} status={robot.get('status')}")
        print(f"strategy={strategy} interval={interval}")

        if args.to:
            to_day = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            to_day = datetime.now(timezone.utc) - timedelta(days=1)
        from_day = to_day - timedelta(days=max(1, args.days))

        cfg_override = _config_overrides(args)
        if cfg_override:
            print(f"config override: {json.dumps(cfg_override, ensure_ascii=False)}")

        req = schemas.RobotHistoryBacktestRequest(
            robot_id=args.robot_id,
            from_date=from_day,
            to_date=to_day,
            initial_capital=float(args.capital),
            async_execution=False,
            config=cfg_override,
        )
        print(f"range UTC: {from_day.date()} .. {to_day.date()} (sync, no BackgroundTasks)")
        print("starting run_robot_history_backtest...")

        t0 = datetime.now(timezone.utc)
        out = await svc.run_robot_history_backtest(db, user_id, req)
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()

        if isinstance(out, dict) and out.get("__async_enqueue__"):
            print(f"unexpected async enqueue run_id={out.get('run_id')}")
            return 2

        resp = schemas.RobotHistoryBacktestResponse.model_validate(out)
        print(f"done in {elapsed:.1f}s")
        print(f"  return_pct={resp.total_return_percent:.4f}%")
        print(f"  final_equity={resp.final_equity:,.2f}")
        print(f"  max_drawdown={resp.max_drawdown_percent}")
        print(f"  trades={len(resp.trades)}")
        if resp.stages:
            print("  stages tail:", " | ".join(resp.stages[-4:]))
        return 0
    except HTTPException as hex:
        print(f"FAILED HTTP {hex.status_code}: {hex.detail}", file=sys.stderr)
        return 1
    except Exception as ex:
        print(f"FAILED: {ex}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
