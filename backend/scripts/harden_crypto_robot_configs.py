#!/usr/bin/env python3
"""
Harden ByBit crypto robot configs in DB:

  - crypto_universe.min_last_price: bump weak values to floor (default 0.05; 0 stays = disabled)
  - crypto_universe.min_open_interest_usd: bump weak values to floor (default 20_000_000)
  - sync risk.max_leverage ← bybit.leverage
  - optional --no-margin: force bybit.leverage=0 and risk.max_leverage=0

  python backend/scripts/harden_crypto_robot_configs.py --dry-run
  python backend/scripts/harden_crypto_robot_configs.py --robot-id 24
  python backend/scripts/harden_crypto_robot_configs.py --no-margin
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

_repo_root = Path(__file__).resolve().parents[2]
_backend = _repo_root / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

_env_file = _repo_root / ".env"
if _env_file.is_file():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()

from app.core.config import get_settings, settings  # noqa: E402

get_settings.cache_clear()
settings = get_settings()

from app.core.database import SessionLocal  # noqa: E402
from app.modules.robots.config.migration import config_equals  # noqa: E402

DEFAULT_MIN_LAST_PRICE = 0.05
DEFAULT_MIN_OI_USD = 20_000_000.0


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def harden_crypto_robot_config(
    raw: Dict[str, Any],
    *,
    min_last_price_floor: float = DEFAULT_MIN_LAST_PRICE,
    min_oi_floor: float = DEFAULT_MIN_OI_USD,
    force_no_margin: bool = False
) -> Tuple[Dict[str, Any], List[str]]:
    """Return (new_config, change_notes). No-op for non-bybit configs."""
    cfg = copy.deepcopy(dict(raw or {}))
    notes: List[str] = []
    broker = str(cfg.get("broker_type") or "").strip().lower()
    if broker != "bybit":
        return cfg, notes

    cu = dict(cfg.get("crypto_universe") or {}) if isinstance(cfg.get("crypto_universe"), dict) else {}
    bybit = dict(cfg.get("bybit") or {}) if isinstance(cfg.get("bybit"), dict) else {}
    risk = dict(cfg.get("risk") or {}) if isinstance(cfg.get("risk"), dict) else {}

    # --- min_last_price ---
    cur_price = _as_float(cu.get("min_last_price"))
    if cur_price is None:
        cu["min_last_price"] = float(min_last_price_floor)
        notes.append(f"min_last_price: <missing> -> {min_last_price_floor}")
    elif cur_price > 0 and cur_price < float(min_last_price_floor):
        cu["min_last_price"] = float(min_last_price_floor)
        notes.append(f"min_last_price: {cur_price} -> {min_last_price_floor}")
    # cur_price == 0 -> explicit disable, keep

    # --- min_open_interest_usd ---
    cur_oi = _as_float(cu.get("min_open_interest_usd"))
    if cur_oi is None:
        cu["min_open_interest_usd"] = float(min_oi_floor)
        notes.append(f"min_open_interest_usd: <missing> -> {min_oi_floor:g}")
    elif cur_oi > 0 and cur_oi < float(min_oi_floor):
        cu["min_open_interest_usd"] = float(min_oi_floor)
        notes.append(f"min_open_interest_usd: {cur_oi:g} -> {min_oi_floor:g}")

    # --- leverage / margin ---
    if force_no_margin:
        old_lev = bybit.get("leverage")
        old_ml = risk.get("max_leverage")
        bybit["leverage"] = 0
        risk["max_leverage"] = 0
        if _as_float(old_lev) != 0.0 or _as_float(old_ml) != 0.0:
            notes.append(f"no-margin: bybit.leverage {old_lev} -> 0, risk.max_leverage -> 0")
    else:
        # Keep bybit.leverage authoritative; sync risk.max_leverage when present.
        if "leverage" in bybit and bybit.get("leverage") is not None:
            try:
                lev = float(bybit.get("leverage"))
            except Exception:
                lev = None
            if lev is not None:
                old_ml = risk.get("max_leverage")
                if _as_float(old_ml) != lev:
                    risk["max_leverage"] = lev if lev == int(lev) else lev
                    # Prefer int when whole number (schema uses int).
                    if float(lev).is_integer():
                        risk["max_leverage"] = int(lev)
                        bybit["leverage"] = int(lev)
                    notes.append(
                        f"risk.max_leverage: {old_ml} -> {risk['max_leverage']} (sync bybit.leverage)"
                    )

    # Health gate defaults (only if missing — do not overwrite user tuning).
    if risk.get("margin_mm_rate_halt") is None:
        risk["margin_mm_rate_halt"] = 0.80
        notes.append("risk.margin_mm_rate_halt: <missing> -> 0.80")
    if risk.get("liq_distance_halt") is None:
        risk["liq_distance_halt"] = 0.05
        notes.append("risk.liq_distance_halt: <missing> -> 0.05")
    if risk.get("account_refresh_fail_halt") is None:
        risk["account_refresh_fail_halt"] = 3
        notes.append("risk.account_refresh_fail_halt: <missing> -> 3")
    if risk.get("min_hold_seconds") is None:
        risk["min_hold_seconds"] = 120
        notes.append("risk.min_hold_seconds: <missing> -> 120")
    if risk.get("min_tp_move_bps") is None:
        risk["min_tp_move_bps"] = 10.0
        notes.append("risk.min_tp_move_bps: <missing> -> 10")

    cfg["crypto_universe"] = cu
    cfg["bybit"] = bybit
    cfg["risk"] = risk
    return cfg, notes


def main() -> int:
    p = argparse.ArgumentParser(description="Harden ByBit crypto robot configs")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--robot-id", type=int, default=None)
    p.add_argument("--user-id", type=int, default=None)
    p.add_argument(
        "--no-margin",
        action="store_true",
        help="Force bybit.leverage=0 and risk.max_leverage=0 (no margin trading)"
    )
    p.add_argument("--min-last-price", type=float, default=DEFAULT_MIN_LAST_PRICE)
    p.add_argument("--min-oi", type=float, default=DEFAULT_MIN_OI_USD)
    args = p.parse_args()

    db = SessionLocal()
    schema = settings.DB_SCHEMA
    try:
        clauses = [
            "type IN (1, 2)",
            "COALESCE(status, 1) != 0",
            "LOWER(COALESCE(config->>'broker_type', '')) = 'bybit'",
        ]
        params: dict = {}
        if args.robot_id is not None:
            clauses.append("id = :rid")
            params["rid"] = args.robot_id
        if args.user_id is not None:
            clauses.append("user_id = :uid")
            params["uid"] = args.user_id
        where = " AND ".join(clauses)
        rows = db.execute(
            text(f"SELECT id, type, name, config FROM robots WHERE {where} ORDER BY id"),
            params
        ).mappings().all()

        updated = 0
        for row in rows:
            rid = int(row["id"])
            name = str(row.get("name") or "")
            raw = dict(row["config"] or {})
            hardened, notes = harden_crypto_robot_config(
                raw,
                min_last_price_floor=float(args.min_last_price),
                min_oi_floor=float(args.min_oi),
                force_no_margin=bool(args.no_margin)
            )
            changed = not config_equals(raw, hardened)
            print(f"robot_id={rid} name={name!r} {'CHANGED' if changed else 'ok'}")
            for n in notes:
                print(f"  - {n}")
            if changed and not args.dry_run:
                db.execute(
                    text(f"UPDATE robots SET config = CAST(:cfg AS jsonb) WHERE id = :rid"),
                    {"cfg": json.dumps(hardened, ensure_ascii=False), "rid": rid}
                )
                updated += 1

        if not args.dry_run:
            db.commit()
        print(f"done: scanned={len(rows)} updated={updated} dry_run={args.dry_run}")
        return 0
    except Exception as ex:
        db.rollback()
        print(f"FAILED: {ex}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
