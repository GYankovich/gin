from sqlalchemy import text
import json
from app.core.database import SessionLocal
from app.core.config import settings

schema = settings.DB_SCHEMA or "public"
db = SessionLocal()
r = db.execute(
    text(f"SELECT id, name, status, token_id, config, metadata FROM {schema}.robots_v2 WHERE id=3"),
).fetchone()
print("robot:", r.id, r.name, "status", r.status, "token", r.token_id)
cfg = r.config or {}
print("mode:", (cfg.get("core") or {}).get("mode"))
print("universe:", json.dumps(cfg.get("universe"), ensure_ascii=False))
print("schedule:", json.dumps((cfg.get("core") or {}).get("schedule"), ensure_ascii=False))
print("metadata:", json.dumps(r.metadata or {}, ensure_ascii=False, default=str))
if r.token_id:
    t = db.execute(
        text(f"SELECT id, label, account_id, is_sandbox FROM {schema}.api_tokens WHERE id=:id"),
        {"id": r.token_id},
    ).fetchone()
    if t:
        print("token:", dict(t._mapping))
dec = db.execute(
    text(
        f"""
        SELECT created_at, stage, code, message
        FROM {schema}.robots_v2_decisions
        WHERE robot_id=3 ORDER BY created_at DESC LIMIT 15
        """
    ),
).fetchall()
print("decisions:", len(dec))
for d in dec:
    print(" ", d.created_at, d.stage, d.code, (d.message or "")[:120])
sess = db.execute(
    text(
        f"""
        SELECT id, started_at, ended_at, stop_reason, account_id
        FROM {schema}.robots_v2_sessions WHERE robot_id=3 ORDER BY started_at DESC LIMIT 5
        """
    ),
).fetchall()
print("sessions:", len(sess))
for s in sess:
    print(" ", s.id, s.started_at, s.ended_at, s.stop_reason, s.account_id)
db.close()
