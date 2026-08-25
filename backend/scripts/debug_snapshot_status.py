from sqlalchemy import text
from app.core.database import SessionLocal
from app.modules.robots.universe import universe_min_tradable_row

db = SessionLocal()
snap = db.execute(
    text(
        """
        SELECT id FROM market_snapshot
        WHERE board='TQBR' AND status='SUCCESS'
        ORDER BY snapshot_time DESC LIMIT 1
        """
    ),
).fetchone()
print("snapshot", snap[0] if snap else None)
rows = db.execute(
    text(
        """
        SELECT ticker, security_status, trading_status, last_price, value_today
        FROM market_snapshot_data
        WHERE snapshot_id=:sid
        LIMIT 20
        """
    ),
    {"sid": snap[0]},
).fetchall()
print("sample rows:")
for r in rows[:10]:
    ok = universe_min_tradable_row({"ticker": r.ticker, "security_status": r.security_status, "trading_status": r.trading_status})
    print(r.ticker, r.security_status, r.trading_status, ok)
all_rows = db.execute(
    text("SELECT ticker, security_status, trading_status FROM market_snapshot_data WHERE snapshot_id=:sid"),
    {"sid": snap[0]},
).fetchall()
tradable = sum(1 for r in all_rows if universe_min_tradable_row({"ticker": r.ticker, "security_status": r.security_status, "trading_status": r.trading_status}))
print("tradable", tradable, "of", len(all_rows))
statuses = {}
for r in all_rows:
    key = (r.security_status, r.trading_status)
    statuses[key] = statuses.get(key, 0) + 1
print("status combos top:", sorted(statuses.items(), key=lambda x: -x[1])[:10])
db.close()
