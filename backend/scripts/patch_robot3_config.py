"""Patch robot #3 config for current live scalper conditions.

Diagnosis from recent fills:
- round-trip commission ~0.10% eats 1% scalps closed early
- TP 1% / SL 0.99% is coin-flip after costs (schema forces SL < TP)
- delta 5% + minFlowTicks 3 lets thin inferred ticks in
- eodFlatten must fire before overnight, not at main-session close
"""
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
    "minFlowTicks": 5,
}

NEW_RISK_PATCH = {
    "stopLossPct": 0.6,
    "takeProfitPct": 1.5,
    "maxDailyLoss": 500,
    # Flatten relative to evening close (timeTo), not main session 18:40.
    "eodFlatten": {"enabled": True, "minutesBeforeClose": 15},
}

NEW_SCHEDULE_PATCH = {
    "timeFrom": "10:00",
    # MOEX evening session ends ~23:50 → EOD flatten ~23:35.
    "timeTo": "23:50",
}

UNIVERSE_PATCH = {
    "maxAssets": 12,
}


def main() -> None:
    schema = settings.DB_SCHEMA or "public"
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"SELECT id, name, status, config FROM {schema}.robots_v2 WHERE id = :id"),
            {"id": ROBOT_ID},
        ).fetchone()
        if row is None:
            print(f"Robot {ROBOT_ID} not found")
            sys.exit(1)

        cfg = dict(row.config or {})
        before = json.dumps(
            {
                "strategy.params": (cfg.get("strategy") or {}).get("params"),
                "risk": cfg.get("risk"),
                "schedule": (cfg.get("core") or {}).get("schedule"),
                "universe.maxAssets": (cfg.get("universe") or {}).get("maxAssets"),
            },
            ensure_ascii=False,
            indent=2,
        )

        strategy = dict(cfg.get("strategy") or {})
        strategy["params"] = NEW_PARAMS
        cfg["strategy"] = strategy

        risk = dict(cfg.get("risk") or {})
        risk.update({k: v for k, v in NEW_RISK_PATCH.items() if k != "eodFlatten"})
        risk["eodFlatten"] = dict(NEW_RISK_PATCH["eodFlatten"])
        cfg["risk"] = risk

        core = dict(cfg.get("core") or {})
        schedule = dict(core.get("schedule") or {})
        schedule.update(NEW_SCHEDULE_PATCH)
        core["schedule"] = schedule
        cfg["core"] = core

        universe = dict(cfg.get("universe") or {})
        universe.update(UNIVERSE_PATCH)
        cfg["universe"] = universe

        from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4

        TradingRobotConfigV4.model_validate(cfg)

        db.execute(
            text(f"UPDATE {schema}.robots_v2 SET config = CAST(:cfg AS jsonb), date_modification = NOW() WHERE id = :id"),
            {"id": ROBOT_ID, "cfg": json.dumps(cfg)},
        )
        db.commit()

        print(f"Updated robot #{ROBOT_ID} ({row.name}) status={row.status}")
        print("--- before ---")
        print(before)
        print("--- after ---")
        print(json.dumps(
            {
                "strategy.params": NEW_PARAMS,
                "risk.patch": NEW_RISK_PATCH,
                "schedule.patch": NEW_SCHEDULE_PATCH,
                "universe.patch": UNIVERSE_PATCH,
            },
            indent=2,
            ensure_ascii=False,
        ))
        print("Restart the robot session to pick this up (live session keeps the old config in memory).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
