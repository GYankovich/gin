"""Debug DMS volatile screener for robot 3."""
import asyncio
import json
from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.config import settings
from app.modules.dms.service import dms_service
from app.modules.robots_v2.universe import presets

schema = settings.DB_SCHEMA or "public"
db = SessionLocal()


async def run():
    filters = presets.resolve_moex_dms_filters(preset="volatile", custom_filters=None)
    print("filters:", json.dumps(filters, ensure_ascii=False))
    result = await dms_service.preview_pipeline_setup(
        db=db,
        user_id=1,
        board="TQBR",
        filters=filters,
        mode="ALL",
        universe_mode="tqbr_scan",
        fixed_tickers=[],
        warmup_candles=True,
    )
    print("total_checked:", result.get("total_checked"))
    print("passed:", result.get("passed"))
    print("rejected:", result.get("rejected"))
    accepts = [x for x in (result.get("sample") or []) if x.get("result") == "ACCEPT"]
    print("accepts:", len(accepts), [x["ticker"] for x in accepts[:15]])
    if result.get("rejected"):
        rejects = [x for x in result.get("sample") or [] if x.get("result") == "REJECT"][:5]
        for r in rejects:
            print(" reject", r.get("ticker"), r.get("reason"))


asyncio.run(run())
db.close()
