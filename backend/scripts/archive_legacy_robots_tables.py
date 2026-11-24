"""Archive legacy robot/DMS tables to gzip CSV before Wave 2 DROP.

Usage (from backend/):
  python -m scripts.archive_legacy_robots_tables
  python -m scripts.archive_legacy_robots_tables --out ../archives/legacy_robots

Writes one <table>.csv.gz per existing table plus manifest.json with row counts.
Does not drop anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from gzip import GzipFile
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings

# Children → parent (same set as alembic 0091).
TABLES = [
    "robot_order_events",
    "robot_signals",
    "robot_decisions",
    "robot_run_cycles",
    "robot_logs",
    "robot_session_logs",
    "robot_execution_logs",
    "robot_risk_events",
    "robot_trades",
    "robot_schedules",
    "robot_strategies",
    "robot_backtest_runs",
    "robot_configs",
    "account_orders",
    "dms_subscriptions",
    "daily_universe",
    "crypto_universe_daily",
    "robots",
]


def _engine():
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT to_regclass(:qname)"),
            {"qname": f"public.{name}"},
        ).scalar()
    )


def _count(conn, name: str) -> int:
    return int(conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0)


def _columns(raw_conn, name: str) -> list[str]:
    with raw_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (name,),
        )
        return [r[0] for r in cur.fetchall()]


def _archive_table(raw_conn, name: str, out_path: Path) -> None:
    cols = _columns(raw_conn, name)
    with GzipFile(out_path, mode="wb", compresslevel=6) as gz:
        gz.write((",".join(cols) + "\n").encode("utf-8"))
        with raw_conn.cursor() as cur:
            cur.copy_expert(
                f'COPY "{name}" TO STDOUT WITH (FORMAT csv, HEADER false)',
                gz,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: ../archives/legacy_robots_<UTC stamp>)",
    )
    parser.add_argument(
        "--skip-empty",
        action="store_true",
        help="Skip tables with 0 rows (still listed in manifest)",
    )
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir: Path = args.out or (
        Path(__file__).resolve().parents[2] / "archives" / f"legacy_robots_{stamp}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = _engine()
    manifest: dict = {
        "created_at": stamp,
        "database": settings.DB_NAME,
        "schema": "public",
        "tables": {},
    }

    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        for name in TABLES:
            entry: dict = {"exists": False, "rows": 0, "file": None, "skipped": False}
            if not _table_exists(conn, name):
                entry["missing"] = True
                manifest["tables"][name] = entry
                print(f"{name}: MISSING")
                continue
            entry["exists"] = True
            n = _count(conn, name)
            entry["rows"] = n
            if args.skip_empty and n == 0:
                entry["skipped"] = True
                manifest["tables"][name] = entry
                print(f"{name}: 0 rows (skipped)")
                continue
            out_file = out_dir / f"{name}.csv.gz"
            print(f"{name}: archiving {n} rows -> {out_file.name} ...", flush=True)
            _archive_table(raw, name, out_file)
            entry["file"] = out_file.name
            entry["bytes"] = out_file.stat().st_size
            manifest["tables"][name] = entry
            print(f"{name}: done ({n} rows, {entry['bytes']} bytes)", flush=True)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
