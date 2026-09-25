"""History provider: GIN → OsEngine MCP (OsData) → Data/ files → candles_cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.history_files import FileHistoryProvider
from app.modules.osengine.intervals_map import cache_interval_to_osengine_tf, normalize_cache_interval
from app.modules.osengine.mcp_client import OsEngineMcpClient, OsEngineMcpError
from app.modules.osengine.types import InstrumentKey, TimeRange

logger = logging.getLogger(__name__)

DownloadProgressCallback = Callable[[float], None]

_DONE_STATUSES = frozenset({"Load", "load"})
_ERROR_STATUSES = frozenset({"Error", "error"})


def _iso_date(d: date) -> str:
    return d.isoformat()


def _parse_date_value(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw).strip()
    if not s:
        return None
    # "2024-01-15T00:00:00" / "2024-01-15"
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _normalize_set_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "GinHistory"
    if n.lower().startswith("set_"):
        return n[4:] or "GinHistory"
    return n


def _set_names_equal(a: str, b: str) -> bool:
    return _normalize_set_name(a).lower() == _normalize_set_name(b).lower()


def _union_gaps(gaps: Sequence[TimeRange]) -> Optional[TimeRange]:
    if not gaps:
        return None
    norms = [g.normalized() for g in gaps if g.normalized().start < g.normalized().end]
    if not norms:
        return None
    return TimeRange(
        start=min(g.start for g in norms),
        end=max(g.end for g in norms),
    )


def _security_names_from_payload(payload: Any) -> List[str]:
    names: List[str] = []
    if isinstance(payload, dict):
        items = payload.get("securities") or payload.get("Securities") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    for item in items:
        if isinstance(item, str):
            names.append(item.strip().upper())
        elif isinstance(item, dict):
            n = item.get("name") or item.get("Name") or item.get("security") or ""
            if n:
                names.append(str(n).strip().upper())
    return names


class McpHistoryProvider:
    """
    Pull-модель для бэктеста:
    1) по gaps заказать OsData через MCP;
    2) дождаться Load (или timeout);
    3) импортировать файлы через FileHistoryProvider.
    """

    def __init__(
        self,
        *,
        mcp: Optional[OsEngineMcpClient] = None,
        files: Optional[FileHistoryProvider] = None,
        set_name: Optional[str] = None,
        source: Optional[str] = None,
        source_name: Optional[str] = None,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._mcp = mcp
        self._owns_mcp = mcp is None
        self._files = files or FileHistoryProvider()
        self._set_name = _normalize_set_name(set_name or settings.OSENGINE_MCP_SET_NAME)
        self._source = (source or settings.OSENGINE_MCP_SOURCE or "TInvest").strip()
        self._source_name = (source_name or settings.OSENGINE_MCP_SOURCE_NAME or self._source).strip()
        self._poll_interval = float(
            poll_interval
            if poll_interval is not None
            else settings.OSENGINE_MCP_POLL_INTERVAL_SECONDS
        )
        self._timeout = float(
            timeout if timeout is not None else settings.OSENGINE_MCP_TIMEOUT_SECONDS
        )

    def _client(self) -> OsEngineMcpClient:
        if self._mcp is None:
            url = (settings.OSENGINE_MCP_URL or "").strip()
            self._mcp = OsEngineMcpClient(
                base_url=url,
                api_key=settings.OSENGINE_MCP_API_KEY,
                timeout=max(30.0, min(self._timeout, 120.0)),
            )
        return self._mcp

    async def fetch_candle_gaps(
        self,
        db: Session,
        *,
        instrument: InstrumentKey,
        interval: str,
        gaps: List[TimeRange],
        progress_callback: Optional[DownloadProgressCallback] = None,
    ) -> int:
        if not gaps:
            return 0

        cache_iv = normalize_cache_interval(interval)
        tf = cache_interval_to_osengine_tf(cache_iv)
        window = _union_gaps(gaps)
        if tf is None or window is None:
            logger.warning(
                "osengine mcp history: skip unsupported interval=%s gaps=%s",
                interval,
                len(gaps),
            )
            return await self._files.fetch_candle_gaps(
                db, instrument=instrument, interval=interval, gaps=gaps
            )

        try:
            await self._ensure_download(
                instrument=instrument,
                timeframe=tf,
                window=window,
                progress_callback=progress_callback,
            )
        except OsEngineMcpError as exc:
            logger.warning(
                "osengine mcp ensure failed ticker=%s tf=%s window=%s..%s: %s",
                instrument.cache_id,
                tf,
                window.start,
                window.end,
                exc,
            )
        except Exception:
            logger.exception(
                "osengine mcp ensure crashed ticker=%s tf=%s",
                instrument.cache_id,
                tf,
            )

        return await self._files.fetch_candle_gaps(
            db, instrument=instrument, interval=interval, gaps=gaps
        )

    async def _ensure_download(
        self,
        *,
        instrument: InstrumentKey,
        timeframe: str,
        window: TimeRange,
        progress_callback: Optional[DownloadProgressCallback] = None,
    ) -> None:
        client = self._client()
        set_name = self._set_name
        ticker = instrument.normalized().ticker

        # OsData date_to is typically inclusive end-of-day; our TimeRange end is exclusive.
        date_from = window.start
        date_to = window.end - timedelta(days=1) if window.end > window.start else window.start
        if date_to < date_from:
            date_to = date_from

        sets = await client.data_get_sets()
        exists = any(_set_names_equal(str(s.get("name") or ""), set_name) for s in sets)

        if not exists:
            logger.info(
                "osengine mcp create set=%s source=%s/%s tf=%s %s..%s",
                set_name,
                self._source,
                self._source_name,
                timeframe,
                date_from,
                date_to,
            )
            await client.data_create_set(
                name=set_name,
                source=self._source,
                source_name=self._source_name,
                timeframes=[timeframe],
                date_from=_iso_date(date_from),
                date_to=_iso_date(date_to),
            )
        else:
            await self._expand_set_window(
                client,
                set_name=set_name,
                timeframe=timeframe,
                date_from=date_from,
                date_to=date_to,
            )

        await self._ensure_security(client, set_name=set_name, ticker=ticker)
        await client.data_set_on(name=set_name)
        await self._wait_loaded(
            client,
            set_name=set_name,
            security=ticker,
            timeframe=timeframe,
            progress_callback=progress_callback,
        )

    async def _expand_set_window(
        self,
        client: OsEngineMcpClient,
        *,
        set_name: str,
        timeframe: str,
        date_from: date,
        date_to: date,
    ) -> None:
        # Best-effort: merge requested window into set settings.
        # If get settings fails, still try set with requested dates.
        cur_from, cur_to = date_from, date_to
        timeframes = [timeframe]
        try:
            # reuse get via settings tool if available through call_tool
            raw = await client.call_tool("data_set_settings_get", {"name": set_name})
            if isinstance(raw, dict):
                parsed_from = _parse_date_value(raw.get("date_from"))
                parsed_to = _parse_date_value(raw.get("date_to"))
                if parsed_from:
                    cur_from = min(cur_from, parsed_from)
                if parsed_to:
                    cur_to = max(cur_to, parsed_to)
                tfs = raw.get("timeframes") or []
                if isinstance(tfs, list):
                    merged = {str(x) for x in tfs if x}
                    merged.add(timeframe)
                    timeframes = sorted(merged)
        except OsEngineMcpError as exc:
            logger.debug("osengine mcp settings get skipped: %s", exc)

        await client.data_set_settings_set(
            name=set_name,
            settings={
                "date_from": _iso_date(cur_from),
                "date_to": _iso_date(cur_to),
                "timeframes": timeframes,
            },
        )

    async def _ensure_security(
        self,
        client: OsEngineMcpClient,
        *,
        set_name: str,
        ticker: str,
    ) -> None:
        try:
            payload = await client.data_set_securities_get(name=set_name)
            existing = _security_names_from_payload(payload)
            if ticker.upper() in existing:
                return
        except OsEngineMcpError as exc:
            logger.debug("osengine mcp securities get skipped: %s", exc)

        await client.data_set_securities_add(
            name=set_name,
            securities=[{"name": ticker}],
        )

    async def _wait_loaded(
        self,
        client: OsEngineMcpClient,
        *,
        set_name: str,
        security: str,
        timeframe: str,
        progress_callback: Optional[DownloadProgressCallback] = None,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + self._timeout
        last: Dict[str, Any] = {}
        last_reported = -1
        while True:
            try:
                last = await client.data_get_security_status(
                    name=set_name,
                    security=security,
                    timeframe=timeframe,
                )
            except OsEngineMcpError:
                # fallback to set-level status
                last = await client.data_get_set_status(name=set_name)

            status = str(last.get("status") or "")
            percent = last.get("percent_load")
            try:
                pct = float(percent) if percent is not None else -1.0
            except (TypeError, ValueError):
                pct = -1.0

            if progress_callback and pct >= 0:
                report = int(min(99.0, max(0.0, pct)))
                if report != last_reported:
                    last_reported = report
                    try:
                        progress_callback(float(report))
                    except Exception:
                        pass

            if status in _ERROR_STATUSES:
                raise OsEngineMcpError(
                    f"OsData load error set={set_name} security={security} tf={timeframe}: {last}"
                )
            if status in _DONE_STATUSES or pct >= 100.0:
                if progress_callback:
                    try:
                        progress_callback(100.0)
                    except Exception:
                        pass
                logger.info(
                    "osengine mcp load done set=%s security=%s tf=%s status=%s pct=%s",
                    set_name,
                    security,
                    timeframe,
                    status,
                    pct,
                )
                return

            if asyncio.get_running_loop().time() >= deadline:
                logger.warning(
                    "osengine mcp load timeout set=%s security=%s tf=%s last=%s",
                    set_name,
                    security,
                    timeframe,
                    last,
                )
                return

            await asyncio.sleep(self._poll_interval)


def build_default_mcp_history_provider() -> McpHistoryProvider:
    return McpHistoryProvider()


__all__ = ["McpHistoryProvider", "build_default_mcp_history_provider"]
