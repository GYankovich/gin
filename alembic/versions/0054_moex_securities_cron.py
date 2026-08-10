"""Expand tqbr_securities to MOEX shares+bonds reference; add cron_table.

Revision ID: 0054_moex_securities_cron
Revises: 0053_drop_orphan_public_tables
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0054_moex_securities_cron"
down_revision = "0053_drop_orphan_public_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE tqbr_securities
                ALTER COLUMN secid TYPE VARCHAR(32)
            """
        )
    )
    op.add_column("tqbr_securities", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("tqbr_securities", sa.Column("regnumber", sa.String(64), nullable=True))
    op.add_column("tqbr_securities", sa.Column("instrument_type", sa.String(32), nullable=True))
    op.add_column("tqbr_securities", sa.Column("instrument_group", sa.String(32), nullable=True))
    op.add_column("tqbr_securities", sa.Column("engine", sa.String(16), nullable=True))
    op.add_column("tqbr_securities", sa.Column("market", sa.String(16), nullable=True))
    op.add_column("tqbr_securities", sa.Column("primary_board", sa.String(16), nullable=True))
    op.add_column(
        "tqbr_securities",
        sa.Column("is_traded", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("tqbr_securities", sa.Column("currency", sa.String(12), nullable=True))
    op.add_column("tqbr_securities", sa.Column("face_value", sa.Numeric(20, 6), nullable=True))
    op.add_column("tqbr_securities", sa.Column("maturity_date", sa.Date(), nullable=True))
    op.add_column("tqbr_securities", sa.Column("lot_size", sa.Integer(), nullable=True))
    op.add_column("tqbr_securities", sa.Column("issuer", sa.Text(), nullable=True))
    op.add_column("tqbr_securities", sa.Column("list_level", sa.Integer(), nullable=True))
    op.add_column(
        "tqbr_securities",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "tqbr_securities",
        sa.Column(
            "extra_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Existing rows came from TQBR-only sync.
    op.execute(
        sa.text(
            """
            UPDATE tqbr_securities
            SET
                primary_board = COALESCE(primary_board, 'TQBR'),
                market = COALESCE(market, 'shares'),
                engine = COALESCE(engine, 'stock'),
                instrument_group = COALESCE(instrument_group, 'stock_shares'),
                instrument_type = COALESCE(instrument_type, 'common_share'),
                is_active = COALESCE(is_active, true),
                is_traded = COALESCE(is_traded, true)
            """
        )
    )

    op.create_index("ix_tqbr_securities_primary_board", "tqbr_securities", ["primary_board"])
    op.create_index("ix_tqbr_securities_instrument_group", "tqbr_securities", ["instrument_group"])
    op.create_index("ix_tqbr_securities_isin", "tqbr_securities", ["isin"])
    op.create_index("ix_tqbr_securities_is_active", "tqbr_securities", ["is_active"])
    op.create_index("ix_tqbr_securities_market", "tqbr_securities", ["market"])

    op.create_table(
        "cron_table",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("robot_name", sa.String(64), nullable=False),
        sa.Column("fixed_delay", sa.Integer(), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("robot_name", name="uq_cron_table_robot_name"),
    )
    op.create_index("ix_cron_table_next_run", "cron_table", ["next_run"])
    op.create_index("ix_cron_table_is_active", "cron_table", ["is_active"])

    op.execute(
        sa.text(
            """
            INSERT INTO cron_table (robot_name, fixed_delay, next_run, is_active)
            VALUES ('moex_securities_updater', 86400, CURRENT_TIMESTAMP, true)
            ON CONFLICT (robot_name) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("cron_table")
    op.drop_index("ix_tqbr_securities_market", table_name="tqbr_securities")
    op.drop_index("ix_tqbr_securities_is_active", table_name="tqbr_securities")
    op.drop_index("ix_tqbr_securities_isin", table_name="tqbr_securities")
    op.drop_index("ix_tqbr_securities_instrument_group", table_name="tqbr_securities")
    op.drop_index("ix_tqbr_securities_primary_board", table_name="tqbr_securities")
    for col in (
        "extra_data",
        "is_active",
        "list_level",
        "issuer",
        "lot_size",
        "maturity_date",
        "face_value",
        "currency",
        "is_traded",
        "primary_board",
        "market",
        "engine",
        "instrument_group",
        "instrument_type",
        "regnumber",
        "name",
    ):
        op.drop_column("tqbr_securities", col)
    op.execute(
        sa.text(
            """
            ALTER TABLE tqbr_securities
                ALTER COLUMN secid TYPE VARCHAR(24)
            """
        )
    )
