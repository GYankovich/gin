"""Full ER PNG of public schema (runtime), grouped by blocks for wall/A0 print."""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from sqlalchemy import text

from app.core.database import SessionLocal

OUT = Path(__file__).with_name("gin-db-full-er.png")
OUT_DOT = Path(__file__).with_name("gin-db-full-er.dot")
OUT_MIRRORS = Path(__file__).with_name("gin-db-mirrors-list.png")

BLOCK_RULES: list[tuple[str, set[str]]] = [
    (
        "1. Пользователь и права",
        {
            "user",
            "package",
            "package_feature",
            "user_email",
            "user_phone",
            "user_token",
            "email_confirmation",
            "outbound_message",
            "app_config",
            "dictionary",
        },
    ),
    (
        "2. API-ключи и роботы",
        {
            "api_tokens",
            "robots_v2",
            "robot_config_history",
            "robots_v2_sessions",
            "robots_v2_cycles",
            "robots_v2_signals",
            "robots_v2_decisions",
            "robots_v2_orders",
            "robots_v2_fills",
            "robots",
            "robot_configs",
            "robot_strategies",
            "robot_schedules",
            "robot_run_cycles",
            "robot_execution_logs",
            "robot_logs",
            "robot_session_logs",
            "robot_signals",
            "robot_decisions",
            "robot_trades",
            "robot_order_events",
            "robot_risk_events",
            "robot_backtest_runs",
            "backtest_runs",
            "backtest_comparisons",
            "market_backtests",
            "backtest_daily_universe",
            "backtest_universe_membership",
            "backtest_signals",
            "backtest_decisions",
            "backtest_orders",
            "backtest_trades",
            "backtest_positions",
            "backtest_portfolio_snapshots",
            "backtest_equity_curve",
            "backtest_metrics",
            "backtest_execution_events",
            "backtest_risk_events",
            "optimization_batches",
            "optimization_batch_items",
        },
    ),
    (
        "3. Счета и прогресс",
        {
            "portfolio_accounts",
            "token_portfolio_accounts",
            "portfolio_snapshots",
            "portfolio_positions",
            "portfolio_operations",
            "portfolio_orders",
            "account_orders",
            "portfolio_snapshot_daily",
        },
    ),
]

BLOCK_COLORS = {
    "1. Пользователь и права": ("#DCEBFF", "#1E4E8C"),
    "2. API-ключи и роботы": ("#DFF3E6", "#1F6B3A"),
    "3. Счета и прогресс": ("#FFE8CC", "#8A4B12"),
    "4. Рынок и Bybit": ("#EADFFl", "#5B3A8C"),
    "5. Служебные": ("#E8E8E8", "#333333"),
}
# fix typo
BLOCK_COLORS["4. Рынок и Bybit"] = ("#EADFFF", "#5B3A8C")

