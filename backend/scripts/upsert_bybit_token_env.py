#!/usr/bin/env python3
"""One-off: upsert ByBit test token from env BYBIT_API_KEY / BYBIT_API_SECRET."""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal


def main() -> int:
    token_id = int(os.environ.get("BYBIT_TOKEN_ID", "25"))
    api_key = os.environ.get("BYBIT_API_KEY", "").strip()
    api_secret = os.environ.get("BYBIT_API_SECRET", "").strip()
    testnet = os.environ.get("BYBIT_TESTNET", "true").strip().lower() in {"1", "true", "yes"}

    if not api_key or not api_secret:
        print("Set BYBIT_API_KEY and BYBIT_API_SECRET", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT id, user_id, token_type, is_active
                FROM api_tokens
                WHERE id = :tid
                """
            ),
            {"tid": token_id},
        ).mappings().first()
        if not row:
            print(f"Token id={token_id} not found", file=sys.stderr)
            return 1

        extra = json.dumps({"token_secret": api_secret, "testnet": testnet}, ensure_ascii=False)
        db.execute(
            text(
                f"""
                UPDATE api_tokens
                SET token = :token,
                    token_type = 'bybit',
                    is_active = 1,
                    extra_data = CAST(:extra AS jsonb),
                    updated_at = NOW()
                WHERE id = :tid
                """
            ),
            {"token": api_key, "extra": extra, "tid": token_id},
        )
        db.commit()
        print(f"updated api_tokens.id={token_id} user_id={row['user_id']} testnet={testnet}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
