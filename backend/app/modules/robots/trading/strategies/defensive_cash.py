from typing import Dict, Optional, List, Any

import pandas as pd

from .base import BaseStrategy


class DefensiveCashStrategy(BaseStrategy):
    """Move to defensive mode on high volatility/correlation proxies."""

    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        volatility_threshold = float(self.params.get("volatility_threshold", 0.25))
        signals: Dict[str, Optional[str]] = {}
        vols: Dict[str, float] = {}

        for figi in self.figis:
            candles = candles_data.get(figi, [])
            closes = [
                int(c["close"].get("units", 0) or 0) + int(c["close"].get("nano", 0) or 0) / 1e9
                for c in candles[-60:]
                if c.get("close")
            ]
            if len(closes) < 20:
                signals[figi] = None
                continue
            returns = pd.Series(closes).pct_change().dropna()
            vols[figi] = float(returns.std() * (252 ** 0.5))

        if not vols:
            return {figi: None for figi in self.figis}
        avg_vol = sum(vols.values()) / len(vols)
        risk_off = avg_vol > volatility_threshold

        for figi in self.figis:
            if figi not in vols:
                signals[figi] = None
                continue
            signals[figi] = "SELL" if risk_off else "BUY"
        return signals
