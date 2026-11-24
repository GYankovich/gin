"""Build a Mermaid flowchart TB ER from live public FKs (runtime only)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal

OUT = Path(__file__).with_name("gin-db-er-flowchart.md")

BLOCKS: list[tuple[str, str, set[str]]] = [
    (
        "U",
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
        "K",
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
        "A",
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

MARKET_PREFIXES = (
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

SENSE = {
    "user": "учётка / tenant",
    "package": "тариф",
    "package_feature": "вкладки",
    "user_email": "почта status",
    "user_phone": "телефон status",
    "user_token": "сессия JWT",
    "email_confirmation": "код / reset",
    "outbound_message": "очередь писем",
    "app_config": "настройки",
    "dictionary": "справочник UI",
    "api_tokens": "ключ + secret шифр",
    "robots_v2": "live/paper",
    "robot_config_history": "версии конфига",
    "robots_v2_sessions": "сессия",
    "robots_v2_cycles": "цикл",
    "robots_v2_signals": "сигнал",
    "robots_v2_decisions": "решение",
    "robots_v2_orders": "ордер",
    "robots_v2_fills": "fill",
    "portfolio_accounts": "брокерский счёт",
    "token_portfolio_accounts": "ключ↔счёт",
    "portfolio_snapshots": "снимок",
    "portfolio_positions": "позиции",
    "portfolio_operations": "операции",
    "portfolio_orders": "заявки UI",
    "account_orders": "журнал заявок",
    "portfolio_snapshot_daily": "дневной агрегат",
    "backtest_runs": "прогон",
    "candles_cache": "кэш свечей",
    "shared_market_candles": "общие свечи",
    "daily_universe": "вселенная дня",
    "crypto_universe_daily": "crypto universe",
    "background_jobs": "фон. задачи",
    "cron_table": "cron",
    "external_api_logs": "логи API",
    "alembic_version": "миграции",
}


def is_mirror(name: str) -> bool:
    return name.startswith(("ganaly__", "backtest__"))


def classify(name: str) -> str:
    for sid, _title, names in BLOCKS:
        if name in names:
            return sid
    if any(name.startswith(p) for p in MARKET_PREFIXES):
        return "M"
    if name.startswith(("backtest", "robot", "robots", "optimization_", "api_")):
        return "K"
    if name.startswith(("portfolio", "account_")):
        return "A"
    return "S"


def node_id(name: str) -> str:
    return "N_" + name.replace("-", "_")


def node_label(name: str) -> str:
    sense = SENSE.get(name)
    if sense:
        return f"{name}<br/>{sense}"
    return name


def load():
    db = SessionLocal()
    try:
        tables = list(
            db.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r','v')
                    ORDER BY 1
                    """
                )
            ).scalars()
        )
        fks = [
            (r["src"], r["tgt"], r["cols"])
            for r in db.execute(
                text(
                    """
                    SELECT
                      src.relname AS src,
                      tgt.relname AS tgt,
                      string_agg(a.attname, ',' ORDER BY ck.ord) AS cols
                    FROM pg_constraint con
                    JOIN pg_class src ON src.oid = con.conrelid
                    JOIN pg_class tgt ON tgt.oid = con.confrelid
                    JOIN pg_namespace ns ON ns.oid = src.relnamespace
                    JOIN unnest(con.conkey) WITH ORDINALITY AS ck(attnum, ord) ON true
                    JOIN unnest(con.confkey) WITH ORDINALITY AS cf(attnum, ord) ON cf.ord = ck.ord
                    JOIN pg_attribute a ON a.attrelid = src.oid AND a.attnum = ck.attnum
                    WHERE con.contype = 'f' AND ns.nspname = 'public'
                    GROUP BY src.relname, tgt.relname
                    ORDER BY 1,2
                    """
                )
            ).mappings()
        ]
        return tables, fks
    finally:
        db.close()


