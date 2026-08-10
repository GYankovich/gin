"""BRD-ARCH-02: equity dividends, TQBR cache, backtest_runs metadata [ref: BRD-ARCH-02].

Revision ID: 0030_equity_div_tqbr_bt (≤32 chars for alembic_version.version_num)
Revises: 0029_shared_moex_candles
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0030_equity_div_tqbr_bt"
down_revision = "0029_shared_moex_candles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equity_dividend_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_corp_action_id", sa.String(160), nullable=False),
        sa.Column("secid", sa.String(24), nullable=False),
        sa.Column("ticker", sa.String(24), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("amount_per_share", sa.Numeric(20, 9), nullable=True),
        sa.Column("currency", sa.String(12), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("source", "external_corp_action_id", name="uq_equity_dividend_events_source_ext")
    )
    op.create_index(
        "ix_equity_dividend_ticker_ex",
        "equity_dividend_events",
        ["ticker", "ex_date"],
        unique=False
    )
    op.create_index(
        "ix_equity_dividend_ex_date",
        "equity_dividend_events",
        ["ex_date"],
        unique=False
    )
    op.create_index(
        "ix_equity_dividend_secid",
        "equity_dividend_events",
        ["secid"],
        unique=False
    )

    op.create_table(
        "tqbr_securities",
        sa.Column("secid", sa.String(24), primary_key=True, nullable=False),
        sa.Column("shortname", sa.Text(), nullable=True),
        sa.Column("isin", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False)
    )
    op.create_index(
        "ix_tqbr_securities_secid",
        "tqbr_securities",
        ["secid"],
        unique=False
    )

    op.add_column(
        "backtest_runs",
        sa.Column("user_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_backtest_runs_user_id",
        "backtest_runs",
        "user",
        ["user_id"],
        ["id"],
        ondelete="SET NULL"
    )
    op.alter_column(
        "backtest_runs",
        "robot_id",
        existing_type=sa.BigInteger(),
        nullable=True
    )
    op.add_column(
        "backtest_runs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column(
        "backtest_runs",
        sa.Column("run_phase", sa.String(40), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("current_trade_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("trade_dates_total", sa.Integer(), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("trade_dates_remaining", sa.Integer(), nullable=True)
    )
    op.add_column(
        "backtest_runs",
        sa.Column("partial_result", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.create_index(
        "ix_backtest_runs_user_started",
        "backtest_runs",
        ["user_id", "started_at"],
        unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_user_started", table_name="backtest_runs")
    op.drop_column("backtest_runs", "partial_result")
    op.drop_column("backtest_runs", "trade_dates_remaining")
    op.drop_column("backtest_runs", "trade_dates_total")
    op.drop_column("backtest_runs", "current_trade_date")
    op.drop_column("backtest_runs", "run_phase")
    op.drop_column("backtest_runs", "cancel_requested")
    op.alter_column(
        "backtest_runs",
        "robot_id",
        existing_type=sa.BigInteger(),
        nullable=False
    )
    op.drop_constraint("fk_backtest_runs_user_id", "backtest_runs", type_="foreignkey")
    op.drop_column("backtest_runs", "user_id")

    op.drop_index("ix_tqbr_securities_secid", table_name="tqbr_securities")
    op.drop_table("tqbr_securities")

    op.drop_index("ix_equity_dividend_secid", table_name="equity_dividend_events")
    op.drop_index("ix_equity_dividend_ex_date", table_name="equity_dividend_events")
    op.drop_index("ix_equity_dividend_ticker_ex", table_name="equity_dividend_events")
    op.drop_table("equity_dividend_events")
