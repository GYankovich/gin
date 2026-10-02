from sqlalchemy import create_engine, text
from app.core.config import settings

e = create_engine(settings.DATABASE_URL)
c = e.connect()
print(
    "any_success",
    c.execute(
        text(
            """
            SELECT id, board, status, left(coalesce(error_message,''),80), snapshot_time
            FROM market_snapshot
            WHERE status='SUCCESS'
            ORDER BY snapshot_time DESC
            LIMIT 5
            """
        )
    ).fetchall(),
)
print(
    "any_tqbr",
    c.execute(
        text(
            """
            SELECT id, status, left(coalesce(error_message,''),120), snapshot_time
            FROM market_snapshot
            WHERE board='TQBR'
            ORDER BY snapshot_time DESC
            LIMIT 5
            """
        )
    ).fetchall(),
)
c.close()
