"""Broker ↔ DB position sync helpers (import missing, fatal error codes)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# ByBit: ab not enough for new order / reduce-only wrong side — halt live trading.
FATAL_BYBIT_RET_CODES: frozenset[int] = frozenset({110007, 110017})


def money_to_float(value: Any) -> float:
    if isinstance(value, dict):
        if value.get("decimal") is not None:
            try:
                return float(value.get("decimal"))
            except Exception:
                return 0.0
        try:
            return float(value.get("units") or 0) + float(value.get("nano") or 0) / 1_000_000_000.0
        except Exception:
            return 0.0
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def qty_to_float(value: Any) -> float:
    return money_to_float(value)


def extract_account_position_meta(
    portfolio_positions: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Build figi/ticker → {qty signed, avg_price, mark, side} from broker portfolio rows."""
    meta: Dict[str, Dict[str, Any]] = {}
    for p in portfolio_positions or []:
        instr = str(p.get("instrument_type") or "").lower()
        if instr == "currency":
            continue
        qty = qty_to_float(p.get("quantity"))
        if abs(qty) <= 1e-12:
            continue
        side = str(p.get("side") or "").lower()
        if qty > 0 and side in {"sell", "short"}:
            qty = -abs(qty)
        elif qty < 0 and side in {"buy", "long"}:
            qty = abs(qty)
        avg = money_to_float(p.get("average_position_price"))
        mark = money_to_float(p.get("current_price"))
        if mark <= 0:
            mark = money_to_float(p.get("mark_price"))
        liq = money_to_float(p.get("liq_price") or p.get("liquidation_price"))
        row = {
            "qty": float(qty),
            "avg_price": float(avg),
            "mark_price": float(mark),
            "liq_price": float(liq),
            "side": "sell" if qty < 0 else "buy",
        }
        figi = str(p.get("figi") or "").strip().upper()
        ticker = str(p.get("ticker") or "").strip().upper()
        if figi:
            meta[figi] = row
        if ticker:
            meta[ticker] = row
    return meta


def is_synthetic_broker_order_id(order_id: Any) -> bool:
    """True for non-exchange ids like broker_import:… (position seeds)."""
    return str(order_id or "").strip().lower().startswith("broker_import:")


def synthetic_broker_import_order_id(figi: str, side: str, *, robot_id: Optional[int] = None) -> str:
    """Stable synthetic order_id for broker→DB position seeds."""
    key = str(figi or "").strip().upper()
    side_l = "buy" if str(side or "").strip().lower() in {"buy", "long"} else "sell"
    if robot_id is not None:
        return f"broker_import:{int(robot_id)}:{key}:{side_l}"
    return f"broker_import:{key}:{side_l}"


def legacy_broker_import_order_ids(figi: str, side: str, *, robot_id: Optional[int] = None) -> List[str]:
    """Current + legacy ids to look up existing seed rows."""
    key = str(figi or "").strip().upper()
    side_l = "buy" if str(side or "").strip().lower() in {"buy", "long"} else "sell"
    out: List[str] = []
    if robot_id is not None:
        out.append(f"broker_import:{int(robot_id)}:{key}:{side_l}")
    out.append(f"broker_import:{key}:{side_l}")
    # de-dupe preserve order
    seen: Set[str] = set()
    uniq: List[str] = []
    for oid in out:
        if oid not in seen:
            seen.add(oid)
            uniq.append(oid)
    return uniq


def db_open_side_keys(open_positions: Optional[Iterable[Dict[str, Any]]]) -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    for pos in open_positions or []:
        figi = str(pos.get("figi") or "").strip().upper()
        if not figi:
            continue
        is_long = str(pos.get("side") or "").lower() in {"buy", "long"}
        keys.add((figi, "long" if is_long else "short"))
    return keys


def broker_positions_missing_in_db(
    account_position_meta: Dict[str, Dict[str, Any]],
    open_positions: Optional[Iterable[Dict[str, Any]]],
    *,
    fallback_prices: Optional[Dict[str, float]] = None,
    robot_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return trade dicts to upsert for broker-only holdings (long or short)."""
    prices = fallback_prices or {}
    db_keys = db_open_side_keys(open_positions)
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for figi, meta in (account_position_meta or {}).items():
        key = str(figi or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        qty = float(meta.get("qty") or 0.0)
        if abs(qty) <= 1e-12:
            continue
        side_key = "long" if qty > 0 else "short"
        if (key, side_key) in db_keys:
            continue
        entry = float(meta.get("avg_price") or 0.0)
        if entry <= 0:
            entry = float(meta.get("mark_price") or 0.0) or float(prices.get(key) or 0.0)
        if entry <= 0:
            continue
        abs_qty = abs(qty)
        side = "buy" if qty > 0 else "sell"
        out.append(
            {
                "figi": key,
                "side": side,
                "quantity": abs_qty,
                "price": entry,
                "total_amount": abs_qty * entry,
                "entry_price": entry,
                "commission": 0.0,
                "status": "open",
                # Synthetic id — not a real exchange order; mark filled so UI/sync
                # never treat this row as a resting limit.
                "order_id": synthetic_broker_import_order_id(key, side, robot_id=robot_id),
                "filled_quantity": abs_qty,
                "avg_fill_price": entry,
                "intent_source": "broker_sync_import",
            }
        )
    return out


def is_fatal_broker_error(error: Any) -> bool:
    """True for ByBit codes that mean the account/position state is unsafe to keep trading."""
    ret = getattr(error, "ret_code", None)
    try:
        if ret is not None and int(ret) in FATAL_BYBIT_RET_CODES:
            return True
    except Exception:
        pass
    text = str(error or "")
    for code in FATAL_BYBIT_RET_CODES:
        if str(code) in text:
            return True
    return False


def configured_leverage(config: Optional[Dict[str, Any]], risk_params: Optional[Dict[str, Any]] = None) -> float:
    """Read bybit.leverage / risk.max_leverage; 0 means margin trading disabled."""
    cfg = config or {}
    risk = risk_params if risk_params is not None else (cfg.get("risk") if isinstance(cfg.get("risk"), dict) else {})
    bybit = cfg.get("bybit") if isinstance(cfg.get("bybit"), dict) else {}
    if "leverage" in bybit and bybit.get("leverage") is not None:
        try:
            return float(bybit.get("leverage"))
        except Exception:
            return 0.0
    if isinstance(risk, dict) and risk.get("max_leverage") is not None:
        try:
            return float(risk.get("max_leverage"))
        except Exception:
            return 0.0
    return 1.0


__all__ = [
    "FATAL_BYBIT_RET_CODES",
    "broker_positions_missing_in_db",
    "configured_leverage",
    "db_open_side_keys",
    "extract_account_position_meta",
    "is_fatal_broker_error",
    "is_synthetic_broker_order_id",
    "legacy_broker_import_order_ids",
    "money_to_float",
    "qty_to_float",
    "synthetic_broker_import_order_id",
]
