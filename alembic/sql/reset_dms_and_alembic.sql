-- Reset DMS-related objects and Alembic version to rerun from 0026.
-- Run manually in PostgreSQL as a privileged user.

BEGIN;

-- Drop DMS objects in dependency-safe order.
DROP TABLE IF EXISTS ganaly.daily_universe CASCADE;
DROP TABLE IF EXISTS ganaly.candles_cache CASCADE;
DROP TABLE IF EXISTS ganaly.market_snapshot_data_history CASCADE;
DROP TABLE IF EXISTS ganaly.market_snapshot_history CASCADE;
DROP TABLE IF EXISTS ganaly.market_snapshot_data CASCADE;
DROP TABLE IF EXISTS ganaly.dms_subscriptions CASCADE;
DROP TABLE IF EXISTS ganaly.market_snapshot CASCADE;
DROP TABLE IF EXISTS ganaly.securities_static CASCADE;

-- Optional cleanup for generated sequences left by dropped BIGSERIAL IDs.
DROP SEQUENCE IF EXISTS ganaly.daily_universe_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.candles_cache_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.market_snapshot_data_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.market_snapshot_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.market_snapshot_data_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.dms_subscriptions_id_seq CASCADE;
DROP SEQUENCE IF EXISTS ganaly.market_snapshot_id_seq CASCADE;

-- Reset alembic head to just before DMS chain.
-- If table has a single row (most common), this is enough:
UPDATE ganaly.alembic_version
SET version_num = '0025_robot_runtime_decisions';

COMMIT;

-- Then run:
-- alembic upgrade head
