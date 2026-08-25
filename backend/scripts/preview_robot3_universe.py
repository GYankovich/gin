import asyncio
from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.config import settings
from app.modules.robots_v2.universe.service import UniverseService

schema = settings.DB_SCHEMA or "public"
db = SessionLocal()
row = db.execute(
    text(f"SELECT config, user_id, token_id FROM {schema}.robots_v2 WHERE id=3"),
).fetchone()
cfg = row.config if isinstance(row.config, dict) else {}
core = cfg.get("core") or {}
instrument_type = str(core.get("instrumentType") or core.get("instrument_type") or "stock")
universe_raw = cfg.get("universe") or {}
svc = UniverseService()


async def run() -> None:
    preview = await svc.preview(
        db,
        user_id=int(row.user_id),
        token_id=int(row.token_id),
        instrument_type=instrument_type,
        universe_raw=universe_raw,
        page_size=50,
        robot_id=3,
    )
    print("assets:", len(preview.assets))
    print("tickers:", [a.ticker for a in preview.assets[:20]])
    print("total:", preview.total)
    print("rejected_sample:", preview.rejected_sample[:10] if preview.rejected_sample else None)


asyncio.run(run())
db.close()
