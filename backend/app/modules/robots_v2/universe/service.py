"""Universe Service orchestrator (greenfield Stage 1)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.dms.service import dms_service
from app.modules.robots_v2.config.v4_schema import UniverseConfig
from app.modules.robots_v2.universe import presets
from app.modules.robots_v2.universe.index_provider import (
    list_index_metadata,
    resolve_crypto_index_constituents,
    resolve_moex_index_constituents,
)
from app.modules.robots_v2.universe.schemas import (
    InstrumentRef,
    PreviewAsset,
    RejectedInstrument,
    ResolvedUniverse,
    ResolvedUniverseStats,
    UniversePreview,
    ValidateTickersResponse,
)
from app.modules.robots_v2.universe.token_context import board_for_instrument_type, load_token_context


def _normalize_tickers(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or []:
        t = str(raw or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _price_in_bounds(price: float | None, lo: float | None, hi: float | None) -> bool:
    if price is None or price <= 0:
        return False
    if lo is not None and price < lo:
        return False
    if hi is not None and price > hi:
        return False
    return True


def _split_v4_price_filters(dms_filters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dms: list[dict[str, Any]] = []
    price_filters: list[dict[str, Any]] = []
    for f in dms_filters:
        if str(f.get("type") or "").lower() == "v4_price":
            price_filters.append(f)
        else:
            dms.append(f)
    return dms, price_filters


def _apply_price_filters(
    rows: list[dict[str, Any]],
    price_filters: list[dict[str, Any]],
    preset: str | None,
    custom_filters: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
    lo, hi = presets.moex_price_bounds(preset, custom_filters)  # type: ignore[arg-type]
    for f in price_filters:
        op = str(f.get("op") or ">")
        val = float(f.get("value") or 0)
        if op == ">":
            lo = val if lo is None else max(lo, val)
        elif op == "<":
            hi = val if hi is None else min(hi, val)
    accepted: list[dict[str, Any]] = []
    rejected: list[RejectedInstrument] = []
    for row in rows:
        price = float(row.get("last_price") or 0)
        if _price_in_bounds(price, lo, hi):
            accepted.append(row)
        else:
            rejected.append(RejectedInstrument(
                ticker=str(row.get("ticker") or "").upper(),
                stage="snapshot",
                code="FILTER_PRICE",
                message=f"Price {price:.2f} outside bounds",
            ))
    return accepted, rejected


def _rank_and_cap(
    rows: list[dict[str, Any]],
    *,
    max_assets: int,
    excluded: set[str],
) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
    ranked = sorted(rows, key=lambda r: float(r.get("value_today") or r.get("volume24h") or 0), reverse=True)
    accepted: list[dict[str, Any]] = []
    rejected: list[RejectedInstrument] = []
    for row in ranked:
        ticker = str(row.get("ticker") or "").upper()
        if ticker in excluded:
            rejected.append(RejectedInstrument(
                ticker=ticker, stage="excluded", code="USER_EXCLUDED", message="Excluded by user",
            ))
            continue
        if len(accepted) < max_assets:
            accepted.append(row)
        else:
            rejected.append(RejectedInstrument(
                ticker=ticker, stage="cap", code="CAP_MAX_ASSETS", message="Exceeded maxAssets",
            ))
    return accepted, rejected


def _paginate_assets(assets: list[PreviewAsset], page: int, page_size: int) -> list[PreviewAsset]:
    start = (page - 1) * page_size
    return assets[start : start + page_size]


def _cache_key(*, universe: dict[str, Any], market: str, token_id: int) -> str:
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    raw = json.dumps({"universe": universe, "market": market, "tokenId": token_id, "bucket": bucket}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class UniverseService:
    schema = settings.DB_SCHEMA

    async def preview(
        self,
        db: Session,
        user_id: int,
        *,
        token_id: int,
        instrument_type: str,
        universe_raw: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> UniversePreview:
        universe = UniverseConfig.model_validate(universe_raw)
        ctx = load_token_context(db, user_id=user_id, token_id=token_id, instrument_type=instrument_type, schema=self.schema)
        as_of = datetime.now(timezone.utc)
        excluded = set(_normalize_tickers(universe.excluded))

        if universe.mode == "fixed":
            assets, rejected = await self._preview_fixed(
                db, ctx, universe, instrument_type, excluded,
            )
        elif universe.mode == "index":
            assets, rejected = await self._preview_index(
                db, ctx, universe, instrument_type, excluded,
            )
        elif universe.mode == "screener":
            assets, rejected = await self._preview_screener(
                db, ctx, universe, instrument_type, excluded,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported universe mode: {universe.mode}")

        preview_assets = [
            PreviewAsset(
                ticker=a["ticker"],
                name=a.get("name") or a["ticker"],
                price=float(a.get("price") or 0),
                volume24h=float(a.get("volume24h") or 0),
                atr=float(a.get("atr") or 0),
                included=a["ticker"] not in excluded,
            )
            for a in assets
        ]
        total = len(preview_assets)
        page_assets = _paginate_assets(preview_assets, page, page_size)
        return UniversePreview(
            asOf=as_of,
            total=total,
            page=page,
            pageSize=page_size,
            assets=page_assets,
            rejectedSample=rejected[:10],
        )

    async def resolve(
        self,
        db: Session,
        user_id: int,
        *,
        token_id: int,
        instrument_type: str,
        universe_raw: dict[str, Any],
        robot_id: int | None = None,
    ) -> ResolvedUniverse:
        preview = await self.preview(
            db, user_id,
            token_id=token_id,
            instrument_type=instrument_type,
            universe_raw=universe_raw,
            page=1,
            page_size=10_000,
        )
        instruments = [
            InstrumentRef(
                ticker=a.ticker,
                name=a.name,
                instrumentType=instrument_type,  # type: ignore[arg-type]
            )
            for a in preview.assets if a.included
        ]
        stats = ResolvedUniverseStats(
            candidateCount=preview.total,
            afterHistorical=preview.total,
            afterSnapshot=preview.total,
            finalCount=len(instruments),
        )
        return ResolvedUniverse(
            robotId=robot_id,
            mode=universe_raw.get("mode", "fixed"),
            asOf=preview.as_of,
            instruments=instruments,
            rejected=preview.rejected_sample,
            stats=stats,
            cacheKey=_cache_key(universe=universe_raw, market=load_token_context(
                db, user_id=user_id, token_id=token_id, instrument_type=instrument_type, schema=self.schema,
            ).market, token_id=token_id),
        )

    async def validate_tickers(
        self,
        db: Session,
        user_id: int,
        *,
        token_id: int,
        instrument_type: str,
        tickers: list[str],
    ) -> ValidateTickersResponse:
        normalized = _normalize_tickers(tickers)
        ctx = load_token_context(db, user_id=user_id, token_id=token_id, instrument_type=instrument_type, schema=self.schema)
        valid: list[str] = []
        invalid: list[RejectedInstrument] = []
        if ctx.market == "crypto":
            from app.modules.robots.crypto_universe import fetch_bybit_tickers
            if not ctx.api_key:
                raise HTTPException(status_code=400, detail="Bybit token missing")
            live = await fetch_bybit_tickers(
                api_key=ctx.api_key,
                api_secret=ctx.api_secret or "",
                testnet=ctx.testnet,
                category="linear",
            )
            known = {str(r.get("symbol") or "").upper() for r in live}
            for t in normalized:
                if t in known:
                    valid.append(t)
                else:
                    invalid.append(RejectedInstrument(
                        ticker=t, stage="broker", code="NOT_FOUND", message="Symbol not found at broker",
                    ))
        else:
            board = board_for_instrument_type(instrument_type)
            result = await dms_service.preview_pipeline_setup(
                db=db,
                user_id=user_id,
                board=board,
                filters=[{"type": "security_status", "eq": "A"}],
                mode="ALL",
                universe_mode="fixed",
                fixed_tickers=normalized,
                warmup_candles=False,
            )
            accepted = {str(i.get("ticker") or "").upper() for i in (result.get("sample") or []) if i.get("result") == "ACCEPT"}
            for t in normalized:
                if t in accepted:
                    valid.append(t)
                else:
                    invalid.append(RejectedInstrument(
                        ticker=t, stage="catalog", code="NOT_TRADABLE", message="Ticker not tradable on board",
                    ))
        return ValidateTickersResponse(valid=valid, invalid=invalid)

    async def list_indices(self, db: Session, user_id: int, *, market: str) -> list[dict[str, Any]]:
        return await list_index_metadata(db, user_id, market=market, schema=self.schema)

    async def _preview_fixed(
        self,
        db: Session,
        ctx: Any,
        universe: UniverseConfig,
        instrument_type: str,
        excluded: set[str],
    ) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
        tickers = _normalize_tickers(universe.fixed_list)
        if ctx.market == "crypto":
            validation = await self.validate_tickers(
                db, ctx.user_id, token_id=ctx.token_id, instrument_type=instrument_type, tickers=tickers,
            )
            rows = [{"ticker": t, "price": 0.0, "volume24h": 0.0, "atr": 0.0} for t in validation.valid]
            return _rank_and_cap(rows, max_assets=universe.max_assets, excluded=excluded)
        board = board_for_instrument_type(instrument_type)
        result = await dms_service.preview_pipeline_setup(
            db=db,
            user_id=ctx.user_id,
            board=board,
            filters=[{"type": "security_status", "eq": "A"}, {"type": "trading_status", "eq": "T"}],
            mode="ALL",
            universe_mode="fixed",
            fixed_tickers=tickers,
            warmup_candles=False,
        )
        rows = []
        rejected: list[RejectedInstrument] = []
        for item in result.get("sample") or []:
            ticker = str(item.get("ticker") or "").upper()
            if item.get("result") == "ACCEPT":
                rows.append({
                    "ticker": ticker,
                    "last_price": item.get("last_price"),
                    "value_today": item.get("value_today"),
                    "volume24h": item.get("value_today"),
                    "atr": item.get("atr_percent") or 0,
                })
            else:
                rejected.append(RejectedInstrument(
                    ticker=ticker,
                    stage="broker",
                    code="NOT_TRADABLE",
                    message=str(item.get("reason") or "Not tradable"),
                ))
        accepted, cap_rejected = _rank_and_cap(rows, max_assets=universe.max_assets, excluded=excluded)
        rejected.extend(cap_rejected)
        assets = [{
            "ticker": r["ticker"],
            "name": r["ticker"],
            "price": float(r.get("last_price") or 0),
            "volume24h": float(r.get("volume24h") or 0),
            "atr": float(r.get("atr") or 0),
        } for r in accepted]
        return assets, rejected

    async def _preview_index(
        self,
        db: Session,
        ctx: Any,
        universe: UniverseConfig,
        instrument_type: str,
        excluded: set[str],
    ) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
        code = str(universe.index or "").strip().upper()
        if not code:
            raise HTTPException(status_code=422, detail="universe.index is required")
        if ctx.market == "crypto":
            constituents = await resolve_crypto_index_constituents(
                db, ctx.user_id, index_code=code, token_id=ctx.token_id,
            )
        else:
            constituents = await resolve_moex_index_constituents(db, index_code=code, schema=self.schema)
        if not constituents:
            raise HTTPException(status_code=502, detail=f"Index {code} returned no constituents")
        fixed = UniverseConfig(
            mode="fixed",
            fixedList=constituents,
            excluded=list(excluded),
            maxAssets=universe.max_assets,
            exitOnDrop=universe.exit_on_drop,
        )
        return await self._preview_fixed(db, ctx, fixed, instrument_type, excluded)

    async def _preview_screener(
        self,
        db: Session,
        ctx: Any,
        universe: UniverseConfig,
        instrument_type: str,
        excluded: set[str],
    ) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
        screener = universe.screener
        if screener is None:
            raise HTTPException(status_code=422, detail="universe.screener is required")
        preset = screener.preset
        custom = screener.filters or None

        if ctx.market == "crypto":
            return await self._preview_crypto_screener(db, ctx, universe, preset, custom, excluded)
        return await self._preview_moex_screener(
            db, ctx, universe, instrument_type, preset, custom, screener.filter_mode, excluded,
        )

    async def _preview_moex_screener(
        self,
        db: Session,
        ctx: Any,
        universe: UniverseConfig,
        instrument_type: str,
        preset: str | None,
        custom: list[dict[str, Any]] | None,
        filter_mode: str,
        excluded: set[str],
    ) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
        raw_filters = presets.resolve_moex_dms_filters(preset=preset, custom_filters=custom)  # type: ignore[arg-type]
        dms_filters, price_filters = _split_v4_price_filters(raw_filters)
        board = board_for_instrument_type(instrument_type)
        mode = "ANY" if filter_mode == "any" else "ALL"
        result = await dms_service.preview_pipeline_setup(
            db=db,
            user_id=ctx.user_id,
            board=board,
            filters=dms_filters,
            mode=mode,
            universe_mode="tqbr_scan",
            fixed_tickers=[],
            warmup_candles=True,
        )
        rows: list[dict[str, Any]] = []
        rejected: list[RejectedInstrument] = []
        for item in result.get("sample") or []:
            ticker = str(item.get("ticker") or "").upper()
            if item.get("result") == "ACCEPT":
                rows.append({
                    "ticker": ticker,
                    "last_price": item.get("last_price"),
                    "value_today": item.get("value_today"),
                    "volume24h": item.get("value_today"),
                    "atr": item.get("atr_percent") or 0,
                })
            elif len(rejected) < 50:
                rejected.append(RejectedInstrument(
                    ticker=ticker,
                    stage="snapshot",
                    code="FILTER_REJECT",
                    message=str(item.get("reason") or "Filter rejected"),
                ))
        if price_filters or preset:
            rows, price_rejected = _apply_price_filters(rows, price_filters, preset, custom)
            rejected.extend(price_rejected)
        accepted, cap_rejected = _rank_and_cap(rows, max_assets=universe.max_assets, excluded=excluded)
        rejected.extend(cap_rejected)
        assets = [{
            "ticker": r["ticker"],
            "name": r["ticker"],
            "price": float(r.get("last_price") or 0),
            "volume24h": float(r.get("volume24h") or 0),
            "atr": float(r.get("atr") or 0),
        } for r in accepted]
        return assets, rejected

    async def _preview_crypto_screener(
        self,
        db: Session,
        ctx: Any,
        universe: UniverseConfig,
        preset: str | None,
        custom: list[dict[str, Any]] | None,
        excluded: set[str],
    ) -> tuple[list[dict[str, Any]], list[RejectedInstrument]]:
        from app.modules.robots.crypto_universe import (
            _resolve_filters,
            fetch_bybit_tickers,
            screen_bybit_universe_live,
        )
        from app.modules.bybit.http_client import BybitHttpClient

        if not ctx.api_key:
            raise HTTPException(status_code=400, detail="Bybit API token required")

        filter_kwargs = presets.resolve_crypto_filters(preset=preset, custom_filters=custom)  # type: ignore[arg-type]
        config = {
            "crypto_universe": {
                "min_volume_24h_usd": filter_kwargs.get("min_volume_24h_usd", 5_000_000),
                "max_spread_pct": filter_kwargs.get("max_spread_pct", 0.15),
                "min_atr_percent": filter_kwargs.get("min_atr_percent"),
                "max_atr_percent": filter_kwargs.get("max_atr_percent"),
                "min_last_price": filter_kwargs.get("min_last_price", 0.05),
                "category": "linear",
                "lookback_days": 20,
            },
            "bybit": {"instrument_category": "linear", "testnet": ctx.testnet},
        }
        filters = _resolve_filters(config)
        tickers = await fetch_bybit_tickers(
            api_key=ctx.api_key,
            api_secret=ctx.api_secret or "",
            testnet=ctx.testnet,
            category=filters.category,
        )
        client = BybitHttpClient(testnet=ctx.testnet, api_key=ctx.api_key, api_secret=ctx.api_secret or "")
        try:
            accepted_rows, rejected_rows = await screen_bybit_universe_live(
                db,
                client=client,
                tickers=tickers,
                filters=filters,
                user_id=ctx.user_id,
            )
        finally:
            await client.close()

        rows = [{
            "ticker": str(r.symbol).upper(),
            "last_price": r.lastPrice,
            "volume24h": r.turnover24h,
            "atr": r.atr_percent or 0,
        } for r in accepted_rows]
        rejected = [
            RejectedInstrument(
                ticker=str(r.symbol).upper(),
                stage="snapshot",
                code="FILTER_REJECT",
                message=str(r.reject_reason or "Rejected"),
            )
            for r in rejected_rows[:50]
        ]
        accepted, cap_rejected = _rank_and_cap(rows, max_assets=universe.max_assets, excluded=excluded)
        rejected.extend(cap_rejected)
        assets = [{
            "ticker": r["ticker"],
            "name": r["ticker"],
            "price": float(r.get("last_price") or 0),
            "volume24h": float(r.get("volume24h") or 0),
            "atr": float(r.get("atr") or 0),
        } for r in accepted]
        return assets, rejected


universe_service = UniverseService()
