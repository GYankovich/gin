from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app.modules.robots.trading.backtest.backtest_narrative_log as narrative
from app.modules.robots.trading.data.stats import CandlePrefetchStats


def test_narrative_step_sub_result(monkeypatch):
    messages: list[str] = []

    def _capture(msg, *args, **kwargs):
        messages.append(msg % args if args else msg)

    monkeypatch.setattr(narrative, "log_backtest_run_info", _capture)

    with narrative.backtest_narrative(run_id=1):
        narrative.narrative_step("Скоринг торгуемых монет на 25.06.2026")
        narrative.narrative_sub("Запрос к ByBit: GET /v5/market/instruments-info")
        narrative.narrative_sub("Ответ ByBit: 595 инструментов")
        narrative.narrative_result("На 25.06.2026 торгуются монеты: BTCUSDT, ETHUSDT")

    assert messages[0] == "Шаг 1: Скоринг торгуемых монет на 25.06.2026"
    assert messages[1] == "  1.1. Запрос к ByBit: GET /v5/market/instruments-info"
    assert messages[2] == "  1.2. Ответ ByBit: 595 инструментов"
    assert messages[3] == "  Результат: На 25.06.2026 торгуются монеты: BTCUSDT, ETHUSDT"


def test_format_symbol_list_truncates():
    symbols = [f"SYM{i}USDT" for i in range(30)]
    text = narrative.format_symbol_list(symbols, limit=5)
    assert "SYM0USDT" in text
    assert "всего 30" in text


def test_format_candle_prefetch_result():
    stats = CandlePrefetchStats(
        total_tickers=10,
        cache_full_hits=8,
        fetched_tickers=2,
        fetched_candles=500,
        interval_label="M5",
    )
    text = narrative.format_candle_prefetch_result(stats)
    assert "M5" in text
    assert "догружено тикеров 2" in text


def test_format_trade_date():
    assert narrative.format_trade_date(date(2026, 6, 25)) == "25.06.2026"