SENSE = {
    "user": "учётка / tenant",
    "package": "тариф",
    "package_feature": "вкладки тарифа",
    "user_email": "почта (status)",
    "user_phone": "телефон (status)",
    "user_token": "сессия входа JWT",
    "email_confirmation": "код / reset",
    "outbound_message": "очередь писем",
    "app_config": "key→value app",
    "dictionary": "справочник UI",
    "api_tokens": "ключ брокера (шифр)",
    "token_portfolio_accounts": "ключ ↔ счёт",
    "portfolio_accounts": "брокерский счёт",
    "portfolio_snapshots": "снимок equity",
    "portfolio_positions": "позиции снимка",
    "portfolio_operations": "операции",
    "portfolio_orders": "заявки UI",
    "account_orders": "журнал заявок",
    "portfolio_snapshot_daily": "дневной агрегат",
    "robots_v2": "робот live/paper",
    "robot_config_history": "версии конфига",
    "robots_v2_sessions": "сессия запуска",
    "robots_v2_cycles": "торговый цикл",
    "robots_v2_signals": "сигнал",
    "robots_v2_decisions": "решение risk",
    "robots_v2_orders": "ордер",
    "robots_v2_fills": "fill",
    "robots": "legacy робот v1",
    "robot_configs": "конфиг v1",
    "robot_strategies": "стратегия v1",
    "robot_schedules": "расписание v1",
    "robot_run_cycles": "цикл v1",
    "robot_execution_logs": "лог исполнения",
    "robot_logs": "логи робота",
    "robot_session_logs": "логи сессии",
    "robot_signals": "сигналы v1",
    "robot_decisions": "решения v1",
    "robot_trades": "сделки v1",
    "robot_order_events": "события ордера",
    "robot_risk_events": "risk events",
    "robot_backtest_runs": "бэктест v1",
    "backtest_runs": "прогон бэктеста",
    "backtest_comparisons": "сравнение прогонов",
    "market_backtests": "market backtest",
    "backtest_daily_universe": "universe дня",
    "backtest_universe_membership": "состав universe",
    "backtest_signals": "сигналы BT",
    "backtest_decisions": "решения BT",
    "backtest_orders": "ордера BT",
    "backtest_trades": "сделки BT",
    "backtest_positions": "позиции BT",
    "backtest_portfolio_snapshots": "снимки BT",
    "backtest_equity_curve": "equity curve",
    "backtest_metrics": "метрики",
    "backtest_execution_events": "exec events",
    "backtest_risk_events": "risk events BT",
    "optimization_batches": "батч оптимизации",
    "optimization_batch_items": "элемент батча",
    "candles_cache": "кэш свечей",
    "shared_market_candles": "общие свечи",
    "market_candles": "свечи market",
    "market_ticks": "тики",
    "market_depth_latest": "стакан",
    "candle_load_jobs": "загрузка свечей",
    "market_instruments": "инструменты",
    "instrument_cache": "кэш инструм.",
    "securities_static": "статика бумаг",
    "tqbr_securities": "TQBR",
    "market_snapshot": "снимок рынка",
    "market_snapshot_data": "строки снимка",
    "market_snapshot_history": "история снимков",
    "market_snapshot_data_history": "строки истории",
    "market_cache_leases": "лизи кэша",
    "daily_universe": "вселенная дня",
    "crypto_universe_daily": "crypto universe",
    "dms_subscriptions": "DMS подписки",
    "equity_dividend_events": "дивиденды",
    "moex_index_cache": "индексы MOEX",
    "bybit_funding_history": "funding",
    "bybit_lsr_history": "LSR",
    "bybit_open_interest_history": "open interest",
    "background_jobs": "фон. задачи",
    "background_worker_leases": "лизи воркеров",
    "cron_table": "cron",
    "external_api_logs": "логи внешних API",
    "osengine_ingest_heartbeat": "OSEngine heartbeat",
    "alembic_version": "версия миграций",
}


def is_mirror(name: str) -> bool:
    return name.startswith(("ganaly__", "backtest__"))


def classify(name: str) -> str:
    for title, names in BLOCK_RULES:
        if name in names:
            return title
    if name.startswith(
        (
            "bybit_",
            "candles_",
            "shared_market",
            "market_",
            "daily_universe",
            "crypto_universe",
            "dms_",
            "equity_",
            "moex_",
            "instrument_",
            "securities_",
            "tqbr_",
        )
    ):
        return "4. Рынок и Bybit"
    if name.startswith(("backtest", "robot", "robots", "optimization_")):
        return "2. API-ключи и роботы"
    if name.startswith("portfolio") or name.startswith("account_"):
        return "3. Счета и прогресс"
    return "5. Служебные"


def load_schema():
    db = SessionLocal()
    try:
        tables = list(
            db.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                    ORDER BY 1
                    """
                )
            ).scalars()
        )
        views = list(
            db.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'v'
                    ORDER BY 1
                    """
                )
            ).scalars()
        )
        fks = [
            dict(r)
            for r in db.execute(
                text(
                    """
                    SELECT
                      src.relname AS src,
                      tgt.relname AS tgt,
                      string_agg(a.attname || '→' || af.attname, ', ' ORDER BY ck.ord) AS cols
                    FROM pg_constraint con
                    JOIN pg_class src ON src.oid = con.conrelid
                    JOIN pg_class tgt ON tgt.oid = con.confrelid
                    JOIN pg_namespace ns ON ns.oid = src.relnamespace
                    JOIN unnest(con.conkey) WITH ORDINALITY AS ck(attnum, ord) ON true
                    JOIN unnest(con.confkey) WITH ORDINALITY AS cf(attnum, ord) ON cf.ord = ck.ord
                    JOIN pg_attribute a ON a.attrelid = src.oid AND a.attnum = ck.attnum
                    JOIN pg_attribute af ON af.attrelid = tgt.oid AND af.attnum = cf.attnum
                    WHERE con.contype = 'f' AND ns.nspname = 'public'
                    GROUP BY src.relname, tgt.relname
                    ORDER BY 1, 2
                    """
                )
            ).mappings()
        ]
        return tables, views, fks
    finally:
        db.close()


