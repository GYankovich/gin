"""
Insert or refresh Obsidian Source Scanner marker blocks.

Python: lines starting with #///EPIC
TS/TSX/JS: lines starting with ///@EPIC

Use --refresh to rewrite only *auto-generated* blocks (second line contains
«автоматическая разметка»), updating TOPIC to a path-unique value — fixes
duplicate [1] / output path collisions (many __init__.py → same Init.md).

Usage:
 python scripts/apply_obsidian_scanner_markers.py
 python scripts/apply_obsidian_scanner_markers.py --refresh
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AUTO_SNIPPET = "автоматическая разметка для Obsidian Source Scanner"

SKIP_DIR_NAMES = frozenset(
 {
 "venv",
 ".venv",
 "node_modules",
 "__pycache__",
 ".git",
 "dist",
 "site-packages",
 ".idea",
 ".vscode",
 }
)

SCAN_ROOTS = [
 ROOT / "backend" / "app",
 ROOT / "alembic",
 ROOT / "frontend" / "src",
]


def has_py_marker(text: str) -> bool:
 return "#///EPIC" in text


def has_ts_marker(text: str) -> bool:
 return "///@EPIC" in text


def epic_item_for_rel(rel_posix: str) -> tuple[str, str]:
 r = rel_posix.lower()
 if r.startswith("backend/app/core/"):
 return "Platform", "Core"
 if r.startswith("backend/app/modules/"):
 parts = r.split("/")
 if len(parts) >= 3:
 mod = parts[2].replace("_", " ").title().replace(" ", "")
 return mod, "Module"
 if r.startswith("backend/app/"):
 return "Platform", "App"
 if r.startswith("alembic/"):
 return "Platform", "Migrations"
 if r.startswith("frontend/src/pages/"):
 return "Frontend", "Pages"
 if r.startswith("frontend/src/components/"):
 return "Frontend", "Components"
 if r.startswith("frontend/src/services/"):
 return "Frontend", "APIClient"
 if r.startswith("frontend/src/stores/"):
 return "Frontend", "State"
 if r.startswith("frontend/src/hooks/"):
 return "Frontend", "Hooks"
 if r.startswith("frontend/src/types/"):
 return "Frontend", "Types"
 if r.startswith("frontend/src/modules/"):
 return "Frontend", "Modules"
 if r.startswith("frontend/src/shared/"):
 return "Frontend", "Shared"
 if r.startswith("frontend/src/core/"):
 return "Frontend", "Core"
 if r.startswith("frontend/src/app/"):
 return "Frontend", "App"
 if r.startswith("frontend/src/"):
 return "Frontend", "Src"
 return "Project", "Source"


def _segment_token(part: str) -> str:
 """Folder or filename stem → PascalCase token (no dots, safe for paths)."""
 part = part.replace(".", " ").replace("-", " ").replace("_", " ")
 return "".join(w.title() for w in part.split() if w)


def topic_from_rel(rel_posix: str) -> str:
 """
 Unique topic from repo-relative path (avoids many Init.md / Schemas.md collisions).
 """
 p = Path(rel_posix)
 tokens = [_segment_token(x) for x in p.with_suffix("").parts]
 out = "".join(tokens)
 return (out or "Module")[:100]


def py_insertion_index(lines: list[str]) -> int:
 i = 0
 n = len(lines)
 if i < n and lines[i].startswith("#!"):
 i += 1
 if i < n and lines[i].strip() == "":
 i += 1
 if i < n and lines[i].strip().startswith("#") and "coding" in lines[i]:
 i += 1
 if i < n and lines[i].strip() == "":
 i += 1
 while i < n and lines[i].strip().startswith("from __future__"):
 i += 1
 if i > 0 and i < n and lines[i - 1].strip().startswith("from __future__") and lines[i].strip() == "":
 i += 1

 if i < n:
 raw = lines[i]
 stripped = raw.lstrip()
 if stripped.startswith('"""') or stripped.startswith("'''"):
 quote = '"""' if stripped.startswith('"""') else "'''"
 if stripped.count(quote) >= 2 and stripped.rstrip().endswith(quote) and len(stripped.strip()) > len(quote) * 2:
 i += 1
 else:
 i += 1
 while i < n:
 if quote in lines[i]:
 i += 1
 break
 i += 1
 if i < n and lines[i].strip() == "":
 i += 1
 return i


def ts_insertion_index(lines: list[str]) -> int:
 i = 0
 n = len(lines)
 while i < n:
 s = lines[i].strip()
 if s.startswith("/// <reference"):
 i += 1
 continue
 break
 return i


