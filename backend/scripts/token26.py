from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.config import settings

schema = settings.DB_SCHEMA or "public"
db = SessionLocal()
t = db.execute(text(f"SELECT * FROM {schema}.api_tokens WHERE id=26")).fetchone()
if t:
    print("token26:", {k: t._mapping[k] for k in t._mapping.keys()})
db.close()
