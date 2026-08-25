"""Test token 26 accounts and persist account_id."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots_v2.engine.broker_factory import resolve_account_id

TOKEN_ID = 26
USER_ID = 1


async def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    row = db.execute(
        text(f"SELECT id, token_type, token, extra_data, account_id, last_error FROM {schema}.api_tokens WHERE id=:id"),
        {"id": TOKEN_ID},
    ).fetchone()
    if not row:
        print("token not found")
        return
    print("before:", {k: row._mapping[k] for k in row._mapping.keys() if k != "token"})
    token = str(row.token)
    extra = row.extra_data if isinstance(row.extra_data, dict) else {}
    broker = create_broker_facade(
        "tinvest",
        token,
        api_secret=extra.get("token_secret"),
        token_extra_data=extra,
        user_id=USER_ID,
        token_id=TOKEN_ID,
    )
    try:
        accounts = await broker.get_accounts()
        print("accounts:", json.dumps(accounts, ensure_ascii=False, indent=2, default=str))
        acc_id = await resolve_account_id(broker, None)
        print("resolved:", acc_id)
        if acc_id:
            db.execute(
                text(f"""
                    UPDATE {schema}.api_tokens
                    SET account_id = :acc, last_error = NULL, last_error_at = NULL, updated_at = NOW()
                    WHERE id = :id AND user_id = :uid
                """),
                {"acc": acc_id, "id": TOKEN_ID, "uid": USER_ID},
            )
            db.commit()
            print("updated account_id in DB")
    except Exception as exc:
        print("ERROR:", exc)
        db.execute(
            text(f"""
                UPDATE {schema}.api_tokens
                SET last_error = :err, last_error_at = NOW(), updated_at = NOW()
                WHERE id = :id
            """),
            {"err": str(exc)[:500], "id": TOKEN_ID},
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