def label(name: str) -> str:
    sense = SENSE.get(name, "")
    return f"{name}\n{sense}" if sense else name


def write_dot(runtime: list[str], fks: list[dict], by_block: dict[str, list[str]]) -> None:
    lines = [
        "digraph GIN {",
        '  graph [rankdir=LR, fontname="Segoe UI", fontsize=12, bgcolor="#F7F5F1", pad=0.4, nodesep=0.25, ranksep=0.55];',
        '  node [shape=box, style="rounded,filled", fontname="Segoe UI", fontsize=9, margin="0.12,0.08"];',
        '  edge [color="#777777", arrowsize=0.6, penwidth=0.8, fontname="Segoe UI", fontsize=7];',
    ]
    color_fill = {
        "1. Пользователь и права": "#DCEBFF",
        "2. API-ключи и роботы": "#DFF3E6",
        "3. Счета и прогресс": "#FFE8CC",
        "4. Рынок и Bybit": "#EADFFF",
        "5. Служебные": "#E8E8E8",
    }
    for title, names in by_block.items():
        safe = title.replace('"', "'")
        lines.append(f'  subgraph "cluster_{safe}" {{')
        lines.append(f'    label="{safe}";')
        lines.append(f'    color="{BLOCK_COLORS[title][1]}";')
        lines.append("    style=rounded;")
        fill = color_fill[title]
        for n in names:
            sense = SENSE.get(n, "").replace('"', "'")
            lab = f"{n}\\n{sense}" if sense else n
            lines.append(f'    "{n}" [label="{lab}", fillcolor="{fill}"];')
        lines.append("  }")
    runtime_set = set(runtime)
    for fk in fks:
        if fk["src"] in runtime_set and fk["tgt"] in runtime_set:
            cols = (fk["cols"] or "").replace('"', "'")
            lines.append(f'  "{fk["src"]}" -> "{fk["tgt"]}" [label="{cols}"];')
    lines.append("}")
    OUT_DOT.write_text("\n".join(lines), encoding="utf-8")


