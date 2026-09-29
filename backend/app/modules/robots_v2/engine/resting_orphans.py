"""Detect resting LIMIT orders that no longer match ledger/strategy intent."""

from __future__ import annotations

from typing import Any, Literal, Protocol

Scope = Literal["exit", "entry", "all"]


class _RestingLike(Protocol):
    side: str
    kind: str | None
    reason: str | None
    reduce_only: bool


_EXIT_KINDS = frozenset({"exit_sl_tp", "exit_strategy", "flatten"})
_EXIT_REASONS = frozenset({"take_profit", "stop_loss", "broker_sync", "hard_stop", "soft_stop"})


def is_exit_resting(ro: _RestingLike) -> bool:
    kind = str(ro.kind or "").lower()
    reason = str(ro.reason or "").lower()
    if bool(getattr(ro, "reduce_only", False)):
        return True
    if kind in _EXIT_KINDS:
        return True
    if reason in _EXIT_REASONS:
        return True
    return False


def is_entry_resting(ro: _RestingLike) -> bool:
    kind = str(ro.kind or "").lower()
    if kind == "entry":
        return True
    return not is_exit_resting(ro)


def select_orphan_resting_tickers(
    resting: dict[str, Any],
    *,
    held_tickers: set[str],
    wanted_entries: set[tuple[str, str]],
    scope: Scope = "all",
) -> list[str]:
    """Return tickers whose resting LIMIT should be cancelled.

    - Exit/reduce resting without an open position → orphan
    - Entry resting whose (ticker, side) is not in wanted_entries → orphan
    """
    held = {str(t).upper() for t in held_tickers}
    wanted = {(str(t).upper(), str(s).upper()) for t, s in wanted_entries}
    orphans: list[str] = []
    for ticker, ro in resting.items():
        t = str(ticker or "").upper()
        if not t:
            continue
        if is_exit_resting(ro):
            if scope in ("exit", "all") and t not in held:
                orphans.append(t)
            continue
        if is_entry_resting(ro):
            if scope not in ("entry", "all"):
                continue
            side = str(getattr(ro, "side", "") or "").upper()
            if (t, side) not in wanted:
                orphans.append(t)
    return orphans
