#!/usr/bin/env python3
"""
Batch migration robots.config → v3 (schema_profile + config_version=3).

  set PYTHONPATH=backend
  python backend/scripts/migrate_robot_configs_v3.py [--dry-run] [--robot-id 10] [--user-id 1]

Without --user-id: migrates all robots type 1|2 in schema (ops / local dev).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import text

# Repo-root .env (script often run from backend/ where pydantic won't find ../.env)
_repo_root = Path(__file__).resolve().parents[2]
_env_file = _repo_root / ".env"
if _env_file.is_file():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()

from app.core.config import get_settings, settings  # noqa: E402

get_settings.cache_clear()
settings = get_settings()

from app.core.database import SessionLocal  # noqa: E402
from app.modules.robots.config.migration import config_equals, migrate_v2_to_v3  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Migrate robot configs to v3")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--robot-id", type=int, default=None)
    p.add_argument("--user-id", type=int, default=None, help="Optional user scope (API parity)")
    args = p.parse_args()

    db = SessionLocal()
    schema = settings.DB_SCHEMA
    try:
        clauses = ["type IN (1, 2)"]
        params: dict = {}
        if args.robot_id is not None:
            clauses.append("id = :rid")
            params["rid"] = args.robot_id
        if args.user_id is not None:
            clauses.append("user_id = :uid")
            params["uid"] = args.user_id
        where = " AND ".join(clauses)
        rows = db.execute(
            text(f"SELECT id, type, config FROM {schema}.robots WHERE {where} ORDER BY id"),
            params,
        ).mappings().all()

        updated = 0
        for row in rows:
            rid = int(row["id"])
            rtype = int(row["type"] or 2)
            raw = dict(row["config"] or {})
            broker = str(raw.get("broker_type") or "tinvest").lower()
            normalized = migrate_v2_to_v3(raw, robot_type=rtype, broker_type=broker)
            changed = not config_equals(raw, normalized)
            print(
                f"robot_id={rid} type={rtype} "
                f"config_version={normalized.get('config_version')} "
                f"schema_profile={normalized.get('schema_profile')} "
                f"broker_type={normalized.get('broker_type')} "
                f"{'CHANGED' if changed else 'ok'}"
            )
            if changed and not args.dry_run:
                db.execute(
                    text(f"UPDATE {schema}.robots SET config = CAST(:cfg AS jsonb) WHERE id = :rid"),
                    {"cfg": json.dumps(normalized, ensure_ascii=False), "rid": rid},
                )
                updated += 1

        if not args.dry_run:
            db.commit()
        print(f"done: scanned={len(rows)} updated={updated} dry_run={args.dry_run}")
        return 0
    except Exception as ex:
        db.rollback()
        print(f"FAILED: {ex}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
