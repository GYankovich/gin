# Agent status — trading_core (while away)

Updated: 2026-09-29 (later)

## Done without you

1. **Waves 1–5** of `trading_core` (see `docs/ARCH-06-trading-core.md` v0.3):
   - contracts / intervals / costs
   - risk + symbols
   - brokers + position sync + account_health
   - market data + OsEngine prefetch helper
   - sim (BrokerEmulator, metrics, types) + run logging
   - cancel helpers also in `trading_core.cancel`
2. Shims on old `robots.trading.*` / `robots_v2.backtest.cancel`.
3. `robots_v2` retargeted to `trading_core`.
4. Fixed rebind_capital test (budget cap).

## Known debt (leave for review with you)

- Soft imports from bybit provider → `robots.backtest_progress`, crypto_universe, pipeline.
- Universe mega-move not started.
- Live session / grain_seed orchestration stays in robots.

## Verify when back

```bash
cd backend
python -c "from app.modules.trading_core import Candle, RiskManager; print('ok')"
python -m pytest tests/test_intervals.py tests/test_trading_costs_ceil.py tests/test_robots_v2_engine.py tests/test_robots_v2_execution.py tests/test_account_health_gates.py tests/test_market_data_facade.py tests/test_db_cache_bulk.py tests/test_robots_v2_backtest_queue.py tests/test_osengine_facade.py tests/test_backtest_run_file_logger.py -q
```
