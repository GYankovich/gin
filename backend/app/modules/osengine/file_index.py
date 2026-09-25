"""Поиск файлов свечей OsEngine под Data/."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from app.modules.osengine.intervals_map import (
    cache_interval_to_osengine_tf,
    known_osengine_timeframes,
    normalize_cache_interval,
)
from app.modules.osengine.types import InstrumentKey

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CandleFileHit:
    path: Path
    ticker: str
    osengine_tf: str
    cache_interval: str
    set_name: Optional[str] = None


def _safe_listdir(path: Path) -> List[Path]:
    try:
        return sorted(path.iterdir())
    except OSError as exc:
        logger.warning("osengine data listdir failed path=%s: %s", path, exc)
        return []


def find_candle_files(
    data_root: str | Path,
    *,
    instrument: InstrumentKey,
    interval: str,
    max_files: int = 32,
) -> List[CandleFileHit]:
    """
    Ищет файлы вида:
      Data/{Set}/{SecName}/{TimeFrame}/{SecName}.txt
      Data/{Set}/{SecName}/{TimeFrame}/Temp/*.txt

    Также подхватывает connector-history layouts, если в пути есть {TimeFrame}/{TICKER}.txt.
    """
    root = Path(data_root)
    if not root.is_dir():
        logger.warning("osengine data_root missing or not a dir: %s", root)
        return []

    ticker = instrument.normalized().ticker
    tf = cache_interval_to_osengine_tf(interval)
    if not tf:
        logger.warning(
            "osengine unsupported interval=%s (normalized=%s)",
            interval,
            normalize_cache_interval(interval),
        )
        return []

    cache_iv = normalize_cache_interval(interval)
    hits: List[CandleFileHit] = []
    ticker_l = ticker.lower()
    tf_names = known_osengine_timeframes()

    # Быстрый путь: */{TICKER}/{TF}/{TICKER}.txt
    for set_dir in _safe_listdir(root):
        if not set_dir.is_dir():
            continue
        if set_dir.name.lower() in ("osdata", "temp"):
            # OsData connector tree — тоже обходим ниже общим сканом по TF
            pass
        sec_dir = set_dir / ticker
        if not sec_dir.is_dir():
            # иногда имя с суффиксом класса: SBER_TQBR
            for candidate in _safe_listdir(set_dir):
                if not candidate.is_dir():
                    continue
                name = candidate.name
                if name.upper() == ticker or name.upper().startswith(ticker + "_"):
                    sec_dir = candidate
                    break
            else:
                continue
        tf_dir = sec_dir / tf
        if not tf_dir.is_dir():
            continue
        main = tf_dir / f"{sec_dir.name}.txt"
        if not main.is_file():
            main = tf_dir / f"{ticker}.txt"
        if main.is_file():
            hits.append(
                CandleFileHit(
                    path=main,
                    ticker=ticker,
                    osengine_tf=tf,
                    cache_interval=cache_iv,
                    set_name=set_dir.name,
                )
            )
        temp_dir = tf_dir / "Temp"
        if temp_dir.is_dir():
            for piece in _safe_listdir(temp_dir):
                if piece.suffix.lower() == ".txt" and piece.is_file() and not piece.name.startswith("Settings_"):
                    hits.append(
                        CandleFileHit(
                            path=piece,
                            ticker=ticker,
                            osengine_tf=tf,
                            cache_interval=cache_iv,
                            set_name=set_dir.name,
                        )
                    )
        if len(hits) >= max_files:
            break

    if hits:
        return hits[:max_files]

    # Fallback: рекурсивный поиск папок TF с файлом тикера
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        if base.name != tf:
            continue
        parent = base.parent.name.upper()
        if parent != ticker and not parent.startswith(ticker + "_"):
            # файл может называться TICKER.txt даже если папка другая
            pass
        for name in filenames:
            if not name.lower().endswith(".txt"):
                continue
            if name.startswith("Settings_"):
                continue
            stem = Path(name).stem.upper()
            if stem != ticker and stem != parent and not stem.startswith(ticker):
                continue
            hits.append(
                CandleFileHit(
                    path=base / name,
                    ticker=ticker,
                    osengine_tf=tf,
                    cache_interval=cache_iv,
                    set_name=base.parent.parent.name if base.parent.parent != root else None,
                )
            )
            if len(hits) >= max_files:
                return hits
    return hits


def resolve_data_root(explicit: Optional[str] = None) -> Optional[Path]:
    from app.core.config import settings

    raw = (explicit if explicit is not None else settings.OSENGINE_DATA_ROOT) or ""
    raw = str(raw).strip()
    if not raw:
        return None
    return Path(raw)


__all__ = ["CandleFileHit", "find_candle_files", "resolve_data_root"]
