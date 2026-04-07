from typing import Dict, Optional, List, Any

import pandas as pd

from .base import BaseStrategy


class AggressiveMomentumStrategy(BaseStrategy):
    """Select top-N momentum leaders; others are SELL."""

    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        periods = self.params.get("momentum_periods", [21, 63, 126])
        top_n = int(self.params.get("top_n", 3))
        scores: Dict[str, float] = {}

        for figi in self.figis:
            candles = candles_data.get(figi, [])
            closes = [
                int(c["close"].get("units", 0) or 0) + int(c["close"].get("nano", 0) or 0) / 1e9
                for c in candles
                if c.get("close")
            ]
            if len(closes) < max(periods) + 2:
                continue
            s = pd.Series(closes)
            score = 0.0
            for idx, p in enumerate(periods, start=1):
                ret = (s.iloc[-1] / s.iloc[-p] - 1.0) if s.iloc[-p] else 0.0
                score += float(ret) * float(idx)
            scores[figi] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_figis = {figi for figi, _ in ranked[:top_n]}
        signals: Dict[str, Optional[str]] = {}
        for figi in self.figis:
            if figi in top_figis:
                signals[figi] = "BUY"
            elif figi in scores:
                signals[figi] = "SELL"
            else:
                signals[figi] = None
        return signals
