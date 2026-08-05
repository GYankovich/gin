#!/usr/bin/env python3
"""
Live smoke: ByBit mainnet через ByBitBrokerFacade (без ордеров).

  python scripts/live_smoke_bybit.py --token-id 25
  python scripts/live_smoke_bybit.py --from-env
  python scripts/live_smoke_bybit.py --public-only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.bybit.live_smoke import run_bybit_live_smoke, run_bybit_public_smoke


def _load_token_from_db(token_id: int) -> tuple[str, dict[str, Any]]:
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
            raise SystemExit(f"Active token id={token_id} not found")
        extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
        api_key = str(row["token"] or "").strip()
        if not api_key:
            raise SystemExit(f"Token id={token_id} has empty api key")
        if not str(extra.get("token_secret") or "").strip():
            raise SystemExit(f"Token id={token_id} missing extra_data.token_secret")
        return api_key, extra
    finally:
        db.close()


def _load_token_from_env() -> tuple[str, dict[str, Any]]:
    key = os.environ.get("BYBIT_API_KEY", "").strip()
    secret = os.environ.get("BYBIT_API_SECRET", "").strip()
    if not key or not secret:
        raise SystemExit("Set BYBIT_API_KEY and BYBIT_API_SECRET or use --token-id")
    return key, {"token_secret": secret}


async def _main_async(args: argparse.Namespace) -> int:
    if args.public_only:
        result = await run_bybit_public_smoke(symbol=args.symbol)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.from_env:
        api_key, extra = _load_token_from_env()
    else:
        api_key, extra = _load_token_from_db(int(args.token_id))

    result = await run_bybit_live_smoke(
        api_key,
        extra,
        symbol=str(args.symbol).upper(),
        instrument_category=args.instrument_category,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ByBit mainnet live smoke (no orders)")
    parser.add_argument("--token-id", type=int, default=None, help="api_tokens.id")
    parser.add_argument("--from-env", action="store_true", help="BYBIT_API_KEY / BYBIT_API_SECRET")
    parser.add_argument("--public-only", action="store_true", help="Public kline only (no API key)")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument-category", default="linear", choices=["spot", "linear", "inverse"])
    args = parser.parse_args()

    if args.public_only:
        pass
    elif args.from_env:
        pass
    elif args.token_id is not None:
        pass
    else:
        parser.error("Provide --token-id, --from-env, or --public-only")

    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
