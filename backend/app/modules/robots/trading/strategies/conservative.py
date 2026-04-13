from typing import Dict, Optional, List, Any

import pandas as pd

from .base import BaseStrategy


class ConservativeStrategy(BaseStrategy):
    """Low-volatility allocation strategy with rebalance signal."""

    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        lookback = int(self.params.get("volatility_lookback", 60))
        max_volatility = float(self.params.get("max_volatility", 0.20))
        signals: Dict[str, Optional[str]] = {}

        for figi in self.figis:
            candles = candles_data.get(figi, [])
            if len(candles) < max(lookback, 20):
                signals[figi] = None
                continue
            closes = [
                int(c["close"].get("units", 0) or 0) + int(c["close"].get("nano", 0) or 0) / 1e9
                for c in candles[-lookback:]
                if c.get("close")
            ]
            if len(closes) < 10:
                signals[figi] = None
                continue
            series = pd.Series(closes)
            vol = float(series.pct_change().dropna().std() * (252 ** 0.5))
            # Backtest engine supports BUY/SELL only.
            # In low volatility we keep/enter exposure with BUY.
            signals[figi] = "SELL" if vol > max_volatility else "BUY"
        return signals
