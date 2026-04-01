"""
Сервис автоподбора инструментов для торговых стратегий.

Фильтрует акции по объёму торгов за последние 7 дней,
исключает низколиквидные (< 1 млн руб/день),
возвращает топ-20.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from app.core.logging_config import get_logger
from app.modules.tinvest.facade import TInvestFacade

logger = get_logger(__name__)

MIN_DAILY_VOLUME_RUB = 1_000_000
TOP_N = 20
LOOKBACK_DAYS = 7


class InstrumentSelector:
    """
    Подбирает инструменты для торговли:
    - только акции
    - топ-20 по среднему объёму за 7 дней
    - исключение низколиквидных (< 1 млн руб/день)
    """

    def __init__(self, token: str):
        self._facade = TInvestFacade(token)

    async def select_instruments(
            self,
            top_n: int = TOP_N,
            min_daily_volume: float = MIN_DAILY_VOLUME_RUB,
            lookback_days: int = LOOKBACK_DAYS,
    ) -> List[Dict[str, Any]]:
        """
        Возвращает список инструментов, отсортированных по объёму.

        Args:
            top_n: Количество инструментов в результате.
            min_daily_volume: Минимальный средний объём (руб/день).
            lookback_days: За сколько дней считать объём.

        Returns:
            Список словарей с figi, ticker, name, avg_volume_rub.
        """
        logger.info("Selecting instruments: top_n=%s, min_vol=%s, days=%s", top_n, min_daily_volume, lookback_days)

        shares = await self._facade.instruments.get_shares()
        logger.info("Total shares from API: %s", len(shares))

        rub_shares = [
            s for s in shares
            if s.get("currency", "").lower() == "rub"
            and s.get("apiTradeAvailableFlag", False)
            and s.get("buyAvailableFlag", False)
            and s.get("sellAvailableFlag", False)
        ]
        logger.info("RUB tradeable shares: %s", len(rub_shares))

        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=lookback_days)

        scored: List[Dict[str, Any]] = []
        for share in rub_shares:
            figi = share.get("figi")
            if not figi:
                continue
            try:
                candles = await self._facade.get_candles(
                    figi=figi,
                    from_date=from_date,
                    to_date=to_date,
                    interval="CANDLE_INTERVAL_DAY",
                )
                if not candles:
                    continue
                total_volume = sum(self._candle_volume_rub(c) for c in candles)
                avg_volume = total_volume / max(len(candles), 1)
                if avg_volume < min_daily_volume:
                    continue
                scored.append({
                    "figi": figi,
                    "ticker": share.get("ticker", ""),
                    "name": share.get("name", ""),
                    "avg_volume_rub": round(avg_volume, 2),
                })
            except Exception as exc:
                logger.debug("Skipping %s: %s", figi, exc)

        scored.sort(key=lambda x: x["avg_volume_rub"], reverse=True)
        result = scored[:top_n]
        logger.info("Selected %s instruments", len(result))
        return result

    @staticmethod
    def _candle_volume_rub(candle: Dict) -> float:
        close_data = candle.get("close", {})
        units = int(close_data.get("units", 0) or 0)
        nano = int(close_data.get("nano", 0) or 0)
        price = units + nano / 1e9
        volume = int(candle.get("volume", 0) or 0)
        return price * volume

    async def close(self) -> None:
        await self._facade.close()
