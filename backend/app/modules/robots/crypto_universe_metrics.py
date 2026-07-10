"""Pure metric helpers for ByBit crypto universe screening."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def compute_rvol(volumes: Sequence[float]) -> Optional[float]:
    """RVOL = last volume / mean of prior volumes."""
    vals = [float(v) for v in volumes if v is not None and float(v) > 0]
    if len(vals) < 2:
        return None
    current = vals[-1]
    prior = vals[:-1]
    avg = sum(prior) / len(prior)
    if avg <= 0:
        return None
    return current / avg


def compute_atr_percent(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 14,
) -> Optional[float]:
    """ATR% = ATR / last close * 100 (simple rolling mean TR)."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, n):
        high = float(highs[i])
        low = float(lows[i])
        prev_close = float(closes[i - 1])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    last_close = float(closes[n - 1])
    if last_close <= 0:
        return None
    return atr / last_close * 100.0


def compute_lsr(buy_ratio: float, sell_ratio: float) -> Optional[float]:
    if sell_ratio <= 0:
        return None
    return float(buy_ratio) / float(sell_ratio)


def open_interest_usd(open_interest_base: float, mark_price: float) -> Optional[float]:
    oi = float(open_interest_base or 0)
    price = float(mark_price or 0)
    if oi <= 0 or price <= 0:
        return None
    return oi * price


def avg_funding_rate(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    rates: List[float] = []
    for row in rows:
        try:
            rates.append(float(row.get("funding_rate") or row.get("fundingRate") or 0))
        except (TypeError, ValueError):
            continue
    if not rates:
        return None
    return sum(rates) / len(rates)


def passes_funding_range(
    avg_rate: Optional[float],
    *,
    min_rate: Optional[float],
    max_rate: Optional[float],
) -> tuple[bool, str]:
    if min_rate is None and max_rate is None:
        return True, "funding_disabled"
    if avg_rate is None:
        return False, "funding_unavailable"
    if min_rate is not None and avg_rate < float(min_rate):
        return False, f"funding_below_min:{avg_rate:.6f}"
    if max_rate is not None and avg_rate > float(max_rate):
        return False, f"funding_above_max:{avg_rate:.6f}"
    return True, "funding_ok"


def passes_oi(min_oi_usd: Optional[float], oi_usd: Optional[float]) -> tuple[bool, str]:
    # min_oi <= 0 is treated as disabled filter.
    if min_oi_usd is None or float(min_oi_usd) <= 0.0:
        return True, "oi_disabled"
    if oi_usd is None:
        return False, "oi_unavailable"
    if oi_usd < float(min_oi_usd):
        return False, f"oi_below_min:{oi_usd:.0f}"
    return True, "oi_ok"


def passes_lsr(
    lsr: Optional[float],
    *,
    min_lsr: Optional[float],
    max_lsr: Optional[float],
) -> tuple[bool, str]:
    if min_lsr is None and max_lsr is None:
        return True, "lsr_disabled"
    if lsr is None:
        # Graceful degradation for backtest: missing historical LSR should not
        # reject the whole universe when this metric is unavailable.
        return True, "lsr_unavailable_ignored"
    if min_lsr is not None and lsr < float(min_lsr):
        return False, f"lsr_below_min:{lsr:.4f}"
    if max_lsr is not None and lsr > float(max_lsr):
        return False, f"lsr_above_max:{lsr:.4f}"
    return True, "lsr_ok"


def passes_rvol(min_rvol: Optional[float], rvol: Optional[float]) -> tuple[bool, str]:
    if min_rvol is None:
        return True, "rvol_disabled"
    if rvol is None:
        return False, "rvol_unavailable"
    if rvol < float(min_rvol):
        return False, f"rvol_below_min:{rvol:.4f}"
    return True, "rvol_ok"


def passes_atr_percent(
    atr_pct: Optional[float],
    *,
    min_pct: Optional[float],
    max_pct: Optional[float],
) -> tuple[bool, str]:
    if min_pct is None and max_pct is None:
        return True, "atr_disabled"
    if atr_pct is None:
        return False, "atr_unavailable"
    if min_pct is not None and atr_pct < float(min_pct):
        return False, f"atr_below_min:{atr_pct:.4f}"
    if max_pct is not None and atr_pct > float(max_pct):
        return False, f"atr_above_max:{atr_pct:.4f}"
    return True, "atr_ok"
