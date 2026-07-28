"""Режимы отбора бумаг (universe) для live и DMS."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

UNIVERSE_MODE_FIXED = "fixed"
UNIVERSE_MODE_AUTO = "auto"
UNIVERSE_MODE_DMS = "dms_pipeline"
UNIVERSE_MODE_TQBR = "tqbr_scan"
UNIVERSE_MODES = (UNIVERSE_MODE_FIXED, UNIVERSE_MODE_DMS, UNIVERSE_MODE_TQBR)
CRYPTO_UNIVERSE_MODES = (UNIVERSE_MODE_FIXED, UNIVERSE_MODE_AUTO)

# MOEX session EOD — never apply on ByBit/crypto.
_MOEX_EOD_FLATTEN_KEYS = ("force_close_time_msk", "force_market_flatten")


def strip_moex_eod_flatten_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Remove MOEX end-of-day flatten knobs from strategy params (ByBit must not use them)."""
    out = dict(params or {})
    for key in _MOEX_EOD_FLATTEN_KEYS:
        out.pop(key, None)
    return out


def strip_moex_eod_flatten_from_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip EOD flatten from strategy_params / signal_generation.params in a robot config."""
    cfg = dict(config or {})
    if isinstance(cfg.get("strategy_params"), dict):
        cfg["strategy_params"] = strip_moex_eod_flatten_params(cfg["strategy_params"])
    sg = cfg.get("signal_generation")
    if isinstance(sg, dict):
        sg2 = dict(sg)
        if isinstance(sg2.get("params"), dict):
            sg2["params"] = strip_moex_eod_flatten_params(sg2["params"])
        cfg["signal_generation"] = sg2
    return cfg


def is_crypto_type2_config(config: Optional[Dict[str, Any]]) -> bool:
    """Type2 Bybit / crypto trading robot config (skip MOEX v2 migration)."""
    if not isinstance(config, dict):
        return False
    broker = str(config.get("broker_type") or "").strip().lower()
    if broker == "bybit":
        return True
    if str(config.get("schema_profile") or "").strip().lower() == "type2_bybit":
        return True
    if str(config.get("market_profile") or "").strip().lower() == "crypto":
        return True
    return False


def resolve_crypto_symbols(config: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(config, dict):
        return []
    raw = config.get("allowed_symbols") or config.get("instruments") or []
    if not isinstance(raw, list):
        return []
    return sorted({str(s).strip().upper() for s in raw if str(s).strip()})


def normalize_crypto_universe_mode(config: Optional[Dict[str, Any]]) -> str:
    """Режим universe для crypto backtest/live: fixed | auto."""
    if not isinstance(config, dict):
        return UNIVERSE_MODE_AUTO
    raw = str(config.get("universe_mode") or "").strip().lower()
    if raw in CRYPTO_UNIVERSE_MODES:
        return raw
    symbols = resolve_crypto_symbols(config)
    cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
    enabled = bool(cu.get("enabled", True))
    if symbols:
        return UNIVERSE_MODE_FIXED
    if enabled:
        return UNIVERSE_MODE_AUTO
    return UNIVERSE_MODE_FIXED


def normalize_universe_mode(config: Optional[Dict[str, Any]]) -> str:
    if not isinstance(config, dict):
        return UNIVERSE_MODE_DMS
    try:
        from app.modules.robots.config.migration import ensure_config_v2

        config = ensure_config_v2(config)
    except Exception:
        pass
    raw = str(config.get("universe_mode") or "").strip().lower()
    if raw in UNIVERSE_MODES:
        return raw
    fixed = resolve_fixed_tickers(config, infer_mode=False)
    if fixed:
        return UNIVERSE_MODE_FIXED
    return UNIVERSE_MODE_DMS


def resolve_fixed_tickers(config: Optional[Dict[str, Any]], *, infer_mode: bool = True) -> List[str]:
    if not isinstance(config, dict):
        return []
    fixed = config.get("fixed_tickers")
    if isinstance(fixed, list):
        out = [str(x).strip().upper() for x in fixed if str(x).strip()]
        if out:
            return sorted(set(out))

    instrument_map = config.get("instrument_map") if isinstance(config.get("instrument_map"), dict) else {}
    figi_by_ticker = instrument_map.get("figi_by_ticker") if isinstance(instrument_map, dict) else None
    if isinstance(figi_by_ticker, dict) and figi_by_ticker:
        tickers = [str(t).strip().upper() for t in figi_by_ticker.keys() if str(t).strip()]
        if tickers and (not infer_mode or normalize_universe_mode(config) == UNIVERSE_MODE_FIXED):
            return sorted(set(tickers))

    sp = config.get("strategy_params") if isinstance(config.get("strategy_params"), dict) else {}
    figis = sp.get("figis") if isinstance(sp, dict) else None
    if isinstance(figis, list) and figis:
        ticker_by_figi = instrument_map.get("ticker_by_figi") if isinstance(instrument_map, dict) else None
        if isinstance(ticker_by_figi, dict):
            tickers = []
            for fg in figis:
                tk = ticker_by_figi.get(str(fg).upper()) or ticker_by_figi.get(str(fg))
                if tk:
                    tickers.append(str(tk).strip().upper())
            if tickers:
                return sorted(set(tickers))
        non_bbg = [str(x).strip().upper() for x in figis if str(x).strip() and not str(x).upper().startswith("BBG")]
        if non_bbg:
            return sorted(set(non_bbg))
    return []


def universe_whitelist_tickers(config: Optional[Dict[str, Any]]) -> Optional[Set[str]]:
    """
    Whitelist для pre-filter в DMS / П2.
    None — не ограничивать snapshot.
    """
    if not isinstance(config, dict):
        return None
    try:
        from app.modules.robots.config.migration import (
            ensure_config_v2,
            paper_selection_from_config,
        )

        cfg = ensure_config_v2(config)
        ps = paper_selection_from_config(cfg)
        if str(ps.input) == "candidate_pool":
            pool = cfg.get("candidate_pool")
            if isinstance(pool, dict):
                tickers = [
                    str(x).strip().upper()
                    for x in (pool.get("tickers") or [])
                    if str(x).strip()
                ]
                if tickers:
                    return set(tickers)
        if str(ps.input) == "fixed":
            fixed = resolve_fixed_tickers(cfg, infer_mode=False)
            return set(fixed) if fixed else set()
    except Exception:
        pass
    if normalize_universe_mode(config) != UNIVERSE_MODE_FIXED:
        return None
    tickers = resolve_fixed_tickers(config)
    return set(tickers) if tickers else set()


def universe_uses_pipeline(config: Optional[Dict[str, Any]]) -> bool:
    return normalize_universe_mode(config) == UNIVERSE_MODE_DMS


def universe_min_tradable_row(row: Dict[str, Any]) -> bool:
    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return False
    status = str(row.get("security_status") or "").strip().upper()
    trading = str(row.get("trading_status") or "").strip().upper()
    if status and status not in {"A", "ACTIVE"}:
        return False
    if trading and trading not in {"T", "TRADING", "NORMAL_TRADING"}:
        return False
    return True


def universe_pipeline_filters(
    config: Optional[Dict[str, Any]],
    filters: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Фильтры П2 (paper_selection) при config v2; иначе legacy pipeline."""
    if not isinstance(config, dict):
        return []
    try:
        from app.modules.robots.config.migration import (
            effective_pipeline_from_config,
            ensure_config_v2,
        )

        cfg = ensure_config_v2(config)
        pl = effective_pipeline_from_config(cfg)
        pf = list(pl.get("filters") or [])
        if pf:
            return [dict(f) for f in pf if isinstance(f, dict)]
    except Exception:
        pass
    if not universe_uses_pipeline(config):
        return []
    return [dict(f) for f in (filters or []) if isinstance(f, dict)]


def universe_filter_snapshot_row(row: Dict[str, Any], config: Optional[Dict[str, Any]]) -> bool:
    """Строка snapshot участвует в отборе universe (history-backtest / DMS)."""
    mode = normalize_universe_mode(config)
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        return False
    if mode == UNIVERSE_MODE_FIXED:
        fixed = set(resolve_fixed_tickers(config))
        return ticker in fixed if fixed else False
    if mode == UNIVERSE_MODE_TQBR:
        return universe_min_tradable_row({**row, "ticker": ticker})
    return True
