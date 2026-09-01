/** Human-readable labels for strategy/risk fill reasons (live monitor + backtest). */

const TRADE_REASON_LABELS: Record<string, string> = {
    entry: 'Вход',
    momentum_breakout: 'Пробой + объём',
    momentum_ma_cross_down: 'Выход: цена ниже MA',
    reversion_rsi_oversold: 'Вход: RSI перепродан',
    reversion_rsi_overbought: 'Вход: RSI перекуплен',
    reversion_rsi_target: 'Выход: RSI у цели',
    reversion_rsi_mean: 'Выход: RSI к средней',
    grid_tp: 'Сетка: тейк-профит',
    scalper_delta_cross: 'Скальп: дельта',
    scalper_delta_reversal: 'Скальп: разворот дельты',
    scalper_delta_invalidation: 'Скальп: инвалидация (ниже входа)',
    stop_loss: 'Стоп-лосс',
    take_profit: 'Тейк-профит',
    eod_flatten: 'EOD flatten',
    flatten: 'Закрытие',
    exit_strategy: 'Выход по стратегии',
    exit_sl_tp: 'SL/TP',
    broker_sync: 'Синх. брокера',
    exit: 'Выход',
}

export function tradeReasonLabel(code: string | null | undefined): string {
    if (!code) return '—'
    const key = String(code).trim()
    if (!key) return '—'
    const mapped = TRADE_REASON_LABELS[key.toLowerCase()]
    if (mapped) return mapped
    const grid = /^grid_level_(\d+)$/i.exec(key)
    if (grid) return `Сетка: уровень ${grid[1]}`
    return key
}
