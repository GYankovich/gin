from .base import BaseStrategy
from .ma_cross import MACrossStrategy

_strategies = {
    'ma_cross': {
        'class': MACrossStrategy,
        'name': 'ma_cross',
        'title': 'Пересечение скользящих средних',
        'description': 'Покупает при пересечении быстрой MA снизу вверх, продаёт при пересечении сверху вниз',
        'params_schema': {
            'fast_period': {'type': 'integer', 'default': 10, 'min': 1, 'label': 'Быстрый период'},
            'slow_period': {'type': 'integer', 'default': 30, 'min': 2, 'label': 'Медленный период'},
            'interval': {
                'type': 'string',
                'default': 'CANDLE_INTERVAL_DAY',
                'enum': [
                    'CANDLE_INTERVAL_5_SEC',
                    'CANDLE_INTERVAL_10_SEC',
                    'CANDLE_INTERVAL_30_SEC',
                    'CANDLE_INTERVAL_1_MIN',
                    'CANDLE_INTERVAL_2_MIN',
                    'CANDLE_INTERVAL_3_MIN',
                    'CANDLE_INTERVAL_5_MIN',
                    'CANDLE_INTERVAL_10_MIN',
                    'CANDLE_INTERVAL_15_MIN',
                    'CANDLE_INTERVAL_30_MIN',
                    'CANDLE_INTERVAL_HOUR',
                    'CANDLE_INTERVAL_2_HOUR',
                    'CANDLE_INTERVAL_4_HOUR',
                    'CANDLE_INTERVAL_DAY',
                    'CANDLE_INTERVAL_WEEK',
                    'CANDLE_INTERVAL_MONTH',
                ],
                'label': 'Интервал свечей'
            },
            'figis': {
                'type': 'array',
                'items': {'type': 'string'},
                'label': 'Инструменты (FIGI)'
            }
        }
    }
}

def get_strategy_class(name: str):
    if name not in _strategies:
        raise ValueError(f"Unknown strategy: {name}")
    return _strategies[name]['class']

def get_strategy_info(name: str):
    strategy = _strategies.get(name)
    if not strategy:
        return None
    return {
        'name': name,
        'title': strategy['title'],
        'description': strategy['description'],
        'params_schema': strategy['params_schema']  # ВАЖНО: добавляем это поле
    }

def list_strategies():
    return [
        {
            'name': name,
            'title': data['title'],
            'description': data['description'],
            'params_schema': data['params_schema']  # ВАЖНО: добавляем это поле
        }
        for name, data in _strategies.items()
    ]