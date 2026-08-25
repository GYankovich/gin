"""Bootstrap stage progress mapping."""

from app.modules.robots_v2.engine.types import cycle_stage_progress


def test_bootstrap_atr_warmup_progress_scales_with_ticker_count():
    assert cycle_stage_progress("bootstrap", "atr_warmup 0/100") == 0.08
    mid = cycle_stage_progress("bootstrap", "atr_warmup 50/100")
    assert 0.14 < mid < 0.16
    assert cycle_stage_progress("bootstrap", "atr_warmup 100/100") == 0.22
