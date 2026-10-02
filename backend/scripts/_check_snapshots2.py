from sqlalchemy import create_engine, text
from app.core.config import settings

e = create_engine(settings.DATABASE_URL)
c = e.connect()
print(
    "success",
    c.execute(
        text(
            """
            SELECT id, status, snapshot_time
            FROM market_snapshot
            WHERE board='TQBR' AND status='SUCCESS'
            ORDER BY snapshot_time DESC
            LIMIT 3
            """
        )
    ).fetchall(),
)
print(
    "counts_2d",
    c.execute(
        text(
            """
            SELECT status, count(*)
            FROM market_snapshot
            WHERE board='TQBR' AND created_at > NOW() - interval '2 days'
            GROUP BY status
            """
        )
    ).fetchall(),
)
c.close()
