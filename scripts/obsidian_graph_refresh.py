"""
Строит «полноценный» граф для vault'а Obsidian (папка scanner-output):

- Генерирует иерархию MOC в scanner-output/Graph/ (Index → корень → EPIC → ITEM).
- В каждую TOPIC-заметку добавляет YAML + секцию «Связи графа» с wikilinks
  (родители, индекс, соседи по ITEM).
- Идемпотентно: повторный запуск перезаписывает только свой блок (маркеры gin_graph).

Запуск из корня репозитория:

  python scripts/obsidian_graph_refresh.py
  python scripts/obsidian_graph_refresh.py --vault path/to/scanner-output
  python scripts/obsidian_graph_refresh.py --watch
  python scripts/obsidian_graph_refresh.py --watch --interval 30

Обычный конвейер после сканера Source Scanner:

  powershell -File scripts/run_obsidian_scan_and_graph.ps1
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT / "scanner-output"
GRAPH_DIR_NAME = "Graph"
GRAPH_VERSION = 1

MARKER_START = "---\ngin_graph:\n"
MARKER_ANCHOR = "<!-- gin_graph:end -->"


@dataclass(frozen=True)
class Topic:
    """Одна заметка TOPIC (лист дерева)."""

    path: Path  # absolute
    root: str
    epic: str
    item: str
    title: str  # stem


def _vault_posix(vault: Path, path: Path) -> str:
    rel = path.relative_to(vault).as_posix()
    # Obsidian wikilinks: используем прямой слеш
    base, _ext = rel.rsplit(".", 1) if "." in rel else (rel, "")
    return base


def _wikilink(vault: Path, target: Path, label: str | None = None) -> str:
    inner = _vault_posix(vault, target)
    if label and label != inner.split("/")[-1]:
        return f"[[{inner}|{label}]]"
    return f"[[{inner}]]"


def _moc_root_name(root: str) -> str:
    return f"MOC Root — {root}"


def _moc_epic_name(root: str, epic_folder: str) -> str:
    return f"MOC EPIC — {root} — {epic_folder}"


def _moc_item_name(root: str, epic_folder: str, item_folder: str) -> str:
    return f"MOC ITEM — {root} — {epic_folder} — {item_folder}"


def _graph_path(vault: Path, stem: str) -> Path:
    return vault / GRAPH_DIR_NAME / f"{stem}.md"


def _strip_old_block(text: str) -> str:
    if MARKER_START not in text:
        return text.lstrip("\n")
    start = text.index(MARKER_START)
    if MARKER_ANCHOR not in text:
        return text.lstrip("\n")
    end = text.index(MARKER_ANCHOR) + len(MARKER_ANCHOR)
    # удаляем блок и один следующий перевод строки
    rest = text[end:].lstrip("\n")
    return rest


def _build_topic_block(
    vault: Path,
    topic: Topic,
    moc_index: Path,
    moc_root: Path,
    moc_epic: Path,
    moc_item: Path,
) -> str:
    tag_root = topic.root.replace("/", "-")
    tag_epic = re.sub(r"[^\w\-]+", "-", topic.epic, flags=re.UNICODE).strip("-").lower()
    tag_item = re.sub(r"[^\w\-]+", "-", topic.item, flags=re.UNICODE).strip("-").lower()
    lines = [
        "---",
        "gin_graph:",
        f"  version: {GRAPH_VERSION}",
        f'  root: "{topic.root}"',
        f'  epic: "{topic.epic}"',
        f'  item: "{topic.item}"',
        "tags:",
        "  - gin-graph",
        "  - gin-scanner",
        f"  - gin-root/{tag_root}",
        f"  - gin-epic/{tag_epic}",
        f"  - gin-item/{tag_item}",
        "---",
        "",
        "## Связи графа",
        "",
        f"> Авто: `scripts/obsidian_graph_refresh.py` · обновление: [[Graph/Index|полный индекс MOC]]",
        "",
        "- Вверх по дереву:",
        f"  - ITEM: {_wikilink(vault, moc_item, moc_item.stem)}",
        f"  - EPIC: {_wikilink(vault, moc_epic, moc_epic.stem)}",
        f"  - Корень: {_wikilink(vault, moc_root, moc_root.stem)}",
        f"  - Индекс: {_wikilink(vault, moc_index, 'Graph / Index')}",
        "",
        f"Остальные заметки этого ITEM перечислены в {_wikilink(vault, moc_item, moc_item.stem)} (избегаем сотен дублей ссылок в каждом файле).",
        "",
    ]
    lines.append(MARKER_ANCHOR)
    lines.append("")
    return "\n".join(lines)


def _write_note(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


def collect_topics(vault: Path) -> list[Topic]:
    topics: list[Topic] = []
    graph_dir = vault / GRAPH_DIR_NAME
    for p in sorted(vault.rglob("*.md")):
        if graph_dir in p.parents or p.parent == graph_dir:
            continue
        rel = p.relative_to(vault)
        parts = rel.parts
        if len(parts) != 4:
            # ожидаем: root / EPIC … / ITEM … / TOPIC ….md
            continue
        root, epic, item, fname = parts
        if not fname.startswith("TOPIC ") or not fname.endswith(".md"):
            continue
        topics.append(
            Topic(
                path=p.resolve(),
                root=root,
                epic=epic,
                item=item,
                title=p.stem,
            )
        )
    return topics


def rebuild_graph(vault: Path) -> tuple[int, int]:
    vault = vault.resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault не найден: {vault}")

    topics = collect_topics(vault)
    graph_dir = vault / GRAPH_DIR_NAME
    graph_dir.mkdir(parents=True, exist_ok=True)
    for stale in graph_dir.glob("*.md"):
        try:
            stale.unlink()
        except OSError:
            pass

    by_root: dict[str, dict[str, dict[str, list[Topic]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for t in topics:
        by_root[t.root][t.epic][t.item].append(t)

    # --- Index ---
    index_path = _graph_path(vault, "Index")
    index_lines = [
        "---",
        "tags:",
        "  - gin-graph",
        "  - gin-scanner",
        "  - moc/index",
        "---",
        "",
        "# Граф проекта (MOC)",
        "",
        "Автогенерация: `scripts/obsidian_graph_refresh.py`. После `get-comments` запусти скрипт снова или `scripts/run_obsidian_scan_and_graph.ps1`.",
        "",
        "## Корни сканирования",
        "",
    ]
    for root in sorted(by_root.keys()):
        moc_r = _graph_path(vault, _moc_root_name(root))
        index_lines.append(f"- {_wikilink(vault, moc_r, _moc_root_name(root))}")
    index_lines.extend(
        [
            "",
            "## Как пользоваться",
            "",
            "- Открой **Graph view** в Obsidian: связи идут по `[[wikilinks]]` из секций ниже и из MOC.",
            "- Добавляй в коде в маркерах ссылки `[[Имя заметки]]` — они попадут в выгрузку и укрепят граф.",
            "",
        ]
    )
    _write_note(index_path, "\n".join(index_lines) + "\n")

    moc_written = 1
    # --- Root / EPIC / ITEM MOCs ---
    for root, epics in sorted(by_root.items()):
        moc_root = _graph_path(vault, _moc_root_name(root))
        moc_written += 1
        root_body = [
            "---",
            "tags:",
            "  - gin-graph",
            "  - gin-scanner",
            "  - moc/root",
            f'  - gin-root/{root.replace("/", "-")}',
            "---",
            "",
            f"# {_moc_root_name(root)}",
            "",
            f"Наверх: {_wikilink(vault, index_path, 'Graph / Index')}",
            "",
            "## EPIC",
            "",
        ]
        for epic_folder in sorted(epics.keys()):
            moc_epic = _graph_path(vault, _moc_epic_name(root, epic_folder))
            root_body.append(f"- {_wikilink(vault, moc_epic, moc_epic.stem)}")
        _write_note(moc_root, "\n".join(root_body) + "\n")

        for epic_folder, items in sorted(epics.items()):
            moc_epic = _graph_path(vault, _moc_epic_name(root, epic_folder))
            moc_written += 1
            epic_body = [
                "---",
                "tags:",
                "  - gin-graph",
                "  - gin-scanner",
                "  - moc/epic",
                f'  - gin-root/{root.replace("/", "-")}',
                "---",
                "",
                f"# {_moc_epic_name(root, epic_folder)}",
                "",
                f"Наверх: {_wikilink(vault, moc_root, moc_root.stem)} · {_wikilink(vault, index_path, 'Index')}",
                "",
                "## ITEM",
                "",
            ]
            for item_folder in sorted(items.keys()):
                moc_item = _graph_path(vault, _moc_item_name(root, epic_folder, item_folder))
                epic_body.append(f"- {_wikilink(vault, moc_item, moc_item.stem)}")
            _write_note(moc_epic, "\n".join(epic_body) + "\n")

            for item_folder, tlist in sorted(items.items()):
                moc_item = _graph_path(vault, _moc_item_name(root, epic_folder, item_folder))
                moc_written += 1
                item_body = [
                    "---",
                    "tags:",
                    "  - gin-graph",
                    "  - gin-scanner",
                    "  - moc/item",
                    f'  - gin-root/{root.replace("/", "-")}',
                    "---",
                    "",
                    f"# {_moc_item_name(root, epic_folder, item_folder)}",
                    "",
                    f"Наверх: {_wikilink(vault, moc_epic, moc_epic.stem)} · {_wikilink(vault, moc_root, moc_root.stem)}",
                    "",
                    "## TOPIC",
                    "",
                ]
                for t in sorted(tlist, key=lambda x: x.path.name):
                    item_body.append(f"- {_wikilink(vault, t.path, t.title)}")
                _write_note(moc_item, "\n".join(item_body) + "\n")

                for t in tlist:
                    block = _build_topic_block(
                        vault,
                        t,
                        index_path,
                        moc_root,
                        moc_epic,
                        moc_item,
                    )
                    raw = t.path.read_text(encoding="utf-8")
                    rest = _strip_old_block(raw)
                    _write_note(t.path, block + rest)

    return len(topics), moc_written


def _snapshot_state(vault: Path) -> tuple[int, float]:
    """Грубая сигнатура для watch: число md и max mtime."""
    vault = vault.resolve()
    mtimes: list[float] = []
    n = 0
    for p in vault.rglob("*.md"):
        if GRAPH_DIR_NAME in p.parts and p.parent.name == GRAPH_DIR_NAME:
            # пересчитываем и при изменении только Graph — тоже ок
            pass
        try:
            st = p.stat()
        except OSError:
            continue
        mtimes.append(st.st_mtime)
        n += 1
    return n, max(mtimes) if mtimes else 0.0


def watch_loop(vault: Path, interval: float) -> None:
    vault = vault.resolve()
    print(f"Watch: {vault} (interval {interval}s). Ctrl+C — выход.", file=sys.stderr)
    last: tuple[int, float] | None = None
    while True:
        snap = _snapshot_state(vault)
        if snap != last:
            try:
                n_top, n_moc = rebuild_graph(vault)
                print(
                    time.strftime("%H:%M:%S"),
                    f"graph ok: topics={n_top} moc_nodes~={n_moc}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(time.strftime("%H:%M:%S"), "graph error:", e, file=sys.stderr)
            # снимок после сборки, иначе mtimes всегда «новые» и цикл гоняет rebuild
            last = _snapshot_state(vault)
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="Obsidian MOC + wikilinks для scanner-output")
    ap.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"Корень vault (по умолчанию {DEFAULT_VAULT})",
    )
    ap.add_argument(
        "--watch",
        action="store_true",
        help="Переобновлять граф при изменении .md (опрос раз в --interval сек)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Интервал опроса в секундах для --watch (по умолчанию 15)",
    )
    args = ap.parse_args()
    vault: Path = args.vault

    if args.watch:
        watch_loop(vault, max(1.0, args.interval))
        return

    n_top, n_moc = rebuild_graph(vault)
    print(f"OK: topics={n_top} moc_files_written~={n_moc} vault={vault.resolve()}")


if __name__ == "__main__":
    main()
