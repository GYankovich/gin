#!/usr/bin/env python3

"""

Миграция config роботов type=2 в схему v2 (П1/П2/П3).



  set PYTHONPATH=backend

  python backend/scripts/migrate_robot_configs_v2.py [--dry-run] [--robot-id 10]

"""

from __future__ import annotations



import argparse

import json

import sys



from sqlalchemy import text



from app.core.config import settings

from app.core.database import SessionLocal

from app.modules.robots.config.migration import migrate_robot_config_row





def main() -> int:

    p = argparse.ArgumentParser(description="Migrate trading robot configs to v2")

    p.add_argument("--dry-run", action="store_true")

    p.add_argument("--robot-id", type=int, default=None)

    args = p.parse_args()



    db = SessionLocal()

    schema = settings.DB_SCHEMA

    try:

        if args.robot_id:

            rows = db.execute(

                text(f"SELECT id, config FROM robots WHERE id = :rid AND type = 2"),

                {"rid": args.robot_id}

            ).mappings().all()

        else:

            rows = db.execute(

                text(f"SELECT id, config FROM robots WHERE type = 2 ORDER BY id")

            ).mappings().all()



        updated = 0

        for row in rows:

            rid = int(row["id"])

            new_cfg, changed = migrate_robot_config_row(row["config"])

            print(

                f"robot_id={rid} config_version={new_cfg.get('config_version')} "

                f"hist_enabled={new_cfg.get('historical_screening', {}).get('enabled')} "

                f"paper_input={new_cfg.get('paper_selection', {}).get('input')} "

                f"mode={new_cfg.get('universe_mode')} "

                f"{'CHANGED' if changed else 'ok'}"

            )

            if changed and not args.dry_run:

                db.execute(

                    text(f"UPDATE robots SET config = CAST(:cfg AS jsonb) WHERE id = :rid"),

                    {"cfg": json.dumps(new_cfg, ensure_ascii=False), "rid": rid}

                )

                updated += 1

        if not args.dry_run:

            db.commit()

        print(f"done: updated={updated} dry_run={args.dry_run}")

        return 0

    except Exception as ex:

        db.rollback()

        print(f"FAILED: {ex}", file=sys.stderr)

        return 1

    finally:

        db.close()





if __name__ == "__main__":

    raise SystemExit(main())

