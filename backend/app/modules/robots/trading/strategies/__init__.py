#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStrategiesInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/strategies/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .base import BaseStrategy
from .grain_seed import GrainSeedStrategy

_strategies = {
    'grain_seed': {
        'class': GrainSeedStrategy,
        'name': 'grain_seed',
        'title': 'По зёрнышку, по семечке',
        'description': 'Осторожная стратегия с фильтрами гэпа/волатильности и режимами тренд/флэт',
        'params_schema': {
            'gap_filter_pct': {'type': 'number', 'default': 2.5, 'label': 'Фильтр гэпа (%)'},
            'spread_limit_pct': {'type': 'number', 'default': 0.15, 'label': 'Лимит спреда (%)'},
            'spread_proxy_multiplier': {'type': 'number', 'default': 8.0, 'label': 'Множитель прокси-спреда'},
            'atr_period': {'type': 'integer', 'default': 14, 'min': 5, 'label': 'Период ATR'},
            'atr_min_pct': {'type': 'number', 'default': 1.5, 'label': 'Минимум ATR/Close (%)'},
            'adx_period': {'type': 'integer', 'default': 14, 'min': 5, 'label': 'Период ADX'},
            'adx_threshold': {'type': 'number', 'default': 22.0, 'label': 'Порог ADX (trend)'},
            'ma_fast_period': {'type': 'integer', 'default': 5, 'min': 1, 'label': 'MA fast (trend)'},
            'ma_slow_period': {'type': 'integer', 'default': 20, 'min': 2, 'label': 'MA slow (trend)'},
            'bb_period': {'type': 'integer', 'default': 20, 'min': 5, 'label': 'Период Bollinger'},
            'bb_stddev': {'type': 'number', 'default': 2.0, 'label': 'Отклонение Bollinger'},
            'commission_pct': {'type': 'number', 'default': 0.05, 'label': 'Комиссия брокера (%)'},
            'min_profit_target_pct': {'type': 'number', 'default': 0.35, 'label': 'Мин. цель прибыли (%)'},
            'day_loss_streak_limit': {'type': 'integer', 'default': 3, 'min': 1, 'label': 'Лимит убытков подряд/день'},
            'free_funds_reserve_pct': {'type': 'number', 'default': 50.0, 'label': 'Резерв свободных средств (%)'},
            'risk_per_trade_pct': {'type': 'number', 'default': 2.0, 'label': 'Риск на сделку (%)'},
            'max_position_size_pct': {'type': 'number', 'default': 20.0, 'label': 'Макс. размер позиции (%)'},
            'force_close_time_msk': {'type': 'string', 'default': '18:45', 'label': 'Принудительное закрытие (МСК)'},
            'force_market_flatten': {'type': 'boolean', 'default': True, 'label': 'После времени закрытия: отмена лимитов и рыночный выход'},
            'interval': {'type': 'string', 'default': 'CANDLE_INTERVAL_5_MIN', 'label': 'Интервал свечей'},
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