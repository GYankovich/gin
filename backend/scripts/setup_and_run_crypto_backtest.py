#!/usr/bin/env python3
"""
Полный smoke-test crypto testnet: upsert token → validate ByBit → screening → sync backtest.

Запуск из корня репозитория (читает .env):
  set BYBIT_API_KEY=...
  set BYBIT_API_SECRET=...
  python backend/scripts/setup_and_run_crypto_backtest.py --token-id 25 --user-id <uid> --days 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_script(name: str, *args: str) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "scripts" / name), *args],
        env=env,
        cwd=str(ROOT),
    )
    return int(proc.returncode)


async def _validate_bybit() -> dict:
    from app.modules.settings.service import api_key_service

    key = os.environ["BYBIT_API_KEY"]
    secret = os.environ["BYBIT_API_SECRET"]
    for testnet in (True, False):
        res = await api_key_service.test_key(
            token=key,
            key_type="bybit",
            token_secret=secret,
            testnet=testnet,
        )
        if res.get("is_valid"):
            return res
    return res


async def _run_backtest(user_id: int, token_id: int, days: int) -> int:
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.modules.robots import schemas
    from app.modules.robots.service import RobotService

    db = SessionLocal()
    svc = RobotService()
    try:
        to_day = datetime.now(timezone.utc) - timedelta(days=1)
        from_day = to_day - timedelta(days=max(1, days))
        testnet = os.environ.get("BYBIT_TESTNET", "true").lower() in {"1", "true", "yes"}
        config = {
            "broker_type": "bybit",
            "universe_mode": "auto",
            "crypto_universe": {
                "enabled": True,
                "min_volume_24h_usd": 1_000_000,
                "max_spread_bps": 50,
            },
            "bybit": {"testnet": testnet, "instrument_category": "linear"},
            "risk": {"max_daily_loss": 5, "max_position_percent": 10},
            "signal_generation": {
                "strategy": "reversion_to_ma",
                "params": {"interval": "5m", "ma_period": 20},
                "data_source": "bybit",
            },
            "costs": {"funding_rate_enabled": False},
        }
        req = schemas.RobotHistoryBacktestRequest(
            robot_id=None,
            token_id=token_id,
            from_date=from_day,
            to_date=to_day,
            initial_capital=10_000,
            async_execution=False,
            config=config,
        )
        print(f"backtest user_id={user_id} token_id={token_id} range={from_day.date()}..{to_day.date()}")
        out = await svc.run_robot_history_backtest(db, user_id, req)
        resp = schemas.RobotHistoryBacktestResponse.model_validate(out)
        print(f"OK return_pct={resp.total_return_percent:.4f}% trades={len(resp.trades)} final={resp.final_equity:.2f}")
        if resp.stages:
            print("stages tail:", " | ".join(resp.stages[-5:]))
        return 0
    except Exception as ex:
        print(f"backtest FAILED: {ex}", file=sys.stderr)
        return 1
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--token-id", type=int, default=25)
    p.add_argument("--user-id", type=int, required=True, help="user_id владельца api_tokens")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--skip-upsert", action="store_true")
    p.add_argument("--skip-backtest", action="store_true")
    args = p.parse_args()

    if not os.environ.get("BYBIT_API_KEY") or not os.environ.get("BYBIT_API_SECRET"):
        print("Set BYBIT_API_KEY and BYBIT_API_SECRET env vars", file=sys.stderr)
        return 1

    os.environ.setdefault("BYBIT_TOKEN_ID", str(args.token_id))
    os.environ.setdefault("BYBIT_TESTNET", "true")

    if not args.skip_upsert:
        print("=== 1/4 upsert api_tokens ===")
        if _run_script("upsert_bybit_token_env.py") != 0:
            return 1

    print("=== 2/4 check token row ===")
    if _run_script("check_bybit_token.py", "--token-id", str(args.token_id)) != 0:
        return 1

    print("=== 3/4 ByBit validate + screening ===")
    if _run_script("try_crypto_screening.py", "--token-id", str(args.token_id)) != 0:
        return 1

    val = asyncio.run(_validate_bybit())
    print("ByBit validate:", json.dumps(val, ensure_ascii=False))
    if not val.get("is_valid"):
        return 1
    os.environ["BYBIT_TESTNET"] = "true" if val.get("testnet") else "false"

    if args.skip_backtest:
        print("skip backtest")
        return 0

    print("=== 4/4 sync crypto auto backtest ===")
    return asyncio.run(_run_backtest(args.user_id, args.token_id, args.days))


if __name__ == "__main__":
    raise SystemExit(main())
