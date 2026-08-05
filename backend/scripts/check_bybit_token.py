#!/usr/bin/env python3
"""Check ByBit api_tokens row (metadata only, no secrets)."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots.crypto_universe import _find_active_bybit_token


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--token-id", type=int, default=25)
    args = p.parse_args()

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT id, user_id, token_type, is_active, created_at,
                       extra_data,
                       CASE WHEN token IS NOT NULL AND length(token::text) > 0 THEN true ELSE false END AS has_token,
                       CASE WHEN extra_data ? 'token_secret'
                            AND length(COALESCE(extra_data->>'token_secret','')) > 0 THEN true ELSE false END AS has_secret
                FROM api_tokens
                WHERE id = :tid
                """
            ),
            {"tid": args.token_id},
        ).mappings().first()
        if not row:
            print(f"Token id={args.token_id} NOT FOUND", file=sys.stderr)
            return 1

        d = dict(row)
        extra = d.pop("extra_data") or {}
        if isinstance(extra, str):
            extra = json.loads(extra)
        d["testnet"] = extra.get("testnet")
        d["extra_keys"] = sorted(extra.keys())
        print("Token metadata (no secrets):")
        for k, v in d.items():
            print(f"  {k}: {v}")

        uid = int(d["user_id"])
        found = _find_active_bybit_token(db, uid)
        print(f"_find_active_bybit_token(user_id={uid}):", "FOUND" if found else "NOT FOUND")
        if found:
            print(
                f"  resolved testnet={found.get('testnet')} "
                f"has_key={bool(found.get('token'))} has_secret={bool(found.get('token_secret'))}"
            )
        return 0 if found else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
