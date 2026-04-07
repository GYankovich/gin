from .base import BaseStrategy
from .ma_cross import MACrossStrategy
from .conservative import ConservativeStrategy
from .aggressive_momentum import AggressiveMomentumStrategy
from .defensive_cash import DefensiveCashStrategy

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
    ,
    'conservative': {
        'class': ConservativeStrategy,
        'name': 'conservative',
        'title': 'Консервативный портфель',
        'description': 'Снижает риск при повышенной волатильности и ребалансирует портфель',
        'params_schema': {
            'volatility_lookback': {'type': 'integer', 'default': 60, 'min': 20, 'label': 'Период волатильности'},
            'max_volatility': {'type': 'number', 'default': 0.20, 'label': 'Макс. волатильность'},
            'interval': {'type': 'string', 'default': 'CANDLE_INTERVAL_DAY', 'label': 'Интервал свечей'},
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'}
        }
    },
    'aggressive_momentum': {
        'class': AggressiveMomentumStrategy,
        'name': 'aggressive_momentum',
        'title': 'Агрессивный моментум',
        'description': 'Покупает лидеров моментума, остальные инструменты сокращает',
        'params_schema': {
            'momentum_periods': {'type': 'array', 'default': [21, 63, 126], 'label': 'Периоды моментума'},
            'top_n': {'type': 'integer', 'default': 3, 'min': 1, 'label': 'Топ активов'},
            'interval': {'type': 'string', 'default': 'CANDLE_INTERVAL_DAY', 'label': 'Интервал свечей'},
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'}
        }
    },
    'defensive_cash': {
        'class': DefensiveCashStrategy,
        'name': 'defensive_cash',
        'title': 'Защитный кэш',
        'description': 'Переходит в защитный режим при росте волатильности',
        'params_schema': {
            'volatility_threshold': {'type': 'number', 'default': 0.25, 'label': 'Порог волатильности'},
            'interval': {'type': 'string', 'default': 'CANDLE_INTERVAL_DAY', 'label': 'Интервал свечей'},
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'}
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