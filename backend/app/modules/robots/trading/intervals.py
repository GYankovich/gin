"""Разрешение интервалов свечей: исполнение (T-Invest) vs исторический анализ (MOEX ISS).

Роли (см. ``resolve_candle_interval_roles``):
- **execution** — ``strategy_params.interval``: сигналы, live-стрим, свечи симуляции бэктеста.
- **moex_history** — ``strategy_params.moex_analysis_interval`` (по умолчанию 10m): prefetch/gap-fill
  MOEX для pipeline, скрининга и преданализа за N дней.

MOEX ISS ``candles.json`` фактически отдаёт бары только для кодов ниже (interval=5 → 0 строк).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from app.modules.market_data_v1.intervals import strategy_interval_code_to_shared_canonical

# Фактически работающие коды MOEX ISS (проверено на TQBR/SBER).
MOEX_ISS_CANDLE_INTERVAL_CODES = frozenset({1, 10, 60, 24, 7, 31, 4})

# Обратная совместимость имён в тестах и prefetch-guard.
MOEX_CANDLE_INTERVAL_CODES = MOEX_ISS_CANDLE_INTERVAL_CODES

DEFAULT_MOEX_ANALYSIS_INTERVAL = "CANDLE_INTERVAL_10_MIN"

_BYBIT_INTERVAL_BY_CODE: dict[int, str] = {
    1: "1",
    3: "3",
    5: "5",
    10: "5",  # nearest supported
    15: "15",
    30: "30",
    60: "60",
    120: "120",
    240: "240",
    24: "D",
    7: "W",
    31: "M",
}

# T-Invest / UI enum → минуты (или MOEX day/week/month code).
_STRATEGY_INTERVAL_MINUTES: dict[str, int] = {
    "CANDLE_INTERVAL_1_MIN": 1,
    "CANDLE_INTERVAL_2_MIN": 2,
    "CANDLE_INTERVAL_3_MIN": 3,
    "CANDLE_INTERVAL_5_MIN": 5,
    "CANDLE_INTERVAL_10_MIN": 10,
    "CANDLE_INTERVAL_15_MIN": 15,
    "CANDLE_INTERVAL_30_MIN": 30,
    "CANDLE_INTERVAL_HOUR": 60,
    "CANDLE_INTERVAL_2_HOUR": 120,
    "CANDLE_INTERVAL_4_HOUR": 240,
    "CANDLE_INTERVAL_DAY": 24,
}

# Дневные/недельные коды MOEX (не «минуты»).
_MOEX_SPECIAL_FROM_MINUTES: dict[int, int] = {
    7 * 24 * 60: 7,
    31 * 24 * 60: 31,
    90 * 24 * 60: 4,
}


@dataclass(frozen=True)
class ResolvedInterval:
    """Нормализованный интервал (T-Invest enum / M5 / I10 → коды кэша и MOEX)."""

    raw: str
    code_num: int
    cache_label: str
    shared_canonical: Optional[str]
    min_required_candles: int
    moex_interval_code: int

    @property
    def supports_moex_iss(self) -> bool:
        return int(self.moex_interval_code) in MOEX_ISS_CANDLE_INTERVAL_CODES

    @property
    def supports_moex_prefetch(self) -> bool:
        return self.supports_moex_iss


@dataclass(frozen=True)
class CandleIntervalRoles:
    """Раздельные интервалы: операционные решения vs MOEX-история."""

    execution: ResolvedInterval
    moex_history: ResolvedInterval


def interval_code_to_cache_label(interval_code: int) -> str:
    ic = int(interval_code)
    if ic == 5:
        return "M5"
    if ic == 24:
        return "D1"
    return f"I{ic}"


def bar_duration_seconds(interval_code: int) -> int:
    """Approximate bar duration in seconds for latency → bar offset conversion."""
    ic = int(interval_code)
    if ic == 24:
        return 24 * 3600
    if ic == 7:
        return 7 * 24 * 3600
    if ic == 31:
        return 31 * 24 * 3600
    if ic == 4:
        return 90 * 24 * 3600
    if ic >= 60:
        return ic * 60
    return max(60, ic * 60)


def minutes_to_moex_interval_code(minutes: int) -> int:
    m = int(minutes)
    if m in _MOEX_SPECIAL_FROM_MINUTES:
        return _MOEX_SPECIAL_FROM_MINUTES[m]
    return m


def resolve_strategy_interval(raw: str) -> ResolvedInterval:
    """Парсит interval из strategy_params (CANDLE_INTERVAL_*, M5, I10, …)."""
    text = str(raw or "CANDLE_INTERVAL_10_MIN").strip()
    upper = text.upper().replace(" ", "")

    code_num: Optional[int] = None

    if upper in _STRATEGY_INTERVAL_MINUTES:
        mins = _STRATEGY_INTERVAL_MINUTES[upper]
        code_num = minutes_to_moex_interval_code(mins)
    else:
        token_map = (
            (("10_MIN", "INTERVAL_10", "I10", "10M", "10MIN", "M10"), 10),
            (("5_MIN", "INTERVAL_5", "M5", "5M", "5MIN", "I5"), 5),
            (("1_MIN", "INTERVAL_1", "I1", "1M", "1MIN", "M1"), 1),
            (("60_MIN", "HOUR", "INTERVAL_60", "I60", "1H", "60M", "M60"), 60),
            (("15_MIN", "INTERVAL_15", "I15", "15M", "15MIN", "M15"), 15),
            (("30_MIN", "INTERVAL_30", "I30", "30M", "30MIN", "M30"), 30),
            (("2_MIN", "INTERVAL_2", "I2", "2M", "2MIN", "M2"), 2),
            (("3_MIN", "INTERVAL_3", "I3", "3M", "3MIN", "M3"), 3),
            (("WEEK", "INTERVAL_7", "I7", "1W"), 7),
            (("MONTH", "INTERVAL_31", "I31"), 31),
            (("QUARTER", "INTERVAL_4", "I4", "1Q", "1K"), 4),
            (("DAY", "D1", "INTERVAL_24", "I24", "24H"), 24),
        )
        for tokens, num in token_map:
            if any(tok in upper for tok in tokens):
                code_num = num
                break

        if code_num is None:
            m = re.search(r"(?:INTERVAL[_-]?|M|I)?(\d+)\s*(MIN|M|H)?", upper)
            if m:
                n = int(m.group(1))
                unit = (m.group(2) or "MIN").upper()
                if unit in ("H", "HR", "HOUR") or "HOUR" in upper:
                    code_num = n * 60 if n < 24 else 24
                elif unit in ("M", "MIN") or "MIN" in upper:
                    code_num = minutes_to_moex_interval_code(n)
                else:
                    code_num = n

    if code_num is None:
        code_num = 10

    cache_label = interval_code_to_cache_label(code_num)
    shared = strategy_interval_code_to_shared_canonical(code_num)
    min_req = 20 if code_num in (1, 10, 60) else 1
    moex_code = int(code_num)

    return ResolvedInterval(
        raw=text,
        code_num=int(code_num),
        cache_label=cache_label,
        shared_canonical=shared,
        min_required_candles=min_req,
        moex_interval_code=moex_code,
    )


def resolve_candle_interval_roles(
    strategy_params: Optional[Mapping[str, Any]] = None,
    *,
    default_execution: str = "CANDLE_INTERVAL_5_MIN",
) -> CandleIntervalRoles:
    """
    Две роли интервала из ``strategy_params``.

    - ``interval`` → execution (T-Invest / симуляция / индикаторы стратегии).
    - ``moex_analysis_interval`` → MOEX prefetch; если не задан или не поддерживается ISS — 10m.
    """
    sp = dict(strategy_params or {})
    execution = resolve_strategy_interval(
        str(sp.get("interval") or default_execution),
    )
    moex_raw = (
        sp.get("moex_analysis_interval")
        or sp.get("history_candles_interval")
        or DEFAULT_MOEX_ANALYSIS_INTERVAL
    )
    moex = resolve_strategy_interval(str(moex_raw))
    if not moex.supports_moex_iss:
        moex = resolve_strategy_interval(DEFAULT_MOEX_ANALYSIS_INTERVAL)
    return CandleIntervalRoles(execution=execution, moex_history=moex)


def strategy_interval_to_bybit_kline(raw: str | ResolvedInterval) -> str:
    resolved = raw if isinstance(raw, ResolvedInterval) else resolve_strategy_interval(str(raw))
    return _BYBIT_INTERVAL_BY_CODE.get(int(resolved.code_num), "5")


# --- Broker-specific canonical storage (§4.4) ---

_TINVEST_ENUM_BY_CODE: dict[int, str] = {
    1: "CANDLE_INTERVAL_1_MIN",
    5: "CANDLE_INTERVAL_5_MIN",
    10: "CANDLE_INTERVAL_10_MIN",
    15: "CANDLE_INTERVAL_15_MIN",
    30: "CANDLE_INTERVAL_30_MIN",
    60: "CANDLE_INTERVAL_HOUR",
    120: "CANDLE_INTERVAL_2_HOUR",
    240: "CANDLE_INTERVAL_4_HOUR",
    24: "CANDLE_INTERVAL_DAY",
}

_TINVEST_ENUM_TO_BYBIT_UI: dict[str, str] = {
    "CANDLE_INTERVAL_1_MIN": "1m",
    "CANDLE_INTERVAL_5_MIN": "5m",
    "CANDLE_INTERVAL_10_MIN": "15m",
    "CANDLE_INTERVAL_15_MIN": "30m",
    "CANDLE_INTERVAL_30_MIN": "1h",
    "CANDLE_INTERVAL_HOUR": "4h",
    "CANDLE_INTERVAL_4_HOUR": "1d",
    "CANDLE_INTERVAL_DAY": "1d",
}

_BYBIT_UI_CANONICAL = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})


def normalize_tinvest_interval(
    raw: str,
    *,
    default: str = "CANDLE_INTERVAL_5_MIN",
) -> str:
    """Canonical T-Invest enum string for MOEX strategy_params.interval."""
    text = str(raw or default).strip().upper().replace(" ", "")
    if text in _STRATEGY_INTERVAL_MINUTES:
        code = minutes_to_moex_interval_code(_STRATEGY_INTERVAL_MINUTES[text])
        return _TINVEST_ENUM_BY_CODE.get(code, default)
    resolved = resolve_strategy_interval(raw)
    return _TINVEST_ENUM_BY_CODE.get(int(resolved.code_num), default)


def normalize_bybit_interval(raw: str, *, default: str = "5m") -> str:
    """Canonical ByBit UI string for crypto strategy_params.interval."""
    text = str(raw or default).strip()
    lower = text.lower()
    if lower in _BYBIT_UI_CANONICAL:
        return lower
    upper = text.upper().replace(" ", "")
    if upper in _TINVEST_ENUM_TO_BYBIT_UI:
        return _TINVEST_ENUM_TO_BYBIT_UI[upper]
    resolved = resolve_strategy_interval(text)
    for enum_key, ui_val in _TINVEST_ENUM_TO_BYBIT_UI.items():
        enum_resolved = resolve_strategy_interval(enum_key)
        if enum_resolved.code_num == resolved.code_num:
            return ui_val
    return default


def normalize_interval(raw: str, broker_type: str) -> str:
    """Normalize strategy interval for broker (tinvest enum vs bybit UI string)."""
    bt = str(broker_type or "tinvest").strip().lower()
    if bt == "bybit":
        return normalize_bybit_interval(raw)
    return normalize_tinvest_interval(raw)


# Back-compat alias used by IndicatorService / older call sites.
resolve_interval = resolve_strategy_interval


__all__ = [
    "CandleIntervalRoles",
    "DEFAULT_MOEX_ANALYSIS_INTERVAL",
    "MOEX_CANDLE_INTERVAL_CODES",
    "MOEX_ISS_CANDLE_INTERVAL_CODES",
    "ResolvedInterval",
    "interval_code_to_cache_label",
    "minutes_to_moex_interval_code",
    "normalize_bybit_interval",
    "normalize_interval",
    "normalize_tinvest_interval",
    "resolve_candle_interval_roles",
    "resolve_interval",
    "resolve_strategy_interval",
    "strategy_interval_to_bybit_kline",
]
