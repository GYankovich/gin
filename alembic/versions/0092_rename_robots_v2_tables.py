"""Rename robots_v2* tables to robots / robot_* (Wave 4).

Revision ID: 0092_rename_robots_v2
Revises: 0091_drop_legacy_robots
"""

from alembic import op

revision = "0092_rename_robots_v2"
down_revision = "0091_drop_legacy_robots"
branch_labels = None
depends_on = None

# Children first so intermediate names never collide with parents we rename later.
_RENAMES = [
    ("robots_v2_fills", "robot_fills"),
    ("robots_v2_orders", "robot_orders"),
    ("robots_v2_decisions", "robot_decisions"),
    ("robots_v2_signals", "robot_signals"),
    ("robots_v2_cycles", "robot_cycles"),
    ("robots_v2_sessions", "robot_sessions"),
    ("robots_v2", "robots"),
]


def upgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f'ALTER TABLE IF EXISTS "{old}" RENAME TO "{new}"')


def downgrade() -> None:
    for old, new in reversed(_RENAMES):
        op.execute(f'ALTER TABLE IF EXISTS "{new}" RENAME TO "{old}"')
