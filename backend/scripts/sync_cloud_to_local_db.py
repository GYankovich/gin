#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Sequence

import psycopg2
from psycopg2 import sql


SCHEMAS: tuple[str, ...] = ("ganaly", "backtest")
TARGET_SCHEMA = "public"
TARGET_TABLE_OVERRIDES: dict[tuple[str, str], str] = {
    ("ganaly", "users"): "user",
}


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

SOURCE_CONFIG = DbConfig(
    host="147.45.235.27",
    port=5432,
    database="test_db",
    user="gen_user",
    password="yankovich",
)

LOCAL_CONFIG = DbConfig(
    host="127.0.0.1",
    port=5432,
    database="gin",
    user="gin_app",
    password="QwantiGYANk697",
)


def _connect(cfg: DbConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.database,
        user=cfg.user,
        password=cfg.password,
    )


def compare_schema_signatures(source: DbConfig, target: DbConfig) -> None:
    def fetch_alembic_versions(cur) -> tuple[str, ...]:
        cur.execute("SELECT to_regclass('public.alembic_version')")
        if cur.fetchone()[0] is None:
            return tuple()
        cur.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
        return tuple(r[0] for r in cur.fetchall())

    def fetch_source_signature(cfg: DbConfig):
        with _connect(cfg) as conn, conn.cursor() as cur:
            versions = fetch_alembic_versions(cur)
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                ORDER BY table_name
                """,
                (list(SCHEMAS),),
            )
            tables = set(r[0] for r in cur.fetchall())
            cur.execute(
                """
                SELECT table_name, column_name, data_type, udt_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = ANY(%s)
                ORDER BY table_name, ordinal_position
                """,
                (list(SCHEMAS),),
            )
            columns = set(cur.fetchall())
        return versions, tables, columns

    def fetch_target_signature(cfg: DbConfig):
        with _connect(cfg) as conn, conn.cursor() as cur:
            versions = fetch_alembic_versions(cur)
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = %s
                ORDER BY table_name
                """,
                (TARGET_SCHEMA,),
            )
            tables = set(r[0] for r in cur.fetchall())
            cur.execute(
                """
                SELECT table_name, column_name, data_type, udt_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (TARGET_SCHEMA,),
            )
            columns = set(cur.fetchall())
        return versions, tables, columns

    s_ver, s_tables, s_cols = fetch_source_signature(source)
    t_ver, t_tables, t_cols = fetch_target_signature(target)

    missing_tables = sorted(s_tables - t_tables)
    extra_tables = sorted(t_tables - s_tables)
    missing_cols = sorted(s_cols - t_cols)
    extra_cols = sorted(t_cols - s_cols)

    print("\n[Migration/Schema check]")
    print(f"source alembic_version: {list(s_ver)}")
    print(f"target alembic_version: {list(t_ver)}")
    print(f"missing tables in target: {len(missing_tables)}")
    print(f"extra tables in target: {len(extra_tables)}")
    print(f"missing columns in target: {len(missing_cols)}")
    print(f"extra columns in target: {len(extra_cols)}")

    if missing_tables:
        print("first missing tables in local public:", missing_tables[:10])
    if extra_tables:
        print("first extra tables in local public:", extra_tables[:10])
    if missing_cols:
        print("first missing columns:", missing_cols[:10])
    if extra_cols:
        print("first extra columns:", extra_cols[:10])


def truncate_local_database(target: DbConfig) -> None:
    with _connect(target) as conn, conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            DECLARE r RECORD;
            BEGIN
                FOR r IN
                    SELECT schemaname, tablename
                    FROM pg_tables
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                LOOP
                    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', r.schemaname, r.tablename);
                END LOOP;

                FOR r IN
                    SELECT sequence_schema, sequence_name
                    FROM information_schema.sequences
                    WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema')
                LOOP
                    EXECUTE format('DROP SEQUENCE IF EXISTS %I.%I CASCADE', r.sequence_schema, r.sequence_name);
                END LOOP;
            END
            $$;
            """
        )
        conn.commit()


