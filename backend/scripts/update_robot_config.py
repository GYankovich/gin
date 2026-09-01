"""Update robot scalper strategy params in DB. Default: robot #3."""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

ROBOT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 3

NEW_PARAMS = {
    "deltaThresholdPct": 8,
    "requiresWebSocket": True,
    "minVolumeWindow": 30,
    "cooldownSec": 180,
    "stopLossCooldownSec": 600,
    "trendLookbackTicks": 10,
    "trendBlockLongBps": 30,
    "minHoldSec": 90,
    "minExitMoveBps": 80,
    "invalidateBelowEntryBps": 180,
    "minFlowTicks": 5,
}


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"SELECT id, name, config FROM {schema}.robots_v2 WHERE id = :id"),
            {"id": ROBOT_ID},
        ).fetchone()
        if row is None:
            print(f"Robot {ROBOT_ID} not found")
            sys.exit(1)

        cfg = dict(row.config or {})
        strategy = dict(cfg.get("strategy") or {})
        strategy["params"] = NEW_PARAMS
        cfg["strategy"] = strategy

        db.execute(
            text(f"UPDATE {schema}.robots_v2 SET config = CAST(:cfg AS jsonb) WHERE id = :id"),
            {"id": ROBOT_ID, "cfg": json.dumps(cfg)},
        )
        db.commit()
        print(f"Updated robot #{ROBOT_ID} ({row.name}) strategy.params:")
        print(json.dumps(NEW_PARAMS, indent=2, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
