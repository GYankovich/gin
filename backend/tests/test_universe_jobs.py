"""Тесты расписания universe job'ов П1/П2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.robots.config.migration import migrate_legacy_to_v2
from app.modules.robots.universe_jobs import (
    should_run_historical_screening,
    should_run_paper_selection,
)


def _v2_config(**overrides):
    base = migrate_legacy_to_v2({
        "universe_mode": "dms_pipeline",
        "universe_refresh_minutes": 30,
        "pipeline": {"mode": "ALL", "filters": [{"type": "atr", "min_percent": 1.5}]},
    })
    base.update(overrides)
    return base


def test_paper_selection_every_minutes():
    cfg = _v2_config()
    cfg["paper_selection"]["refresh"]["every_minutes"] = 15
    cfg["paper_selection"]["refresh"]["only_trading_hours"] = False
    now = datetime(2024, 6, 3, 12, 0, tzinfo=timezone.utc)
    assert should_run_paper_selection(cfg, last_run_at=None, now=now)
    last = now - timedelta(minutes=10)
    assert not should_run_paper_selection(cfg, last_run_at=last, now=now)
    last = now - timedelta(minutes=20)
    assert should_run_paper_selection(cfg, last_run_at=last, now=now)


def test_historical_disabled():
    cfg = _v2_config()
    cfg["historical_screening"]["enabled"] = False
    assert not should_run_historical_screening(cfg)


def test_historical_daily_msk_window():
    cfg = _v2_config()
    cfg["historical_screening"]["refresh"] = {
        "every_minutes": 0,
        "daily_at_msk": "07:00",
        "only_trading_hours": False,
    }
    # 04:00 UTC ≈ 07:00 MSK (летом) — ещё не время
    early = datetime(2024, 6, 3, 3, 0, tzinfo=timezone.utc)
    assert not should_run_historical_screening(cfg, last_run_at=None, now=early)
    # 05:00 UTC ≈ 08:00 MSK — после 07:00, первый запуск за день
    late = datetime(2024, 6, 3, 5, 0, tzinfo=timezone.utc)
    assert should_run_historical_screening(cfg, last_run_at=None, now=late)