def main() -> None:
    tables, fks = load()
    runtime = [t for t in tables if not is_mirror(t)]
    mirrors = [t for t in tables if is_mirror(t)]

    by: dict[str, list[str]] = defaultdict(list)
    for t in runtime:
        by[classify(t)].append(t)
    for k in by:
        by[k].sort()

    titles = {
        "U": "1. Пользователь и права",
        "K": "2. API-ключи и роботы",
        "A": "3. Счета и прогресс",
        "M": "4. Рынок и Bybit",
        "S": "5. Служебные",
        "Z": "6. Зеркала — не runtime",
    }

    lines: list[str] = []
    lines.append("# GIN — ER flowchart (стиль subgraph)")
    lines.append("")
    lines.append(
        f"Runtime: **{len(runtime)}** таблиц/view · FK: **{len([1 for s,t,_ in fks if s in runtime and t in runtime])}** · "
        f"зеркала: **{len(mirrors)}** (внизу списком)."
    )
    lines.append("")
    lines.append(
        "Стрелка: владелец → зависимое (как в вашем примере). "
        "В БД FK обратный. Пунктир — смысл без FK."
    )
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TB")

    # subgraphs
    for sid in ("U", "K", "A", "M", "S"):
        names = by.get(sid, [])
        if not names:
            continue
        lines.append(f'  subgraph {sid}["{titles[sid]}"]')
        lines.append("    direction TB")
        for name in names:
            nid = node_id(name)
            lab = node_label(name).replace('"', "#quot;")
            lines.append(f'    {nid}["{lab}"]')
        # intra-block: parent → child (invert FK)
        for src, tgt, cols in fks:
            if src in names and tgt in names:
                lines.append(f"    {node_id(tgt)} --> {node_id(src)}")
        lines.append("  end")
        lines.append("")

    # mirrors as one node list
    lines.append(f'  subgraph Z["{titles["Z"]}"]')
    lines.append("    direction TB")
    # chunk mirrors into a few summary nodes + note
    lines.append('    MIR_NOTE["копии после переноса облака<br/>приложение не читает"]')
    for i in range(0, len(mirrors), 8):
        chunk = mirrors[i : i + 8]
        lab = "<br/>".join(chunk)
        lines.append(f'    MIR_{i}["{lab}"]')
        lines.append(f"    MIR_NOTE -.-> MIR_{i}")
    lines.append("  end")
    lines.append("")

    # cross-block FK
    lines.append("  %% cross-block FK")
    seen = set()
    for src, tgt, cols in fks:
        if is_mirror(src) or is_mirror(tgt):
            continue
        if src not in runtime or tgt not in runtime:
            continue
        if classify(src) == classify(tgt):
            continue
        key = (src, tgt)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {node_id(tgt)} --> {node_id(src)}")

    # semantic dashed links that help the story
    lines.append("  %% semantic")
    if "email_confirmation" in runtime and "user" in runtime:
        lines.append(f'  {node_id("email_confirmation")} -.->|"до появления user"| {node_id("user")}')
    if "portfolio_snapshot_daily" in runtime and "portfolio_snapshots" in runtime:
        lines.append(f"  {node_id('portfolio_snapshots')} -.-> {node_id('portfolio_snapshot_daily')}")
    # market fuels robots / backtest (no FK)
    if "candles_cache" in runtime and "robots_v2" in runtime:
        lines.append(f"  {node_id('candles_cache')} -.-> {node_id('robots_v2')}")
    if "candles_cache" in runtime and "backtest_runs" in runtime:
        lines.append(f"  {node_id('candles_cache')} -.-> {node_id('backtest_runs')}")
    if "background_jobs" in runtime and "backtest_runs" in runtime:
        lines.append(f"  {node_id('background_jobs')} -.-> {node_id('backtest_runs')}")

    # block-level orientation edges (subtle via hubs)
    lines.append("  %% block flow")
    lines.append("  U --> K")
    lines.append("  U --> A")
    lines.append("  K --> A")
    lines.append("  M --> K")
    lines.append("  S --> K")

    lines.append("```")
    lines.append("")
    lines.append("## Как смотреть")
    lines.append("")
    lines.append("- В Obsidian: Reading Mode.")
    lines.append("- Или вставьте блок в https://mermaid.live")
    lines.append("- Зеркала намеренно отдельно: это не граф runtime.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} nodes={len(runtime)} cross_fk={len(seen)}")


if __name__ == "__main__":
    main()