def build_py_block(rel_posix: str) -> list[str]:
 epic, item = epic_item_for_rel(rel_posix)
 topic = topic_from_rel(rel_posix)
 return [
 f"#///EPIC {epic}.ITEM {item}.TOPIC {topic} [1]\n",
 f"#/// Исходный модуль `{rel_posix}` — {AUTO_SNIPPET}.\n",
 "\n",
 ]


def build_ts_block(rel_posix: str) -> list[str]:
 epic, item = epic_item_for_rel(rel_posix)
 topic = topic_from_rel(rel_posix)
 return [
 f"///@EPIC {epic}.ITEM {item}.TOPIC {topic} [1]\n",
 f"///@ Исходный модуль `{rel_posix}` — {AUTO_SNIPPET}.\n",
 "\n",
 ]


def iter_files():
 for base in SCAN_ROOTS:
 if not base.is_dir():
 continue
 for p in base.rglob("*"):
 if p.is_dir():
 continue
 if any(part in SKIP_DIR_NAMES for part in p.parts):
 continue
 if p.suffix == ".py":
 yield p
 elif p.suffix in {".ts", ".tsx", ".js", ".jsx"}:
 yield p


def _is_auto_py_block(lines: list[str], i: int) -> bool:
 if i >= len(lines) or not lines[i].startswith("#///EPIC"):
 return False
 if i + 1 >= len(lines):
 return False
 return AUTO_SNIPPET in lines[i + 1]


def _is_auto_ts_block(lines: list[str], i: int) -> bool:
 if i >= len(lines) or not lines[i].startswith("///@EPIC"):
 return False
 if i + 1 >= len(lines):
 return False
 return AUTO_SNIPPET in lines[i + 1]


def refresh_auto_markers(path: Path, rel: str) -> bool:
 text = path.read_text(encoding="utf-8")
 lines = text.splitlines(keepends=True)
 out: list[str] = []
 changed = False
 i = 0
 is_py = path.suffix == ".py"
 while i < len(lines):
 if is_py and _is_auto_py_block(lines, i):
 out.extend(build_py_block(rel))
 i += 2
 if i < len(lines) and lines[i].strip() == "":
 i += 1
 changed = True
 continue
 if not is_py and _is_auto_ts_block(lines, i):
 out.extend(build_ts_block(rel))
 i += 2
 if i < len(lines) and lines[i].strip() == "":
 i += 1
 changed = True
 continue
 out.append(lines[i])
 i += 1
 if changed:
 path.write_text("".join(out), encoding="utf-8")
 return changed


def process_file(path: Path, *, refresh: bool) -> str:
 """
 Returns: 'inserted' | 'refreshed' | 'skip'
 """
 rel = path.relative_to(ROOT).as_posix()
 if refresh and refresh_auto_markers(path, rel):
 return "refreshed"

 text = path.read_text(encoding="utf-8")
 if path.suffix == ".py":
 if has_py_marker(text):
 return "skip"
 lines = text.splitlines(keepends=True)
 idx = py_insertion_index(lines)
 block = build_py_block(rel)
 path.write_text("".join(lines[:idx] + block + lines[idx:]), encoding="utf-8")
 return "inserted"
 else:
 if has_ts_marker(text):
 return "skip"
 lines = text.splitlines(keepends=True)
 idx = ts_insertion_index(lines)
 block = build_ts_block(rel)
 path.write_text("".join(lines[:idx] + block + lines[idx:]), encoding="utf-8")
 return "inserted"


def main() -> int:
 ap = argparse.ArgumentParser(description="Apply Obsidian Source Scanner markers")
 ap.add_argument(
 "--refresh",
 action="store_true",
 help="Rewrite auto-generated marker blocks to use path-unique TOPIC",
 )
 args = ap.parse_args()

 inserted = refreshed = skipped = 0
 for path in sorted(iter_files(), key=lambda x: str(x).lower()):
 try:
 res = process_file(path, refresh=args.refresh)
 if res == "inserted":
 inserted += 1
 print(f"+ {path.relative_to(ROOT)}")
 elif res == "refreshed":
 refreshed += 1
 print(f"~ {path.relative_to(ROOT)}")
 else:
 skipped += 1
 except OSError as e:
 print(f"! {path.relative_to(ROOT)}: {e}", file=sys.stderr)
 print(f"Done. inserted={inserted} refreshed={refreshed} skipped={skipped}")
 return 0


if __name__ == "__main__":
 raise SystemExit(main())
