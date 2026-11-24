"""Drop legacy robots / DMS child tables (Wave 2).

Keeps market_snapshot*, candles_cache, backtest_runs/metrics (still used by
robots_v2 universe preview, engine, and recommendations).

Revision ID: 0091_drop_legacy_robots
Revises: 0090_api_tokens_mod
"""

from alembic import op

revision = "0091_drop_legacy_robots"
down_revision = "0090_api_tokens_mod"
branch_labels = None
depends_on = None

# Children first, parent `robots` last.
_DROP_TABLES = [
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


def upgrade() -> None:
    for name in _DROP_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')


def downgrade() -> None:
    # Irreversible: restore from archives/legacy_robots_*/manifest.json dumps.
    raise NotImplementedError(
        "0091_drop_legacy_robots cannot recreate schema; restore from CSV.gz archive"
    )
