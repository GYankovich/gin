"""Preview Bybit screener universe for robots_v2 (like robot 3)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.modules.robots_v2.universe.service import UniverseService

UNIVERSE = {
    "mode": "screener",
    "screener": {
        "preset": "volatile",
        "filters": [{"type": "price", "op": "<", "value": 1.0}],
        "filterMode": "all",
        "refreshPolicy": "on_session",
    },
    "excluded": [],
    "maxAssets": 8,
    "exitOnDrop": False,
}


async def main() -> None:
    db = SessionLocal()
    try:
        preview = await UniverseService().preview(
            db,
            user_id=1,
            token_id=25,
            instrument_type="perpetual",
            universe_raw=UNIVERSE,
            page_size=20,
            robot_id=4,
        )
        print("total", preview.total)
        for a in preview.assets:
            vol = getattr(a, "volume24h", None)
            atr = getattr(a, "atr", None)
            print(f"{a.ticker:14} px={float(a.price or 0):.6g} vol24h={vol} atr={atr}")
        sample = preview.rejected_sample or []
        print("rejected_sample", [(r.ticker, r.code, r.message) for r in sample[:8]])
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
