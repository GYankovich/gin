# -*- coding: utf-8 -*-
"""Generate as-built PDF for the GIN backtest module. Run: python docs/_gen_backtest_pdf.py"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

DOCS = Path(__file__).resolve().parent
OUT = DOCS / "backtest-module-as-built.pdf"
SHOTS = DOCS / "backtest-shots"
FONT = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

# Live UI captures: RobotPageChrome tabs + backtest page (robot #13, momentum).
UI_SHOTS: list[tuple[str, str]] = [
    (
        "01-fleet.png",
        "Вкладка «Флот» (/robots): список опросников и торговых роботов. "
        "Точка входа в сценарий — выбрать робота и открыть «Бэктест».",
    ),
    (
        "02-live.png",
        "Вкладка «Лайв» (/robots/:id/monitor): live/paper монитор той же ноды. "
        "Chrome: Флот · Лайв · Правка · Логи · Бэктест.",
    ),
    (
        "03-edit.png",
        "Вкладка «Правка» (/robots/edit/:id): мастер V4 (основное → стратегия → активы → риск). "
        "Конфиг отсюда уходит в backtest snapshot.",
    ),
    (
        "04-logs.png",
        "Вкладка «Логи» (/robots/:id/logs): audit stream (исполнения, заявки, циклы).",
    ),
    (
        "05-backtest.png",
        "Вкладка «Бэктест» (/robots/:id/backtest): пресеты периода, капитал, "
        "«Запустить бэктест», история прогонов (SUCCESS/FAILED, доходность, Max DD, сделки).",
    ),
    (
        "05-backtest-full.png",
        "Бэктест — полная страница (full page): toolbar + история целиком.",
    ),
]


class Doc(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Body", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"GIN | Backtest as-built | p. {self.page_no()}/{{nb}}", align="C")


def reset(pdf: Doc) -> None:
    pdf.set_x(pdf.l_margin)


def h2(pdf: Doc, text: str) -> None:
    reset(pdf)
    pdf.ln(3)
    pdf.set_font("Body", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 7, text)
    pdf.ln(1)


def h3(pdf: Doc, text: str) -> None:
    reset(pdf)
    pdf.ln(2)
    pdf.set_font("Body", "B", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6, text)


def body(pdf: Doc, text: str) -> None:
    reset(pdf)
    pdf.set_font("Body", size=9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5, text)
    pdf.ln(0.5)


def figure(pdf: Doc, path: Path, caption: str, max_h: float = 120) -> None:
    """Embed a screenshot with a Russian caption; skip quietly if missing."""
    if not path.is_file():
        note(pdf, f"[скриншот не найден: {path.name}]")
        return
    usable_w = pdf.epw
    try:
        from PIL import Image

        with Image.open(path) as im:
            iw, ih = im.size
    except Exception:
        # fpdf can still place the image; assume 16:10 if size unknown
        iw, ih = 1440, 900
    aspect = ih / max(iw, 1)
    draw_w = usable_w
    draw_h = draw_w * aspect
    if draw_h > max_h:
        draw_h = max_h
        draw_w = draw_h / aspect
    need = draw_h + 14
    if pdf.get_y() + need > pdf.page_break_trigger:
        pdf.add_page()
        reset(pdf)
    x = pdf.l_margin + (usable_w - draw_w) / 2
    pdf.image(str(path), x=x, w=draw_w, h=draw_h)
    pdf.ln(1)
    reset(pdf)
    pdf.set_font("Body", size=8)
    pdf.set_text_color(70, 70, 70)
    pdf.multi_cell(0, 4.5, f"Рис. {path.stem}: {caption}")
    pdf.ln(3)


def bullet(pdf: Doc, text: str) -> None:
    reset(pdf)
    pdf.set_font("Body", size=9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5, f"- {text}")


def note(pdf: Doc, text: str) -> None:
    reset(pdf)
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(200, 210, 220)
    pdf.set_font("Body", size=9)
    pdf.set_text_color(35, 45, 55)
    pdf.multi_cell(0, 5, text, border=1, fill=True)
    pdf.ln(2)


def table(pdf: Doc, headers: list[str], rows: list[list[str]], col_w: list[float]) -> None:
    reset(pdf)
    line_h = 5
    pdf.set_font("Body", "B", 8)
    pdf.set_fill_color(230, 234, 240)
    pdf.set_text_color(20, 20, 20)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], line_h + 1, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Body", size=8)
    for row in rows:
        measured: list[int] = []
        for i, cell in enumerate(row):
            lines = pdf.multi_cell(col_w[i], line_h, cell, dry_run=True, output="LINES")
            measured.append(max(1, len(lines)) * line_h)
        max_h = max(measured)
        if pdf.get_y() + max_h > pdf.page_break_trigger:
            pdf.add_page()
            reset(pdf)
            pdf.set_font("Body", "B", 8)
            pdf.set_fill_color(230, 234, 240)
            for i, h in enumerate(headers):
                pdf.cell(col_w[i], line_h + 1, h, border=1, fill=True)
            pdf.ln()
            pdf.set_font("Body", size=8)
        x0, y0 = pdf.l_margin, pdf.get_y()
        for i, cell in enumerate(row):
            pdf.set_xy(x0 + sum(col_w[:i]), y0)
            pdf.rect(x0 + sum(col_w[:i]), y0, col_w[i], max_h)
            pdf.multi_cell(col_w[i], line_h, cell)
        pdf.set_y(y0 + max_h)
    pdf.ln(2)


def main() -> None:
    pdf = Doc(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("Body", "", str(FONT))
    pdf.add_font("Body", "B", str(FONT_BOLD))
    pdf.add_page()
    pdf.set_margins(16, 16, 16)

    pdf.set_font("Body", "B", 18)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 9, "Бэктест GIN — as-built описание")
    pdf.set_font("Body", size=10)
    pdf.set_text_color(90, 90, 90)
    body(
        pdf,
        "Документ для анализа реализации и пользовательского сценария. "
        "Дата: 2026-10-02. Источник правды по продукту: robots_v2 (V2).",
    )
    note(
        pdf,
        "Вердикт: UI → /robots/:id/backtest → POST /api/v2/robots/backtest → "
        "job backtest_run → BacktestHost (RiskEngine / StrategyRuntime / paper cycle). "
        "Day-by-day universe + DMS historical filters + dividend calendar; "
        "crypto funding; child tables signals/orders/snapshots. "
        "Единственный engine — V2. Legacy history-backtest HTTP/job/engines вырезаны.",
    )

    h2(pdf, "1. Границы модуля")
    table(
        pdf,
        ["Слой", "Путь", "Роль"],
        [
            ["V2 façade", "robots_v2/backtest/*", "Enqueue, квоты, status, persist, worker"],
            ["Sim host", "…/backtest/host.py", "Bar replay через paper cycle"],
            ["Shared live core", "robots_v2/engine|risk|strategy", "Тот же цикл/риск/стратегия"],
            ["Shared helpers", "trading_core + session_backtest", "Live/smoke replay helpers (не prod UI)"],
            ["Prefetch", "trading_core/data/providers", "MOEX snapshots / Bybit candles"],
            ["Queue", "core/background_jobs", "lane=heavy, job_type=backtest_run"],
            ["UI prod", "RobotV2BacktestPage.tsx", "Единственный живой UX"],
            ["FE shared", "modules/robots/shared/*", "Пресеты, builders, hours (ex-/testing)"],
        ],
        [32, 55, 87],
    )

    h2(pdf, "2. Пользовательский сценарий (prod)")
    body(pdf, "Happy path:")
    bullet(pdf, "Вход: робот V2 → вкладка Backtest (/robots/:id/backtest). Загружается V4-конфиг, капитал из risk.capital, tokenId для crypto.")
    bullet(pdf, "Параметры: пресеты 7/30/90/180 дней или DateRangePicker; initial capital; scalper блокируется (нужны ticks).")
    bullet(pdf, "Запуск: POST /api/v2/robots/backtest → всегда 202 + run_id. UI poll GET …/runs/{id}/status ~1.5s.")
    bullet(pdf, "Прогресс: queued → loading_candles → simulating → done. Progress % по барам. Cancel → POST …/cancel.")
    bullet(pdf, "Результат: GET details → equity curve, trades, return %, max DD. История + compare двух run_id.")
    h3(pdf, "API surface")
    bullet(pdf, "POST /api/v2/robots/backtest → 202")
    bullet(pdf, "GET /backtest/runs · GET /backtest/runs/{id}/status · GET /backtest/runs/{id}")
    bullet(pdf, "POST /backtest/runs/{id}/cancel · POST /backtest/compare")
    h3(pdf, "Статусы")
    body(pdf, "QUEUED → RUNNING → SUCCESS | FAILED | CANCELLED. cancel_requested в БД; воркер опрашивает ~0.5s.")

    h2(pdf, "2.1 UI-скриншоты вкладок (prod)")
    body(
        pdf,
        "RobotPageChrome: Флот · Лайв · Правка · Логи · Бэктест. "
        "Снимки с живого UI 2026-09-28, робот #13 (бэктест / momentum / paper).",
    )
    for fname, caption in UI_SHOTS:
        figure(pdf, SHOTS / fname, caption, max_h=145)

    h2(pdf, "3. Поток исполнения (worker)")
    table(
        pdf,
        ["Шаг", "Что происходит"],
        [
            ["handle_backtest_run", "Читает backtest_runs + config_snapshot"],
            ["Universe by day", "build_universe_by_day: fixed once / screener|index daily + dividends"],
            ["DMS historical", "snapshot дня или PIT candles → _evaluate_pipeline_row"],
            ["Prefetch MOEX", "prefetch_candles_for_backtest → OsEngine (union тикеров)"],
            ["Prefetch crypto", "Bybit candles + funding history; нужен tokenId"],
            ["Load cache", "load_candles_by_symbol_from_cache → Candle[]"],
            ["BacktestHost.run_sync", "Bar timeline; active universe per day; funding"],
            ["Persist", "metrics_summary + backtest_metrics + signals/orders/snapshots"],
        ],
        [45, 129],
    )

    h2(pdf, "4. Модель симуляции (BacktestHost)")
    body(
        pdf,
        "host.py — unified bar-close replay (ADR-02). Компоненты: PaperLedger, "
        "RiskEngine(config.risk), ExecutionService(mode=paper), StrategyRuntime.",
    )
    h3(pdf, "На каждом баре")
    bullet(pdf, "Warmup до trade_from (история без торговли)")
    bullet(pdf, "Deferred fills на open текущего бара")
    bullet(pdf, "run_paper_cycle_sync — те же решения, что live paper")
    bullet(pdf, "Market intents → очередь на next open (no look-ahead)")
    bullet(pdf, "Day universe: universe_by_day; exitOnDrop закрывает выпавшие")
    bullet(pdf, "Crypto funding charges (historical) на bar")
    h3(pdf, "Выходы метрик")
    bullet(pdf, "initial / final equity, total_return %, max_drawdown %")
    bullet(pdf, "trades[], equity_curve[], orders[], history_stats")
    bullet(pdf, "Child tables: backtest_signals / orders / portfolio_snapshots")
    note(
        pdf,
        "Ограничения: Scalper запрещён. Shorts только perpetual/coin_futures. "
        "MOEX DMS на as_of: snapshot дня если есть, иначе PIT candles + allow_missing_spread.",
    )

    h2(pdf, "5. Входы / квоты")
    table(
        pdf,
        ["Поле", "Смысл"],
        [
            ["config", "TradingRobotConfigV4 JSON (strategy, risk, universe, …)"],
            ["from_date / to_date", "UTC; to > from"],
            ["initial_capital", "Опционально; иначе config.risk.capital"],
            ["robotId / tokenId", "Аудит / Bybit token"],
            ["asyncExecution", "Deprecated — всегда enqueue"],
            ["COMPUTE_MAX_SPAN_DAYS", "Лимит периода (default 366)"],
            ["COMPUTE_MAX_USER_RUNNING", "Параллельных RUNNING (default 1)"],
            ["COMPUTE_MAX_USER_QUEUED", "В очереди QUEUED (default 10)"],
        ],
        [55, 119],
    )

    h2(pdf, "6. Shared с live vs изоляция")
    table(
        pdf,
        ["Concern", "Live", "Backtest V2"],
        [
            ["Config", "V4 на robots_v2", "Тот же snapshot в request/БД"],
            ["Strategy", "StrategyRuntime plugins", "Те же; scalper blocked"],
            ["Risk", "RiskEngine", "Тот же"],
            ["Cycle", "async run_trading_cycle", "sync run_paper_cycle_sync"],
            ["Execution", "paper/live broker", "paper + deferred next-open"],
            ["Universe", "live resolve + dividend filter", "day-by-day + DMS historical + dividends"],
            ["Data", "stream / broker", "candles_cache / OsEngine / Bybit"],
            ["Funding", "live Bybit", "historical funding in BacktestHost"],
        ],
        [28, 58, 88],
    )

    h2(pdf, "7. Cut legacy → V2 only")
    table(
        pdf,
        ["Было", "Сейчас"],
        [
            ["HTTP history-backtest", "не смонтирован"],
            ["job history_backtest", "удалён; stale → unknown job"],
            ["trading/engines/* + data_provider/*", "удалены"],
            ["pages/testing UI", "только DEPRECATED.md; shared → modules/robots/shared"],
            ["Optimization", "backtest_service.start(priority=batch)"],
            ["Prod engine", "только BacktestHost + TradingRobotConfigV4"],
        ],
        [70, 104],
    )
    body(
        pdf,
        "Risk-adjusted: Sharpe в metrics_summary и backtest_metrics; Sortino/Calmar в payload JSON.",
    )

    h2(pdf, "8. Сценарии для проверки UX / реализации")
    for title, desc in [
        (
            "SC-1 P0 Запуск и результат",
            "Робот (momentum/reversion/grid) → 30d → Start → poll → SUCCESS → equity + trades. "
            "Config snapshot = конфиг робота на момент старта.",
        ),
        (
            "SC-2 P0 Отмена",
            "Длинный период → Cancel во время simulating → CANCELLED.",
        ),
        (
            "SC-3 P1 Квоты",
            "Второй Start при RUNNING → 429. Span > max → 400. Очередь > max → 429.",
        ),
        (
            "SC-4 P1 Compare + history",
            "Два успешных прогона → compare: metrics_diff + config_diff.",
        ),
        (
            "SC-5 P1 Crypto vs MOEX",
            "MOEX: OsEngine. Perpetual: tokenId + funding charges в metrics.",
        ),
        (
            "SC-6 P1 Day universe / dividends",
            "Screener daily: разные тикеры по дням. Ex-date исключает бумагу. exitOnDrop flatten.",
        ),
        (
            "SC-7 P2 Scalper / edge",
            "scalper → 422. Пустые свечи → ошибка/0 trades. Reload mid-run → status из БД.",
        ),
    ]:
        h3(pdf, title)
        body(pdf, desc)

    h2(pdf, "9. Остаточный backlog")
    table(
        pdf,
        ["#", "Пункт", "Статус"],
        [
            ["1", "Day-by-day universe + dividends", "DONE"],
            ["2", "Child tables signals/orders/snapshots", "DONE"],
            ["3", "Crypto funding in V2 host", "DONE"],
            ["4", "DMS historical filters (as_of screener)", "DONE"],
            ["5", "FE shared → modules/robots/shared", "DONE"],
            ["6", "Legacy HTTP/job history-backtest", "DONE (cut)"],
            ["7", "pages/testing UI", "DONE (только DEPRECATED.md)"],
            ["8", "Deprecated engines + data_provider", "DONE (удалены)"],
            ["9", "Sharpe/Sortino/Calmar в V2", "DONE (persist + backtest_metrics.sharpe_ratio)"],
        ],
        [10, 90, 74],
    )

    h2(pdf, "10. Ключевые файлы")
    bullet(pdf, "robots_v2/backtest/{service,host,persist,universe_schedule,funding,worker_handler}.py")
    bullet(pdf, "robots_v2/universe/{service,historical_dms,board_as_of}.py")
    bullet(pdf, "robots_v2/engine/{cycle_sync,session,paper_ledger}.py")
    bullet(pdf, "frontend/src/pages/robots-v2/RobotV2BacktestPage.tsx")
    bullet(pdf, "frontend/src/modules/robots/shared/*")
    bullet(pdf, "docs/ARCH-05 · BRD-ARCH-02")

    pdf.output(str(OUT))
    print(OUT)


if __name__ == "__main__":
    main()
