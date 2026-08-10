#!/usr/bin/env python3
"""E2E Bybit smoke: history-backtest (sync) + safe limit order on mainnet."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots import schemas
from app.modules.robots.router import _continue_history_backtest_async
from app.modules.robots.service import robot_service
from app.modules.robots.trading.brokers.factory import create_broker_facade


def _load_env_from_repo_root() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        import os

        os.environ.setdefault(key.strip(), val.strip())


def _bybit_config(symbol: str = "BTCUSDT") -> dict:
    return {
        "config_version": 3,
        "schema_profile": "type2_bybit",
        "broker_type": "bybit",
        "market_profile": "crypto",
        "instrument_id_type": "symbol",
        "universe_mode": "fixed",
        "allowed_symbols": [symbol],
        "instruments": [symbol],
        "bybit": {
            "testnet": False,
            "instrument_category": "linear",
            "leverage": 1,
            "position_mode": "one_way",
        },
        "signal_generation": {
            "strategy": "reversion_to_ma",
            "params": {"interval": "1h", "ma_period": 20},
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
        },
    }


def _find_robot(db, token_id: int) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT id, user_id, token_id, type, config
            FROM robots
            WHERE token_id = :tid AND type = 2
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"tid": token_id},
    ).mappings().first()
    return dict(row) if row else None


async def run_backtest_e2e(*, token_id: int, user_id: int, robot_id: int | None, days: int) -> dict:
    db = SessionLocal()
    try:
        to_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        from_dt = to_dt - timedelta(days=max(3, days))
        req = schemas.RobotHistoryBacktestRequest(
            robot_id=robot_id,
            strategy="reversion_to_ma" if robot_id is None else None,
            from_date=from_dt,
            to_date=to_dt,
            initial_capital=1000.0,
            token_id=token_id,
            type=2,
            config=None if robot_id else _bybit_config(),
            async_execution=True,
        )
        payload = await robot_service.run_robot_history_backtest(db, user_id, req)
        if not isinstance(payload, dict) or not payload.get("__async_enqueue__"):
            return {"phase": "backtest", "result": payload}

        run_id = int(payload["run_id"])
        body = req.model_dump(mode="json")
        await _continue_history_backtest_async(run_id, user_id, body)

        row = db.execute(
            text(
                f"""
                SELECT br.id, br.status, br.run_phase, br.error_message,
                       bm.total_return_percent, bm.max_drawdown_percent, bm.trades_total
                FROM backtest_runs br
                LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
                WHERE br.id = :rid
                """
            ),
            {"rid": run_id},
        ).mappings().first()
        out = dict(row) if row else {"run_id": run_id, "status": "unknown"}
        out["run_id"] = run_id
        out["phase"] = "backtest"
        return out
    finally:
        db.close()


async def run_live_order_smoke(*, token_id: int, symbol: str = "BTCUSDT") -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT token, extra_data
                FROM api_tokens
                WHERE id = :tid AND is_active = 1
                """
            ),
            {"tid": token_id},
        ).mappings().first()
        if not row:
            raise SystemExit(f"token_id={token_id} not found")

        extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
        api_key = str(row["token"] or "").strip()
        secret = str(extra.get("token_secret") or "").strip()
        if not api_key or not secret:
            raise SystemExit(f"token_id={token_id} missing key/secret")

        broker = create_broker_facade(
            "bybit",
            api_key,
            token_extra_data={"token_secret": secret},
            robot_config=_bybit_config(symbol),
        )
        accounts = await broker.get_accounts()
        unified = next(
            (a for a in accounts if str(a.get("type") or "").upper() == "UNIFIED"),
            accounts[0] if accounts else {"id": broker.make_account_id("UNIFIED")},
        )
        account_id = str(unified.get("id"))
        out: dict = {"phase": "live_order", "symbol": symbol.upper(), "ok": False, "account_id": account_id}
        try:
            to_dt = datetime.now(timezone.utc)
            from_dt = to_dt - timedelta(hours=2)
            candles = await broker.get_candles(symbol.upper(), from_dt, to_dt, "1h")
            if not candles:
                out["error"] = "no candles for price reference"
                return out
            last_close = float(candles[-1].get("close") or 0)
            # Limit far below market — should not fill; safe mainnet smoke.
            limit_price = round(last_close * 0.5, 1)
            qty = "0.001"

            resp = await broker._http.create_order(
                category="linear",
                symbol=symbol.upper(),
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=str(limit_price),
                time_in_force="GTC",
            )
            order_id = str(((resp.get("result") or {}).get("orderId")) or "")
            out["order_id"] = order_id
            out["limit_price"] = limit_price
            out["last_close"] = last_close
            out["qty"] = qty

            if not order_id:
                out["error"] = "order not created"
                out["raw"] = resp
                return out

            state = await broker.get_order_state(account_id, order_id)
            out["order_status"] = state.get("executionReportStatus")
            cancelled = await broker.cancel_order(account_id, order_id)
            out["cancelled"] = bool(cancelled.get("orderId"))
            out["ok"] = True
            return out
        finally:
            await broker.close()
    finally:
        db.close()


async def _main_async(args: argparse.Namespace) -> int:
    robot_id = args.robot_id
    user_id = args.user_id
    db = SessionLocal()
    try:
        if robot_id is None:
            found = _find_robot(db, args.token_id)
            if found:
                robot_id = int(found["id"])
                user_id = int(found["user_id"])
                print(f"using robot_id={robot_id} user_id={user_id}")
            else:
                print(f"no type=2 robot for token_id={args.token_id}, standalone backtest")
        elif user_id is None:
            row = db.execute(
                text(f"SELECT user_id FROM robots WHERE id = :rid"),
                {"rid": robot_id},
            ).first()
            if not row:
                raise SystemExit(f"robot_id={robot_id} not found")
            user_id = int(row[0])
    finally:
        db.close()

    results: dict = {}
    if args.skip_backtest:
        pass
    else:
        print("=== E2E history-backtest ===")
        results["backtest"] = await run_backtest_e2e(
            token_id=args.token_id,
            user_id=int(user_id),
            robot_id=robot_id,
            days=args.days,
        )
        print(json.dumps(results["backtest"], ensure_ascii=False, indent=2, default=str))

    if not args.skip_order:
        print("=== Live order smoke (limit + cancel) ===")
        results["live_order"] = await run_live_order_smoke(
            token_id=args.token_id,
            symbol=args.symbol,
        )
        print(json.dumps(results["live_order"], ensure_ascii=False, indent=2, default=str))

    ok_bt = args.skip_backtest or str(results.get("backtest", {}).get("status", "")).upper() in ("COMPLETED", "SUCCESS")
    ok_ord = args.skip_order or bool(results.get("live_order", {}).get("ok"))
    return 0 if ok_bt and ok_ord else 1


def main() -> int:
    _load_env_from_repo_root()
    parser = argparse.ArgumentParser(description="Bybit E2E backtest + live order smoke")
    parser.add_argument("--token-id", type=int, default=25)
    parser.add_argument("--robot-id", type=int, default=None)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--skip-order", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
