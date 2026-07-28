"""Preloaded candles for history backtest — данные уже в памяти после loading_candles."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.contracts import Candle
from app.modules.robots.trading.data_provider.historical import HistoricalDataProvider


def _candle_time_key(candle: Dict[str, Any]) -> str:
    t = candle.get("time")
    if isinstance(t, str):
        return t
    return str(t or "")


def _tinvest_dict_to_candle(raw: Dict[str, Any], *, secid: str, interval: str) -> Candle:
    return Candle.from_tinvest_dict(raw, interval=interval, figi=secid)


class PreloadedHistoricalDataProvider(HistoricalDataProvider):
    """HistoricalDataProvider + in-memory intraday series (T-Invest dict format)."""

    def __init__(
        self,
        db,
        *,
        board: str = "TQBR",
        candles_by_ticker: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        interval_label: str = "M5",
    ):
        super().__init__(db, board=board)
        self._candles = {str(k).upper(): list(v or []) for k, v in (candles_by_ticker or {}).items()}
        self._interval_label = interval_label
        self._by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for tk, series in self._candles.items():
            for c in sorted(series, key=_candle_time_key):
                iso = _candle_time_key(c)
                if len(iso) < 10:
                    continue
                day = iso[:10]
                self._by_day.setdefault(day, {}).setdefault(tk, []).append(c)

    async def get_intraday_candles(self, secid: str, day: date, interval: str) -> List[Candle]:
        tk = str(secid).upper()
        day_key = day.isoformat()
        rows = (self._by_day.get(day_key) or {}).get(tk) or []
        norm = interval or self._interval_label
        return [_tinvest_dict_to_candle(r, secid=tk, interval=norm) for r in rows]

    def candles_for_day(self, day: date) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self._by_day.get(day.isoformat()) or {})


__all__ = ["PreloadedHistoricalDataProvider"]
