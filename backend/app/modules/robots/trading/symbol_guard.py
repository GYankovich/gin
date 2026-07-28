"""
SymbolGuard — единый in-flight / pending-close guard для Stage4/5/6.

Один источник правды: session._in_flight_orders + _pending_position_closures,
плюс опциональная проверка активных заявок на брокере (restart-safe).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

_BROKER_ORDER_ACTIVE = frozenset({
    "EXECUTION_REPORT_STATUS_NEW",
    "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
    "NEW",
    "PARTIALLYFILLED",
    "Created",
    "New",
    "PartiallyFilled",
})


def normalize_figi(figi: Any) -> str:
    return str(figi or "").upper().strip()


class SymbolGuard:
    """Shared blocked-figi set for exits and entries."""

    def __init__(
        self,
        *,
        in_flight_orders: Optional[Dict[str, str]] = None,
        pending_position_closures: Optional[Dict[str, Any]] = None,
        broker: Any = None,
        account_id: str = "",
        log_func: Optional[Callable[[str], None]] = None,
    ):
        self.in_flight_orders: Dict[str, str] = (
            in_flight_orders if in_flight_orders is not None else {}
        )
        self.pending_position_closures: Dict[str, Any] = (
            pending_position_closures if pending_position_closures is not None else {}
        )
        self.broker = broker
        self.account_id = account_id or ""
        self._log = log_func

    def _write(self, message: str) -> None:
        if self._log:
            self._log(f"[GUARD] {message}")

    def blocked_figis(self) -> Set[str]:
        blocked: Set[str] = set()
        for key in (self.in_flight_orders or {}).keys():
            figi = normalize_figi(key)
            if figi:
                blocked.add(figi)
        for meta in (self.pending_position_closures or {}).values():
            figi = normalize_figi((meta or {}).get("figi"))
            if figi:
                blocked.add(figi)
        return blocked

    def is_blocked(self, figi: str) -> bool:
        key = normalize_figi(figi)
        return bool(key) and key in self.blocked_figis()

    async def has_active_broker_order(self, figi: str) -> bool:
        figi_key = normalize_figi(figi)
        if not figi_key or not self.account_id or self.broker is None:
            return False
        try:
            orders = await self.broker.get_orders(self.account_id)
        except Exception as exc:
            self._write(f"get_orders for skip: {exc}")
            return False
        for order in orders or []:
            sym = normalize_figi(order.get("symbol") or order.get("figi"))
            if sym != figi_key:
                continue
            status = str(order.get("executionReportStatus") or order.get("orderStatus") or "")
            if status in _BROKER_ORDER_ACTIVE or "NEW" in status.upper() or "PARTIAL" in status.upper():
                return True
        return False

    async def is_blocked_including_broker(self, figi: str) -> bool:
        if self.is_blocked(figi):
            return True
        return await self.has_active_broker_order(figi)

    def mark_in_flight(self, figi: str, order_id: str) -> None:
        figi_key = normalize_figi(figi)
        oid = str(order_id or "").strip()
        if figi_key and oid:
            self.in_flight_orders[figi_key] = oid

    def register_pending_close(self, order_id: str, meta: Dict[str, Any]) -> None:
        oid = str(order_id or "").strip()
        if not oid:
            return
        payload = dict(meta or {})
        figi = normalize_figi(payload.get("figi"))
        if figi:
            payload["figi"] = figi
            self.mark_in_flight(figi, oid)
        self.pending_position_closures[oid] = payload


__all__ = ["SymbolGuard", "normalize_figi"]