def rebuild_local_schema_with_migrations() -> None:
    with _connect(LOCAL_CONFIG) as conn, conn.cursor() as cur:
        # Некоторые исторические миграции явно пишут в ganaly/backtest.
        # Создаем схемы заранее, чтобы цепочка могла выполниться до head.
        cur.execute("CREATE SCHEMA IF NOT EXISTS ganaly")
        cur.execute("CREATE SCHEMA IF NOT EXISTS backtest")
        conn.commit()

    command = [sys.executable, "-m", "alembic", "upgrade", "head"]
    print(f"\n[alembic] {' '.join(command)}")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(command, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed with code {proc.returncode}")


def copy_data_into_public(source: DbConfig, target: DbConfig) -> None:
    with _connect(source) as s_conn, _connect(target) as t_conn:
        with s_conn.cursor() as s_cur, t_conn.cursor() as t_cur:
            s_cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                ORDER BY table_schema, table_name
                """,
                (list(SCHEMAS),),
            )
            source_tables = s_cur.fetchall()

            copied = 0
            skipped: list[str] = []
            failed: list[str] = []
            for src_schema, table_name in source_tables:
                t_cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                    """,
                    (TARGET_SCHEMA, table_name),
                )
                if not t_cur.fetchone()[0]:
                    skipped.append(f"{src_schema}.{table_name}")
                    continue

                s_cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (src_schema, table_name),
                )
                source_columns = [r[0] for r in s_cur.fetchall()]
                t_cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (TARGET_SCHEMA, table_name),
                )
                target_columns = {r[0] for r in t_cur.fetchall()}

                columns = [c for c in source_columns if c in target_columns]
                if not columns:
                    continue

                col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
                copy_out = sql.SQL("COPY (SELECT {} FROM {}.{}) TO STDOUT WITH CSV").format(
                    col_sql,
                    sql.Identifier(src_schema),
                    sql.Identifier(table_name),
                )
                copy_in = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH CSV").format(
                    sql.Identifier(TARGET_SCHEMA),
                    sql.Identifier(table_name),
                    col_sql,
                )

                try:
                    t_cur.execute("SAVEPOINT copy_table_sp")
                    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".csv", delete=True) as tmp:
                        s_cur.copy_expert(copy_out.as_string(s_conn), tmp)
                        tmp.flush()
                        tmp.seek(0)
                        t_cur.copy_expert(copy_in.as_string(t_conn), tmp)
                    t_cur.execute("RELEASE SAVEPOINT copy_table_sp")
                    copied += 1
                except Exception:  # noqa: BLE001
                    t_cur.execute("ROLLBACK TO SAVEPOINT copy_table_sp")
                    failed.append(f"{src_schema}.{table_name}")

        t_conn.commit()

    print(f"[data copy] copied {copied} tables to {TARGET_SCHEMA}")
    if skipped:
        print(f"[data copy] skipped {len(skipped)} tables (not found in {TARGET_SCHEMA})")
        print("first skipped:", skipped[:10])
    if failed:
        print(f"[data copy] failed {len(failed)} tables (constraint/type conflicts)")
        print("first failed:", failed[:10])


def _mirror_table_name(src_schema: str, table_name: str) -> str:
    return f"{src_schema}__{table_name}"