def render_mirrors(mirrors: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(16, 10), dpi=140)
    ax.axis("off")
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.text(5, 9.6, "Зеркала облака (не runtime) — приложение не читает", ha="center", fontsize=16, fontweight="bold")
    ax.text(
        5,
        9.15,
        "Копии после переноса ganaly/backtest → local. Для отката/сверки, не для связей runtime ER.",
        ha="center",
        fontsize=10,
        color="#555",
    )
    cols = 3
    for i, name in enumerate(sorted(mirrors)):
        c, r = i % cols, i // cols
        x = 0.4 + c * 3.2
        y = 8.6 - r * 0.32
        ax.text(x, y, "• " + name, fontsize=8, family="DejaVu Sans", color="#444")
    fig.savefig(OUT_MIRRORS, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    tables, views, fks = load_schema()
    mirrors = [t for t in tables if is_mirror(t)]
    runtime = [t for t in tables if not is_mirror(t)] + [v for v in views if not is_mirror(v)]
    runtime = sorted(set(runtime))

    by_block: dict[str, list[str]] = defaultdict(list)
    for t in runtime:
        by_block[classify(t)].append(t)
    for k in by_block:
        by_block[k].sort()

    write_dot(runtime, fks, by_block)
    render_mirrors(mirrors)

    # Large print canvas (~A0 landscape at 120 dpi)
    fig_w, fig_h = 46, 30
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=120)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor("#F7F5F1")
    ax.set_facecolor("#F7F5F1")

    ax.text(
        50,
        98.5,
        "GIN — полная ER public (runtime). Стрелка: дочерняя → родитель (FK). Подпись — смысл таблицы.",
        ha="center",
        va="top",
        fontsize=20,
        fontweight="bold",
    )
    ax.text(
        50,
        96.6,
        f"Таблиц runtime: {len(runtime)} · зеркал отдельно: {len(mirrors)} · FK: {len(fks)} · файл DOT рядом для Graphviz",
        ha="center",
        va="top",
        fontsize=12,
        color="#555",
    )

    # Regions tuned for readability
    regions = {
        "1. Пользователь и права": (1.0, 58.0, 28.0, 36.0),
        "3. Счета и прогресс": (31.0, 58.0, 28.0, 36.0),
        "5. Служебные": (61.0, 78.0, 37.5, 16.0),
        "2. API-ключи и роботы": (1.0, 2.0, 58.0, 53.0),
        "4. Рынок и Bybit": (61.0, 2.0, 37.5, 73.0),
    }

    positions: dict[str, tuple[float, float, float, float, str]] = {}

    for title, (x, y, w, h) in regions.items():
        names = by_block.get(title, [])
        bg, accent = BLOCK_COLORS[title]
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.2,rounding_size=0.7",
                linewidth=2.5,
                edgecolor=accent,
                facecolor=bg,
                alpha=0.95,
                zorder=0,
            )
        )
        ax.text(x + 0.7, y + h - 1.4, title, fontsize=15, fontweight="bold", color=accent, zorder=2)

        if not names:
            continue

        # Prefer taller packing for market / robots
        if title.startswith("2"):
            cols = 5
            box_w, box_h = 10.6, 2.7
            font_size = 7.2
        elif title.startswith("4"):
            cols = 3
            box_w, box_h = 11.4, 2.55
            font_size = 7.0
        elif title.startswith("5"):
            cols = 4
            box_w, box_h = 8.6, 2.3
            font_size = 6.8
        else:
            cols = 3
            box_w, box_h = 8.5, 3.0
            font_size = 7.5

        inner_x0 = x + 0.9
        inner_y0 = y + h - 4.0
        gap_x, gap_y = 0.55, 0.35
        for i, name in enumerate(names):
            c = i % cols
            r = i // cols
            cx = inner_x0 + c * (box_w + gap_x) + box_w / 2
            cy = inner_y0 - r * (box_h + gap_y) - box_h / 2
            positions[name] = (cx, cy, box_w, box_h, accent, font_size)

    runtime_set = set(runtime)
    for fk in fks:
        src, tgt = fk["src"], fk["tgt"]
        if src not in positions or tgt not in positions:
            continue
        if is_mirror(src) or is_mirror(tgt):
            continue
        x1, y1, *_ = positions[src]
        x2, y2, *_ = positions[tgt]
        same = classify(src) == classify(tgt)
        ax.add_patch(
            FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                arrowstyle="-|>",
                mutation_scale=9,
                lw=0.9 if same else 1.15,
                color="#5A5A5A" if same else "#2F2F2F",
                alpha=0.35 if same else 0.55,
                connectionstyle="arc3,rad=0.06",
                zorder=1,
            )
        )

    for name, (cx, cy, lw, lh, accent, font_size) in positions.items():
        ax.add_patch(
            FancyBboxPatch(
                (cx - lw / 2, cy - lh / 2),
                lw,
                lh,
                boxstyle="round,pad=0.03,rounding_size=0.18",
                linewidth=1.2,
                edgecolor=accent,
                facecolor="white",
                zorder=3,
            )
        )
        ax.text(
            cx,
            cy,
            label(name),
            ha="center",
            va="center",
            fontsize=font_size,
            color="#111",
            zorder=4,
            family="DejaVu Sans",
            linespacing=1.15,
        )

    ax.text(
        1.0,
        0.6,
        "Зеркала ganaly__* / backtest__* — на отдельном листе gin-db-mirrors-list.png. "
        "Интерактив: gin-db-full-er.dot → Graphviz / https://dreampuf.github.io/GraphvizOnline",
        fontsize=10,
        color="#444",
    )

    fig.tight_layout(pad=0.3)
    fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {OUT}")
    print(f"wrote {OUT_DOT}")
    print(f"wrote {OUT_MIRRORS}")
    print(f"runtime={len(runtime)} mirrors={len(mirrors)} fks={sum(1 for f in fks if f['src'] in runtime_set and f['tgt'] in runtime_set)}")


if __name__ == "__main__":
    main()
