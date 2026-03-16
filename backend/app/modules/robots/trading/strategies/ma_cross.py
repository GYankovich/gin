import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from .base import BaseStrategy


class MACrossStrategy(BaseStrategy):
    """
    Стратегия на пересечении скользящих средних
    """

    async def get_required_candles_count(self) -> int:
        slow = self.params.get('slow_period', 30)
        return slow + 20  # запас для расчета

    async def generate_signals(self) -> Dict[str, Optional[str]]:
        signals = {}
        fast = self.params.get('fast_period', 10)
        slow = self.params.get('slow_period', 30)
        interval = self.params.get('interval', 'CANDLE_INTERVAL_DAY')

        to_date = datetime.utcnow()
        days_needed = await self.get_required_candles_count()
        from_date = to_date - timedelta(days=days_needed)

        for figi in self.figis:
            try:
                candles = await self.client.get_candles(figi, from_date, to_date, interval)
                if len(candles) < slow + 1:
                    signals[figi] = None
                    continue

                # Преобразуем в DataFrame
                df = pd.DataFrame([{
                    'time': c['time'],
                    'close': c['close']['units'] + c['close']['nano'] / 1e9
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
                print(f"Error processing {figi}: {e}")
                signals[figi] = None

        return signals