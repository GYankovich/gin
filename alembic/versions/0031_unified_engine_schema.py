"""BRD-ARCH-03: unified engine schema (backtest_decisions, risk_events).

Revision ID: 0031_unified_engine_schema
Revises: 0030_equity_div_tqbr_bt
Create Date: 2026-05-15

Что делает миграция (см. docs/BRD-ARCH-03-unified-engine-architecture.md §10–§11):

1. Переносит runtime-DDL `{schema}.backtest_decisions` (создаётся в `service.py`
   на лету) в нормальную миграцию — таблица обязательная для нового
   `BacktestRecorder`, она должна существовать до старта приложения.

2. Создаёт две новые таблицы для журналирования событий риск-менеджмента,
   которые понадобятся универсальному `RiskManager` (BRD-ARCH-03 §7):
   - `{schema}.backtest_risk_events`
   - `{schema}.robot_risk_events`

Миграция идемпотентна (`IF NOT EXISTS`), чтобы не мешать существующим стендам,
где `backtest_decisions` уже создан runtime-DDL.
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0031_unified_engine_schema"
down_revision = "0030_equity_div_tqbr_bt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. {schema}.backtest_decisions -----------------------------------
    bind.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_decisions (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'PIPELINE',
            result VARCHAR(20) NOT NULL,
            reason TEXT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_backtest_decisions_run_day
        ON {SCHEMA}.backtest_decisions(run_id, trade_date)
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_backtest_decisions_run_ticker
        ON {SCHEMA}.backtest_decisions(run_id, ticker)
    """))

    # --- 2. {schema}.backtest_risk_events ---------------------------------
    bind.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_risk_events (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            secid VARCHAR(24) NULL,
            figi VARCHAR(64) NULL,
            signal_id VARCHAR(64) NULL,
            reason_code VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_backtest_risk_events_run_ts
        ON {SCHEMA}.backtest_risk_events(run_id, ts)
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_backtest_risk_events_reason
        ON {SCHEMA}.backtest_risk_events(run_id, reason_code)
    """))

    # --- 3. {schema}.robot_risk_events ------------------------------------
    bind.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.robot_risk_events (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            secid VARCHAR(24) NULL,
            figi VARCHAR(64) NULL,
            signal_id VARCHAR(64) NULL,
            reason_code VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_robot_risk_events_robot_ts
        ON {SCHEMA}.robot_risk_events(robot_id, ts)
    """))
    bind.execute(sa.text(f"""
        CREATE INDEX IF NOT EXISTS idx_robot_risk_events_reason
        ON {SCHEMA}.robot_risk_events(robot_id, reason_code)
    """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.robot_risk_events"))
    bind.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_risk_events"))
    # `backtest_decisions` оставляем — её всё ещё создаёт runtime-DDL в service.py
    # как fallback; полноценное удаление будет в отдельной миграции после удаления
    # runtime-DDL из кода (см. BRD-ARCH-03 §11).
