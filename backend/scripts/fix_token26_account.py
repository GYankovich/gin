"""Test token 26 accounts and persist account_id."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.core.config import settings
from app.core.secret_box import open_broker_material
from app.core.database import SessionLocal
from app.modules.robot_lib.trading.brokers.factory import create_broker_facade
from app.modules.robots.engine.broker_factory import persist_token_account_id, resolve_account_id

TOKEN_ID = 26
USER_ID = 1


async def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    row = db.execute(
        text(f"SELECT id, token_type, token, token_secret, extra_data, last_error FROM {schema}.api_tokens WHERE id=:id"),
        {"id": TOKEN_ID},
    ).fetchone()
    if not row:
        print("token not found")
        return
    print("before:", {k: row._mapping[k] for k in row._mapping.keys() if k not in {"token", "token_secret"}})
    token, extra = open_broker_material(row.token, row.token_secret, row.extra_data)
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
            persist_token_account_id(
                user_id=USER_ID,
                token_id=TOKEN_ID,
                account_id=acc_id,
                schema=schema,
            )
            print("linked account in token_portfolio_accounts")
    except Exception as exc:
        print("ERROR:", exc)
        db.execute(
            text(f"""
                UPDATE {schema}.api_tokens
                SET last_error = :err, last_error_at = NOW(), modification_date = NOW()
                WHERE id = :id
            """),
            {"err": str(exc)[:500], "id": TOKEN_ID},
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
