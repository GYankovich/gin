#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStrategiesInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/strategies/__init__.py` — автоматическая разметка для Obsidian Source Scanner.
"""Реестр торговых стратегий.

Регистрирует три стратегии (см. docs/BRD-ARCH-03-unified-engine-architecture.md
§6): grain_seed, momentum_breakout, reversion_to_ma. Контракт единый —
`BaseStrategy.generate_signals(candles_data) -> Dict[figi, "BUY"/"SELL"/None]`.

Новые места кода должны импортировать стратегии через `get_strategy_class()`.
"""

from .base import BaseStrategy
from .grain_seed import GrainSeedStrategy
from .momentum_breakout import MomentumBreakoutStrategy
from .reversion_to_ma import ReversionToMaStrategy

TINVEST_CANDLE_INTERVALS = [
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
]

_interval_field = {
    'type': 'string',
    'default': 'CANDLE_INTERVAL_5_MIN',
    'label': 'Интервал свечей (T-Invest WS)',
    'enum': TINVEST_CANDLE_INTERVALS,
    'description': 'WebSocket subscribeCandles + расчёт сигналов; история — REST bootstrap 10m',
}

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
            # MOEX/T-Invest only — stripped for ByBit (crypto is 24/7).
            'force_close_time_msk': {
                'type': 'string',
                'default': '18:45',
                'label': 'Принудительное закрытие (МСК)',
                'brokers': ['tinvest'],
            },
            'force_market_flatten': {
                'type': 'boolean',
                'default': True,
                'label': 'После времени закрытия: отмена лимитов и рыночный выход',
                'brokers': ['tinvest'],
            },
            'interval': {**_interval_field, 'default': 'CANDLE_INTERVAL_5_MIN'},
            'candle_days': {'type': 'integer', 'default': 14, 'min': 1, 'max': 3650, 'label': 'Период истории свечей (дней)'},
            'signal_profile': {
                'type': 'string',
                'default': 'legacy',
                'label': 'Профиль сигналов',
                'enum': ['legacy', 'tz_signals_v1'],
                'description': 'tz_signals_v1 — §6.5 docs/backtest_review (только BUY; SL/TP/флэттен в движке бэктеста)',
            },
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'}
        }
    },
    'momentum_breakout': {
        'class': MomentumBreakoutStrategy,
        'name': 'momentum_breakout',
        'title': 'Пробой максимума',
        'description': 'Вход при пробое максимума N дней в первые M минут торгов',
        'params_schema': {
            'lookback_days': {'type': 'integer', 'default': 5, 'min': 1, 'label': 'Дней истории для уровня'},
            'entry_minutes_from_open': {'type': 'integer', 'default': 30, 'min': 1, 'label': 'Окно входа от открытия, мин'},
            'hold_candles': {'type': 'integer', 'default': 4, 'min': 1, 'label': 'Сколько свечей удерживать'},
            'volume_confirmation': {'type': 'boolean', 'default': True, 'label': 'Требовать подтверждения объёмом'},
            'volume_multiplier': {'type': 'number', 'default': 1.5, 'label': 'Множитель объёма'},
            'exit_on_reverse': {'type': 'boolean', 'default': True, 'label': 'Выход при пробое вниз'},
            'sell_only_if_has_asset': {'type': 'boolean', 'default': True, 'label': 'SELL только при наличии бумаги'},
            'allow_entry_all_day': {'type': 'boolean', 'default': False, 'label': 'Разрешить вход в течение всей сессии'},
            'interval': {**_interval_field, 'default': 'CANDLE_INTERVAL_10_MIN'},
            'candle_days': {'type': 'integer', 'default': 14, 'min': 1, 'max': 3650, 'label': 'Период истории свечей (дней)'},
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'},
        },
    },
    'reversion_to_ma': {
        'class': ReversionToMaStrategy,
        'name': 'reversion_to_ma',
        'title': 'Возврат к MA',
        'description': 'Mean-reversion: отскок от MA при перекупленности/перепроданности RSI',
        'params_schema': {
            'ma_period': {'type': 'integer', 'default': 20, 'min': 5, 'label': 'Период MA'},
            'deviation_pct': {'type': 'number', 'default': 2.0, 'label': 'Отклонение от MA (%)'},
            'rsi_period': {'type': 'integer', 'default': 14, 'min': 5, 'label': 'Период RSI'},
            'rsi_overbought': {'type': 'number', 'default': 80.0, 'label': 'Порог перекупленности RSI'},
            'rsi_oversold': {'type': 'number', 'default': 20.0, 'label': 'Порог перепроданности RSI'},
            'max_hold_candles': {'type': 'integer', 'default': 12, 'min': 1, 'label': 'Максимум удержания (свечей)'},
            'use_volume_filter': {'type': 'boolean', 'default': True, 'label': 'Использовать фильтр объёма'},
            'interval': {**_interval_field, 'default': 'CANDLE_INTERVAL_5_MIN'},
            'candle_days': {'type': 'integer', 'default': 14, 'min': 1, 'max': 3650, 'label': 'Период истории свечей (дней)'},
            'figis': {'type': 'array', 'items': {'type': 'string'}, 'label': 'Инструменты (FIGI)'},
        },
    },
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
        'params_schema': strategy['params_schema'],
    }


def list_strategies():
    return [
        {
            'name': name,
            'title': data['title'],
            'description': data['description'],
            'params_schema': data['params_schema'],
        }
        for name, data in _strategies.items()
    ]
