"""Packages: package + package_feature; user.package_code → package.id.

Revision ID: 0076_package_feature
Revises: 0075_user_token_session_meta

Schema notes:
- user.package_code is BIGINT FK to package.id (numeric link, name kept as package_code).
- package_feature.package_id links features to a package (required; not listed in the brief
  but otherwise features cannot be scoped per package).
- Audit columns follow project convention: usercre / date_creation / usermod / date_modification
  (brief shorthand: userce / datcre / usermod / datmod).
- status 0/1 via dictionary PACKAGE.STATUS and PACKAGE_FEATURE.STATUS.
"""

from alembic import op

revision = "0076_package_feature"
down_revision = "0075_user_token_session_meta"
branch_labels = None
depends_on = None

_FEATURES = ("dashboard", "portfolio", "robots", "backtest")


def upgrade() -> None:
    # Drop previous draft shape if this revision was applied partially in a branch.
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS package_code')
    op.execute("DROP TABLE IF EXISTS package_feature")
    op.execute("DROP TABLE IF EXISTS package")

    op.execute(
        """
        CREATE TABLE package (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            status INTEGER NOT NULL DEFAULT 1,
            usercre BIGINT NULL,
            date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usermod BIGINT NULL,
            date_modification TIMESTAMPTZ NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_package_status ON package (status)")

    op.execute(
        """
        CREATE TABLE package_feature (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES package (id) ON DELETE CASCADE,
            feature VARCHAR(64) NOT NULL,
            status INTEGER NOT NULL DEFAULT 0,
            usercre BIGINT NULL,
            date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usermod BIGINT NULL,
            date_modification TIMESTAMPTZ NULL,
            CONSTRAINT uq_package_feature_package_feature UNIQUE (package_id, feature)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_package_feature_package_id ON package_feature (package_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_package_feature_feature ON package_feature (feature)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_package_feature_status ON package_feature (status)"
    )

    for table_name, rows in (
        (
            "PACKAGE",
            (
                (0, "off", "Выкл", "Пакет выключен"),
                (1, "on", "Вкл", "Пакет включён"),
            ),
        ),
        (
            "PACKAGE_FEATURE",
            (
                (0, "off", "Выкл", "Фича пакета выключена"),
                (1, "on", "Вкл", "Фича пакета включена"),
            ),
        ),
    ):
        for num_value, string_value, name, description in rows:
            op.execute(
                f"""
                INSERT INTO dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    '{table_name}',
                    'STATUS',
                    {num_value},
                    '{string_value}',
                    '{name}',
                    '{description}',
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM dictionary
                     WHERE table_name = '{table_name}'
                       AND column_name = 'STATUS'
                       AND num_value = {num_value}
                )
                """
            )

    op.execute(
        """
        INSERT INTO package (id, name, status, date_creation)
        VALUES (1, 'Полный', 1, CURRENT_TIMESTAMP)
        """
    )
    op.execute("SELECT setval(pg_get_serial_sequence('package', 'id'), (SELECT MAX(id) FROM package))")

    for feature in _FEATURES:
        op.execute(
            f"""
            INSERT INTO package_feature (package_id, feature, status, date_creation)
            VALUES (1, '{feature}', 1, CURRENT_TIMESTAMP)
            """
        )

    op.execute(
        """
        ALTER TABLE "user"
            ADD COLUMN package_code BIGINT NOT NULL DEFAULT 1
                REFERENCES package (id)
        """
    )
    op.execute(
        """
        UPDATE "user"
           SET package_code = 1
         WHERE package_code IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_package_code ON \"user\" (package_code)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_package_code")
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS package_code')
    op.execute("DROP INDEX IF EXISTS ix_package_feature_status")
    op.execute("DROP INDEX IF EXISTS ix_package_feature_feature")
    op.execute("DROP INDEX IF EXISTS ix_package_feature_package_id")
    op.execute("DROP TABLE IF EXISTS package_feature")
    op.execute("DROP INDEX IF EXISTS ix_package_status")
    op.execute("DROP TABLE IF EXISTS package")
    op.execute(
        """
        DELETE FROM dictionary
         WHERE table_name IN ('PACKAGE', 'PACKAGE_FEATURE')
           AND column_name = 'STATUS'
        """
    )