def copy_all_tables_strict(source: DbConfig, target: DbConfig) -> None:
    """Strict mode: copy every source table into public, using mirrors if needed."""
    with _connect(source) as s_conn, _connect(target) as t_conn:
        with s_conn.cursor() as s_cur, t_conn.cursor() as t_cur:
            s_cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                ORDER BY table_schema, table_name
                """,
                (list(SCHEMAS),),
            )
            source_tables = s_cur.fetchall()

            # Detect collisions between ganaly/backtest table names.
            s_cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                GROUP BY table_name
                HAVING COUNT(*) > 1
                """,
                (list(SCHEMAS),),
            )
            collisions = {r[0] for r in s_cur.fetchall()}

            copied_main = 0
            copied_mirror = 0
            unresolved: list[str] = []
            truncated_targets: set[str] = set()

            def copy_into_table(
                src_schema_name: str,
                src_table_name: str,
                dst_table_name: str,
                dst_columns: list[str],
            ) -> None:
                src_cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in dst_columns)
                out_sql = sql.SQL("COPY (SELECT {} FROM {}.{}) TO STDOUT WITH CSV").format(
                    src_cols_sql, sql.Identifier(src_schema_name), sql.Identifier(src_table_name)
                )
                in_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH CSV").format(
                    sql.Identifier(TARGET_SCHEMA), sql.Identifier(dst_table_name), src_cols_sql
                )
                with tempfile.NamedTemporaryFile(mode="w+b", suffix=".csv", delete=True) as tmp:
                    s_cur.copy_expert(out_sql.as_string(s_conn), tmp)
                    tmp.flush()
                    tmp.seek(0)
                    t_cur.copy_expert(in_sql.as_string(t_conn), tmp)

            def ensure_mirror_and_copy(src_schema_name: str, src_table_name: str, col_defs_local: list[tuple[str, str]]) -> None:
                mirror_name = _mirror_table_name(src_schema_name, src_table_name)
                t_cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                    """,
                    (TARGET_SCHEMA, mirror_name),
                )
                if not t_cur.fetchone()[0]:
                    create_cols = sql.SQL(", ").join(
                        sql.SQL("{} {}").format(sql.Identifier(cn), sql.SQL(ct))
                        for cn, ct in col_defs_local
                    )
                    create_sql = sql.SQL("CREATE TABLE {}.{} ({})").format(
                        sql.Identifier(TARGET_SCHEMA),
                        sql.Identifier(mirror_name),
                        create_cols,
                    )
                    t_cur.execute(create_sql)
                mirror_cols = [cn for cn, _ in col_defs_local]
                copy_into_table(src_schema_name, src_table_name, mirror_name, mirror_cols)

            for src_schema, table_name in source_tables:
                is_collision = table_name in collisions
                if (src_schema, table_name) in TARGET_TABLE_OVERRIDES:
                    target_name = TARGET_TABLE_OVERRIDES[(src_schema, table_name)]
                elif src_schema == "ganaly" or not is_collision:
                    target_name = table_name
                else:
                    target_name = _mirror_table_name(src_schema, table_name)

                # Source columns with physical types.
                s_cur.execute(
                    """
                    SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s
                      AND c.relname = %s
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    ORDER BY a.attnum
                    """,
                    (src_schema, table_name),
                )
                col_defs = s_cur.fetchall()
                if not col_defs:
                    unresolved.append(f"{src_schema}.{table_name}: no source columns")
                    continue

                col_names = [c for c, _ in col_defs]

                # Ensure target table exists. For mirror tables, create raw compatible table.
                t_cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                    """,
                    (TARGET_SCHEMA, target_name),
                )
                exists = t_cur.fetchone()[0]

                if not exists:
                    # If canonical table does not exist in local, create a raw-compatible table.
                    create_cols = sql.SQL(", ").join(
                        sql.SQL("{} {}").format(sql.Identifier(cn), sql.SQL(ct))
                        for cn, ct in col_defs
                    )
                    t_cur.execute(
                        sql.SQL("CREATE TABLE {}.{} ({})").format(
                            sql.Identifier(TARGET_SCHEMA),
                            sql.Identifier(target_name),
                            create_cols,
                        )
                    )

                # For canonical target tables, use intersection to avoid insert errors.
                t_cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (TARGET_SCHEMA, target_name),
                )
                target_columns = {r[0] for r in t_cur.fetchall()}
                use_columns = [c for c in col_names if c in target_columns]
                if not use_columns:
                    # No overlap with canonical contract -> full mirror fallback.
                    try:
                        t_cur.execute("SAVEPOINT strict_copy_sp")
                        ensure_mirror_and_copy(src_schema, table_name, col_defs)
                        t_cur.execute("RELEASE SAVEPOINT strict_copy_sp")
                        copied_mirror += 1
                        continue
                    except Exception as exc:  # noqa: BLE001
                        t_cur.execute("ROLLBACK TO SAVEPOINT strict_copy_sp")
                        unresolved.append(f"{src_schema}.{table_name}: {exc}")
                        continue

                try:
                    t_cur.execute("SAVEPOINT strict_copy_sp")
                    if target_name not in truncated_targets:
                        t_cur.execute(
                            sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE").format(
                                sql.Identifier(TARGET_SCHEMA),
                                sql.Identifier(target_name),
                            )
                        )
                        truncated_targets.add(target_name)
                    copy_into_table(src_schema, table_name, target_name, use_columns)
                    t_cur.execute("RELEASE SAVEPOINT strict_copy_sp")
                    if target_name == table_name:
                        copied_main += 1
                    else:
                        copied_mirror += 1
                except Exception as exc:  # noqa: BLE001
                    t_cur.execute("ROLLBACK TO SAVEPOINT strict_copy_sp")
                    # Canonical insert failed -> preserve source table into mirror.
                    try:
                        t_cur.execute("SAVEPOINT strict_copy_sp")
                        ensure_mirror_and_copy(src_schema, table_name, col_defs)
                        t_cur.execute("RELEASE SAVEPOINT strict_copy_sp")
                        copied_mirror += 1
                    except Exception as mirror_exc:  # noqa: BLE001
                        t_cur.execute("ROLLBACK TO SAVEPOINT strict_copy_sp")
                        unresolved.append(
                            f"{src_schema}.{table_name}: canonical={exc}; mirror={mirror_exc}"
                        )

        t_conn.commit()

    print(f"[strict copy] copied canonical tables: {copied_main}")
    print(f"[strict copy] copied mirror tables: {copied_mirror}")
    if unresolved:
        print(f"[strict copy] unresolved tables: {len(unresolved)}")
        print("first unresolved:", unresolved[:10])
        raise RuntimeError("strict copy finished with unresolved tables")
    print("[strict copy] all source tables copied")


