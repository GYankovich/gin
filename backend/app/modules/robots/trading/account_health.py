"""Live account health gates: MMR, equity drawdown, book freshness."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# ByBit UNIFIED: accountMMRate → 1.0 means maintenance margin exhausted (liq).
DEFAULT_MM_RATE_HALT = 0.80
DEFAULT_LIQ_DISTANCE_HALT = 0.05  # halt if mark within 5% of liqPrice
DEFAULT_REFRESH_FAIL_HALT = 3


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def extract_wallet_margin_health(wallet: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Parse ByBit UNIFIED wallet row into comparable margin metrics."""
    w = wallet if isinstance(wallet, dict) else {}
    equity = _as_float(w.get("totalEquity"))
    mm_rate = _as_float(w.get("accountMMRate"))
    im_rate = _as_float(w.get("accountIMRate"))
    total_mm = _as_float(w.get("totalMaintenanceMargin"))
    total_im = _as_float(w.get("totalInitialMargin"))
    # Fallback: derive rate from absolute margins if rate fields missing.
    if mm_rate <= 0 and equity > 0 and total_mm > 0:
        mm_rate = total_mm / equity
    if im_rate <= 0 and equity > 0 and total_im > 0:
        im_rate = total_im / equity
    return {
        "equity": equity,
        "account_mm_rate": mm_rate,
        "account_im_rate": im_rate,
        "total_maintenance_margin": total_mm,
        "total_initial_margin": total_im,
    }


def min_liq_distance_pct(positions: Optional[list]) -> Optional[float]:
    """Smallest |mark-liq|/mark across open perps; None if unknown."""
    best: Optional[float] = None
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("instrument_type") or "").lower() == "currency":
            continue
        mark = _as_float(p.get("mark_price"))
        if mark <= 0:
            cur = p.get("current_price")
            if isinstance(cur, dict):
                mark = _as_float(cur.get("decimal"))
            else:
                mark = _as_float(cur)
        liq = _as_float(p.get("liq_price") or p.get("liquidation_price"))
        if mark <= 0 or liq <= 0:
            continue
        dist = abs(mark - liq) / mark
        if best is None or dist < best:
            best = dist
    return best


def evaluate_margin_halt(
    health: Dict[str, Any],
    *,
    mm_rate_halt: float = DEFAULT_MM_RATE_HALT,
    liq_distance_halt: float = DEFAULT_LIQ_DISTANCE_HALT,
) -> Tuple[bool, str]:
    """Return (halt, reason) from wallet + optional liq proximity."""
    mm_rate = _as_float(health.get("account_mm_rate"))
    threshold = max(0.0, float(mm_rate_halt or DEFAULT_MM_RATE_HALT))
    if threshold > 0 and mm_rate >= threshold:
        return True, f"account_mm_rate={mm_rate:.4f}>={threshold:.4f}"

    liq_dist = health.get("min_liq_distance_pct")
    if liq_dist is not None:
        try:
            dist = float(liq_dist)
        except Exception:
            dist = None
        lim = max(0.0, float(liq_distance_halt or DEFAULT_LIQ_DISTANCE_HALT))
        if dist is not None and lim > 0 and dist <= lim:
            return True, f"near_liquidation distance={dist:.4f}<={lim:.4f}"
    return False, ""


def evaluate_equity_drawdown_halt(
    *,
    equity: float,
    peak_equity: float,
    session_start_equity: float,
    max_drawdown_percent: float,
) -> Tuple[bool, str]:
    """Halt when drawdown from peak (or session start) exceeds max_drawdown_percent."""
    max_dd = float(max_drawdown_percent or 0.0)
    if max_dd <= 0:
        return False, ""
    eq = float(equity or 0.0)
    peak = max(float(peak_equity or 0.0), float(session_start_equity or 0.0), eq)
    if peak <= 0:
        return False, ""
    dd_pct = (peak - eq) / peak * 100.0
    if dd_pct >= max_dd:
        return True, f"equity_drawdown={dd_pct:.2f}%>=max_drawdown={max_dd:.2f}%"
    return False, ""


def evaluate_refresh_fail_halt(
    fail_streak: int,
    *,
    halt_after: int = DEFAULT_REFRESH_FAIL_HALT,
) -> Tuple[bool, str]:
    limit = max(1, int(halt_after or DEFAULT_REFRESH_FAIL_HALT))
    streak = int(fail_streak or 0)
    if streak >= limit:
        return True, f"account_book_refresh_failed x{streak}>={limit}"
    return False, ""


__all__ = [
    "DEFAULT_LIQ_DISTANCE_HALT",
    "DEFAULT_MM_RATE_HALT",
    "DEFAULT_REFRESH_FAIL_HALT",
    "evaluate_equity_drawdown_halt",
    "evaluate_margin_halt",
    "evaluate_refresh_fail_halt",
    "extract_wallet_margin_health",
    "min_liq_distance_pct",
]
