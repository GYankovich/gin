import pandas as pd
from typing import Dict, Optional, List, Any
from .base import BaseStrategy
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class MACrossStrategy(BaseStrategy):
    """
    Стратегия на пересечении скользящих средних
    """

    async def get_required_candles_count(self) -> int:
        slow = self.params.get('slow_period')
        if slow is None:
            raise ValueError("strategy_params.fast_period and strategy_params.slow_period are required for ma_cross")
        return slow + 20  # запас для расчета

    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        signals = {}
        fast = self.params.get('fast_period')
        slow = self.params.get('slow_period')
        if fast is None or slow is None:
            raise ValueError("strategy_params.fast_period and strategy_params.slow_period are required for ma_cross")
        if fast >= slow:
            raise ValueError("strategy_params.fast_period must be less than strategy_params.slow_period")

        for figi in self.figis:
            try:
                candles = candles_data.get(figi, [])
                if len(candles) < slow + 1:
                    signals[figi] = None
                    continue

                df = pd.DataFrame([{
                    'time': c['time'],
                    'close': int(c['close'].get('units', 0) or 0) + int(c['close'].get('nano', 0) or 0) / 1e9
                } for c in candles])

                df['fast_ma'] = df['close'].rolling(fast).mean()
                df['slow_ma'] = df['close'].rolling(slow).mean()

                if len(df) < 2:
                    signals[figi] = None
                    continue

                prev_fast = df['fast_ma'].iloc[-2]
                prev_slow = df['slow_ma'].iloc[-2]
                curr_fast = df['fast_ma'].iloc[-1]
                curr_slow = df['slow_ma'].iloc[-1]

                if pd.notna(prev_fast) and pd.notna(prev_slow) and pd.notna(curr_fast) and pd.notna(curr_slow):
                    if prev_fast <= prev_slow and curr_fast > curr_slow:
                        signals[figi] = 'BUY'
                    elif prev_fast >= prev_slow and curr_fast < curr_slow:
                        signals[figi] = 'SELL'
                    else:
                        signals[figi] = None
                else:
                    signals[figi] = None

            except Exception as e:
                logger.error(f"Error processing {figi}: {e}", exc_info=True)
                signals[figi] = None

        return signals