"""Robots v2 audit trail tables (sessions, cycles, signals, decisions, orders, fills).

Revision ID: 0059_robots_v2_audit
Revises: 0058_moex_index_cache
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0059_robots_v2_audit"
down_revision = "0058_moex_index_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "robots_v2_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("virtual_capital", sa.Numeric(20, 4), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_sessions_robot_started", "robots_v2_sessions", ["robot_id", "started_at"])

    op.create_table(
        "robots_v2_cycles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(length=32), nullable=False, server_default="poll"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("equity", sa.Numeric(20, 4), nullable=True),
        sa.Column("stats", JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["session_id"], ["robots_v2_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_cycles_robot_started", "robots_v2_cycles", ["robot_id", "started_at"])
    op.create_index("ix_robots_v2_cycles_session_id", "robots_v2_cycles", ["session_id"])

    op.create_table(
        "robots_v2_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", UUID(as_uuid=True), nullable=False),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["robots_v2_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_signals_cycle_id", "robots_v2_signals", ["cycle_id"])

    op.create_table(
        "robots_v2_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", UUID(as_uuid=True), nullable=False),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("ticker", sa.String(length=32), nullable=True),
        sa.Column("context", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["robots_v2_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_decisions_robot_created", "robots_v2_decisions", ["robot_id", "created_at"])
    op.create_index("ix_robots_v2_decisions_cycle_id", "robots_v2_decisions", ["cycle_id"])

    op.create_table(
        "robots_v2_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_id", UUID(as_uuid=True), nullable=False),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["robots_v2_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_orders_robot_submitted", "robots_v2_orders", ["robot_id", "submitted_at"])
    op.create_index("ix_robots_v2_orders_broker_order_id", "robots_v2_orders", ["broker_order_id"])
    op.create_index("ix_robots_v2_orders_cycle_id", "robots_v2_orders", ["cycle_id"])

    op.create_table(
        "robots_v2_fills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.Column("pnl", sa.Numeric(20, 6), nullable=True),
        sa.Column("commission", sa.Numeric(20, 6), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["robots_v2_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robots_v2_fills_robot_filled", "robots_v2_fills", ["robot_id", "filled_at"])
    op.create_index("ix_robots_v2_fills_order_id", "robots_v2_fills", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_robots_v2_fills_order_id", table_name="robots_v2_fills")
    op.drop_index("ix_robots_v2_fills_robot_filled", table_name="robots_v2_fills")
    op.drop_table("robots_v2_fills")
    op.drop_index("ix_robots_v2_orders_cycle_id", table_name="robots_v2_orders")
    op.drop_index("ix_robots_v2_orders_broker_order_id", table_name="robots_v2_orders")
    op.drop_index("ix_robots_v2_orders_robot_submitted", table_name="robots_v2_orders")
    op.drop_table("robots_v2_orders")
    op.drop_index("ix_robots_v2_decisions_cycle_id", table_name="robots_v2_decisions")
    op.drop_index("ix_robots_v2_decisions_robot_created", table_name="robots_v2_decisions")
    op.drop_table("robots_v2_decisions")
    op.drop_index("ix_robots_v2_signals_cycle_id", table_name="robots_v2_signals")
    op.drop_table("robots_v2_signals")
    op.drop_index("ix_robots_v2_cycles_session_id", table_name="robots_v2_cycles")
    op.drop_index("ix_robots_v2_cycles_robot_started", table_name="robots_v2_cycles")
    op.drop_table("robots_v2_cycles")
    op.drop_index("ix_robots_v2_sessions_robot_started", table_name="robots_v2_sessions")
    op.drop_table("robots_v2_sessions")