def sync_sequence_values(source: DbConfig, target: DbConfig) -> None:
    seq_list_query = """
        SELECT ns.nspname AS schema_name, c.relname AS sequence_name
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND ns.nspname = ANY(%s)
        ORDER BY ns.nspname, c.relname
    """

    with _connect(source) as s_conn, _connect(target) as t_conn:
        with s_conn.cursor() as s_cur, t_conn.cursor() as t_cur:
            s_cur.execute(seq_list_query, (list(SCHEMAS),))
            sequences = s_cur.fetchall()

            updated = 0
            skipped = []
            for schema_name, sequence_name in sequences:
                s_cur.execute(
                    sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(sequence_name),
                    )
                )
                last_value, is_called = s_cur.fetchone()
                t_cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_class c
                        JOIN pg_namespace ns ON ns.oid = c.relnamespace
                        WHERE c.relkind = 'S'
                          AND ns.nspname = %s
                          AND c.relname = %s
                    )
                    """,
                    (TARGET_SCHEMA, sequence_name),
                )
                if not t_cur.fetchone()[0]:
                    skipped.append(f"{schema_name}.{sequence_name}")
                    continue
                t_cur.execute(
                    "SELECT setval(%s, %s, %s)",
                    (f"{TARGET_SCHEMA}.{sequence_name}", int(last_value), bool(is_called)),
                )
                updated += 1

        t_conn.commit()

    print(f"[sequence sync] updated {updated} sequences in {TARGET_SCHEMA}")
    if skipped:
        print(f"[sequence sync] skipped {len(skipped)} source sequences (no local match)")
        print("first skipped:", skipped[:10])


def apply_mirror_to_canonical(target: DbConfig) -> None:
    """
    Apply mirror tables back to canonical public tables.
    By default applies only ganaly mirrors; backtest collisions remain isolated.
    """
    preferred_order = [
        "user",
        "user_email",
        "user_phone",
        "user_token",
        "api_tokens",
        "portfolio_accounts",
        "robots",
        "robot_configs",
        "robot_schedules",
        "robot_strategies",
        "robot_execution_logs",
        "robot_logs",
        "robot_run_cycles",
        "robot_order_events",
        "robot_signals",
        "robot_trades",
        "portfolio_orders",
        "portfolio_operations",
        "portfolio_positions",
        "portfolio_snapshots",
        "account_orders",
        "backtest_runs",
        "backtest_metrics",
        "backtest_orders",
        "backtest_signals",
        "backtest_decisions",
        "backtest_portfolio_snapshots",
        "external_api_logs",
        "daily_universe",
        "dms_subscriptions",
        "crypto_universe_daily",
        "robot_backtest_runs",
    ]

    with _connect(target) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name LIKE 'ganaly\\_\\_%' ESCAPE '\\'
            ORDER BY table_name
            """
        )
        mirrors = [r[0] for r in cur.fetchall()]
        if not mirrors:
            print("[strict-apply] no ganaly mirror tables found")
            return

        mirror_to_target: dict[str, str] = {}
        for mirror in mirrors:
            target_name = mirror.replace("ganaly__", "", 1)
            if target_name == "users":
                # Legacy table with incompatible shape; keep as mirror-only dataset.
                continue
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                )
                """,
                (target_name,),
            )
            if cur.fetchone()[0]:
                mirror_to_target[mirror] = target_name

        if not mirror_to_target:
            print("[strict-apply] no applicable mirror->canonical mappings found")
            return

        # Apply in dependency-aware order first, then the rest.
        ordered_pairs: list[tuple[str, str]] = []
        used_mirrors: set[str] = set()
        target_to_mirror = {t: m for m, t in mirror_to_target.items()}
        for tname in preferred_order:
            mname = target_to_mirror.get(tname)
            if mname:
                ordered_pairs.append((mname, tname))
                used_mirrors.add(mname)
        for mname, tname in mirror_to_target.items():
            if mname not in used_mirrors:
                ordered_pairs.append((mname, tname))

        cur.execute("SET session_replication_role = replica")
        truncated: set[str] = set()
        applied = 0
        failed: list[str] = []
        try:
            for mirror_name, target_name in ordered_pairs:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                    ORDER BY ordinal_position
                    """,
                    (target_name,),
                )
                target_cols = [r[0] for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                    ORDER BY ordinal_position
                    """,
                    (mirror_name,),
                )
                mirror_cols = {r[0] for r in cur.fetchall()}
                cols = [c for c in target_cols if c in mirror_cols]
                if not cols:
                    continue

                try:
                    cur.execute("SAVEPOINT apply_sp")
                    if target_name not in truncated:
                        cur.execute(
                            sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE").format(
                                sql.Identifier(TARGET_SCHEMA),
                                sql.Identifier(target_name),
                            )
                        )
                        truncated.add(target_name)

                    cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
                    cur.execute(
                        sql.SQL("INSERT INTO {}.{} ({}) SELECT {} FROM {}.{}").format(
                            sql.Identifier(TARGET_SCHEMA),
                            sql.Identifier(target_name),
                            cols_sql,
                            cols_sql,
                            sql.Identifier(TARGET_SCHEMA),
                            sql.Identifier(mirror_name),
                        )
                    )
                    cur.execute("RELEASE SAVEPOINT apply_sp")
                    applied += 1
                except Exception as exc:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT apply_sp")
                    failed.append(f"{mirror_name}->{target_name}: {exc}")
        finally:
            cur.execute("SET session_replication_role = origin")

        conn.commit()
    if failed:
        print(f"[strict-apply] failed mappings: {len(failed)}")
        print("first failed:", failed[:10])
        raise RuntimeError("strict-apply finished with failed mappings")
    print(f"[strict-apply] applied mirrors to canonical tables: {applied}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync cloud Postgres schemas (ganaly/backtest) to local Postgres, "
            f"copying data into local {TARGET_SCHEMA} tables and syncing sequence values."
        )
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only print migration/schema comparison without modifying local database.",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip migration/schema comparison phase.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Strict 100%% mode: attempt to copy all source tables; if canonical table conflicts, "
            "store collision variant in public.<schema>__<table> and fail on unresolved tables."
        ),
    )
    parser.add_argument(
        "--strict-apply",
        action="store_true",
        help=(
            "Apply data from public.ganaly__* mirror tables into canonical public tables "
            "without rebuilding schema."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.strict_apply:
            print("[strict-apply] applying mirror tables to canonical public tables...")
            apply_mirror_to_canonical(LOCAL_CONFIG)
            print("[strict-apply] updating sequences from source metadata...")
            sync_sequence_values(SOURCE_CONFIG, LOCAL_CONFIG)
            print("\nDone.")
            return 0

        if not args.skip_check:
            compare_schema_signatures(SOURCE_CONFIG, LOCAL_CONFIG)
        if args.check_only:
            return 0

        print("\n[1/4] Dropping all local tables and sequences...")
        truncate_local_database(LOCAL_CONFIG)

        print("[2/4] Rebuilding local structure from migrations (public schema)...")
        rebuild_local_schema_with_migrations()

        print("[3/4] Copying data from cloud ganaly/backtest to local public...")
        if args.strict:
            copy_all_tables_strict(SOURCE_CONFIG, LOCAL_CONFIG)
        else:
            copy_data_into_public(SOURCE_CONFIG, LOCAL_CONFIG)

        print("[4/4] Synchronizing sequence values to local public...")
        sync_sequence_values(SOURCE_CONFIG, LOCAL_CONFIG)

        print("\nDone.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
