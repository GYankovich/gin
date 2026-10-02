from sqlalchemy import create_engine, text
from app.core.config import settings

e = create_engine(settings.DATABASE_URL)
c = e.connect()
rows = c.execute(
    text(
        """
        SELECT id, board, status, error_message, snapshot_time, created_at
        FROM market_snapshot
        ORDER BY created_at DESC
        LIMIT 10
        """
    )
).mappings().all()
for r in rows:
    print(dict(r))
c.close()
