"""Progress percent and ETA for history-backtest runs.

Revision ID: 0032_backtest_progress_eta
Revises: 0031_unified_engine_schema
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0032_backtest_progress_eta"
down_revision = "0031_unified_engine_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("progress_percent", sa.Numeric(5, 2), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("eta_seconds", sa.Integer(), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("eta_confidence", sa.String(10), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("phase_units_done", sa.Integer(), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("phase_units_total", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "phase_units_total")
    op.drop_column("backtest_runs", "phase_units_done")
    op.drop_column("backtest_runs", "eta_confidence")
    op.drop_column("backtest_runs", "eta_seconds")
    op.drop_column("backtest_runs", "progress_percent")
