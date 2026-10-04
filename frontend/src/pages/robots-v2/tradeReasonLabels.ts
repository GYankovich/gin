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

/** Risk / exec reject codes — glass-box backtest + monitor. */
const REJECT_REASON_LABELS: Record<string, string> = {
    risk_block: 'Блок риска',
    risk_blocked: 'Блок риска',
    entries_paused: 'Новые входы на паузе',
    session_halted: 'Сессия остановлена',
    max_drawdown: 'Превышен max drawdown',
    no_position: 'Нет позиции для выхода',
    break_even_block: 'Блок break-even',
    zero_qty: 'Нулевой объём',
    stale_or_missing_price: 'Нет актуальной цены',
    exec_reject: 'Отказ исполнения',
    exec_rejected: 'Отказ исполнения',
    reject_cooldown: 'Кулдаун после отказа',
    in_flight_order: 'Уже есть заявка в полёте',
    figi_unresolved: 'FIGI не сопоставлен',
    broker_or_account_missing: 'Нет брокера / счёта',
    invalid_qty_or_ticker: 'Некорректный тикер или объём',
    fill_confirm_timeout: 'Нет подтверждения исполнения',
    broker_rejected: 'Брокер отклонил заявку',
    short_not_allowed: 'Шорт запрещён',
    blocked_pause_after_loss_streak: 'Пауза после серии убытков',
    blocked_daily_loss_cap: 'Дневной лимит убытка',
    max_concurrent_positions: 'Лимит одновременных позиций',
    no_execution_price: 'Нет цены исполнения',
    rejected_position_size: 'Размер позиции отклонён',
    exit_below_break_even: 'Выход ниже break-even',
    stale_mark_tp: 'Устаревшая mark для TP',
    already_resting: 'Заявка уже в рынке',
    outside_session: 'Вне торговой сессии',
    eod_hold: 'EOD: удержание',
    no_signal: 'Нет сигнала',
    warmup: 'Прогрев индикаторов',
    schedule_skip: 'Пропуск по расписанию',
    deferred: 'Отложено (next open)',
    dropped_deferred: 'Отложенный ордер сброшен',
}

export function tradeReasonLabel(code: string | null | undefined): string {
    if (!code) return '—'
    const key = String(code).trim()
    if (!key) return '—'
    const lower = key.toLowerCase()
    const mapped = TRADE_REASON_LABELS[lower] ?? REJECT_REASON_LABELS[lower]
    if (mapped) return mapped
    const grid = /^grid_level_(\d+)$/i.exec(key)
    if (grid) return `Сетка: уровень ${grid[1]}`
    const streak = /^loss_streak>=(\d+)$/i.exec(key)
    if (streak) return `Серия убытков ≥ ${streak[1]}`
    return key
}
