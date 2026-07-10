#!/usr/bin/env python3
"""Dry-run crypto auto screening for a user (uses real ByBit API)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots.crypto_universe import rebuild_crypto_universe, resolve_crypto_universe_filters


def _token_owner(db, token_id: int) -> int | None:
    row = db.execute(
        text(f"SELECT user_id FROM {settings.DB_SCHEMA}.api_tokens WHERE id = :tid"),
        {"tid": token_id},
    ).first()
    return int(row[0]) if row else None


def _bybit_robots(db, user_id: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT id, type, status, config
            FROM {settings.DB_SCHEMA}.robots
            WHERE user_id = :uid AND LOWER(COALESCE(config->>'broker_type','')) = 'bybit'
            ORDER BY id DESC
            LIMIT 10
            """
        ),
        {"uid": user_id},
    ).mappings().all()
    out = []
    for r in rows:
        cfg = r["config"] or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        out.append({"id": r["id"], "type": r["type"], "status": r["status"], "universe_mode": cfg.get("universe_mode")})
    return out


async def _screen(db, *, robot_id: int, user_id: int, config: dict) -> dict:
    return await rebuild_crypto_universe(db, robot_id=robot_id, user_id=user_id, config=config)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--token-id", type=int, default=25)
    p.add_argument("--robot-id", type=int, default=None)
    p.add_argument("--min-volume", type=float, default=5_000_000)
    p.add_argument("--max-spread-bps", type=float, default=30)
    args = p.parse_args()

    db = SessionLocal()
    try:
        user_id = _token_owner(db, args.token_id)
        if user_id is None:
            print(f"Token id={args.token_id} not found", file=sys.stderr)
            return 1
        print(f"token_id={args.token_id} user_id={user_id}")

        robots = _bybit_robots(db, user_id)
        print(f"ByBit robots: {robots if robots else '(none)'}")
        robot_id = args.robot_id or (robots[0]["id"] if robots else None)

        config = {
            "broker_type": "bybit",
            "universe_mode": "auto",
            "crypto_universe": {
                "enabled": True,
                "min_volume_24h_usd": args.min_volume,
                "max_spread_bps": args.max_spread_bps,
            },
            "bybit": {"testnet": True, "instrument_category": "linear"},
            "allowed_symbols": [],
        }
        flt = resolve_crypto_universe_filters(config)
        print(f"filters: min_turnover={flt.min_turnover_24h_usd} max_spread_pct={flt.max_spread_pct} category={flt.category}")

        if robot_id is None:
            print("No robot_id — screening in-memory only (ad-hoc path uses same ByBit fetch)")
            from app.modules.robots.trading.pipeline.crypto_universe_scoring import _fetch_and_score_symbols

            symbols, decisions, scanned = asyncio.run(
                _fetch_and_score_symbols(db, user_id=user_id, config=config, candidate_pool=None)
            )
            print(f"scanned={scanned} accepted={len(symbols)} symbols={symbols[:15]}")
            return 0

        print(f"running rebuild_crypto_universe robot_id={robot_id} ...")
        result = asyncio.run(_screen(db, robot_id=robot_id, user_id=user_id, config=config))
        print(json.dumps({k: result[k] for k in result if k != "message"}, ensure_ascii=False, indent=2))
        if result.get("message"):
            print("message:", result["message"])
        return 0 if result.get("accepted", 0) > 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
