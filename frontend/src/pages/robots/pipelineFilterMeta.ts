export type PipelineFilterType =
    | 'security_status'
    | 'trading_status'
    | 'volume'
    | 'num_trades'
    | 'gap'
    | 'spread'
    | 'atr'
    | 'capitalization'
    | 'allowed_tickers'
    | 'min_step_ratio'
    | 'excluded_tickers'
    | 'turnover'
    | 'gap_retention'
    | 'price_vs_open'
    | 'opening_range'

export type PipelineFilter = {
    id: string
    type: PipelineFilterType
    min?: number
    max_percent?: number
    min_percent?: number
    period?: number
    eq?: string
    direction?: 'BOTH' | 'UP_ONLY' | 'DOWN_ONLY'
    max_steps?: number
    min_ratio?: number
    list?: string[] | null
}

export const FILTER_META: Record<PipelineFilterType, { label: string }> = {
    security_status: { label: 'Статус бумаги' },
    trading_status: { label: 'Режим торгов' },
    volume: { label: 'Объём за сегодня' },
    num_trades: { label: 'Количество сделок' },
    gap: { label: 'Утренний гэп' },
    spread: { label: 'Спред' },
    atr: { label: 'ATR' },
    capitalization: { label: 'Капитализация' },
    allowed_tickers: { label: 'Белый список' },
    excluded_tickers: { label: 'Чёрный список' },
    min_step_ratio: { label: 'Шаг цены' },
    turnover: { label: 'Оборачиваемость' },
    gap_retention: { label: 'Удержание гэпа' },
    price_vs_open: { label: 'Цена vs открытие' },
    opening_range: { label: 'Диапазон открытия' },
}

/** Пояснение под полем — человеческий язык вместо tooltip. */
export const FILTER_FIELD_HINT: Record<PipelineFilterType, string> = {
    security_status: 'Бумага должна быть активна и допущена к торгам на MOEX.',
    trading_status: 'Инструмент должен находиться в режиме торгов, а не в паузе.',
    volume: 'Объём торгов за сегодня в рублях. Отсекает низколиквидные бумаги.',
    num_trades: 'Минимальное число сделок за сессию — показатель активности.',
    gap: 'Ограничивает утренний ценовой разрыв относительно закрытия вчера.',
    spread: 'Разница между лучшей покупкой и продажей. Узкий спред — лучше ликвидность.',
    atr: 'Средняя волатильность за период. Гарантирует достаточное движение цены.',
    capitalization: 'Рыночная капитализация эмитента в рублях.',
    allowed_tickers: 'Только эти тикеры пройдут отбор. Пустой список — фильтр игнорируется.',
    excluded_tickers: 'Эти тикеры будут исключены из universe.',
    min_step_ratio: 'Технический фильтр: шаг цены не должен «съедать» комиссию.',
    turnover: 'Доля оборота выпуска за день — дополнительный критерий ликвидности.',
    gap_retention: 'Насколько цена удерживает утренний гэп. >0.7 — тренд, <0.3 — откат.',
    price_vs_open: 'Цена не должна сильно отклоняться от цены открытия.',
    opening_range: 'Минимальная ширина диапазона High–Low в начале сессии.',
}

const RUB = new Intl.NumberFormat('ru-RU')

export function formatRub(value: number | undefined): string {
    return `${RUB.format(Number(value || 0))} ₽`
}

const GAP_DIRECTION_LABEL: Record<string, string> = {
    BOTH: 'в обе стороны',
    UP_ONLY: 'только рост',
    DOWN_ONLY: 'только падение',
}

export function formatHumanFilterRule(f: PipelineFilter): string {
    switch (f.type) {
        case 'security_status':
            return `Статус бумаги = «${f.eq || 'A'}» (активна)`
        case 'trading_status':
            return `Режим торгов = «${f.eq || 'T'}» (идут торги)`
        case 'volume':
            return `Объём за сегодня ≥ ${formatRub(f.min)}`
        case 'num_trades':
            return `Количество сделок ≥ ${RUB.format(Number(f.min || 0))}`
        case 'gap': {
            const dir = GAP_DIRECTION_LABEL[f.direction || 'BOTH'] || 'в обе стороны'
            return `Утренний гэп ≤ ${f.max_percent ?? 0}% (${dir})`
        }
        case 'spread':
            return `Спред ≤ ${f.max_percent ?? 0}%`
        case 'atr':
            return `ATR (${f.period ?? 14} дн.) ≥ ${f.min_percent ?? 0}% от цены`
        case 'capitalization':
            return `Капитализация ≥ ${formatRub(f.min)}`
        case 'turnover':
            return `Оборачиваемость ≥ ${f.min_percent ?? 0}% от выпуска`
        case 'gap_retention':
            return `Удержание гэпа ≥ ${f.min_ratio ?? 0}`
        case 'price_vs_open':
            return `Цена ≥ ${((f.min_percent ?? 0.998) * 100).toFixed(2)}% от открытия`
        case 'opening_range':
            return `Диапазон открытия ≥ ${f.min_percent ?? 0}%`
        case 'min_step_ratio':
            return `Макс. шагов цены ≤ ${f.max_steps ?? 5}`
        case 'allowed_tickers':
            return Array.isArray(f.list) && f.list.length
                ? `Только тикеры: ${f.list.slice(0, 5).join(', ')}${f.list.length > 5 ? ` … +${f.list.length - 5}` : ''}`
                : 'Белый список (не задан)'
        case 'excluded_tickers':
            return Array.isArray(f.list) && f.list.length
                ? `Исключить: ${f.list.slice(0, 5).join(', ')}${f.list.length > 5 ? ` … +${f.list.length - 5}` : ''}`
                : 'Чёрный список (не задан)'
        default:
            return FILTER_META[f.type]?.label ?? f.type
    }
}

export const FILTER_DEFAULTS: Partial<Record<PipelineFilterType, Omit<PipelineFilter, 'id'>>> = {
    volume: { type: 'volume', min: 50_000_000 },
    num_trades: { type: 'num_trades', min: 100 },
    gap: { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
    spread: { type: 'spread', max_percent: 0.15 },
    atr: { type: 'atr', min_percent: 1.5, period: 14 },
    capitalization: { type: 'capitalization', min: 10_000_000_000 },
    turnover: { type: 'turnover', min_percent: 0.1 },
    gap_retention: { type: 'gap_retention', min_ratio: 0.5 },
    price_vs_open: { type: 'price_vs_open', min_percent: 0.998 },
    opening_range: { type: 'opening_range', min_percent: 1.5 },
    min_step_ratio: { type: 'min_step_ratio', max_steps: 5 },
    allowed_tickers: { type: 'allowed_tickers', list: [] },
    excluded_tickers: { type: 'excluded_tickers', list: [] },
}

/** Типы, которые можно добавить кнопкой «+ Добавить фильтр». */
export const ADDABLE_SNAPSHOT_FILTER_TYPES: PipelineFilterType[] = [
    'volume',
    'num_trades',
    'gap',
    'spread',
    'atr',
    'capitalization',
    'turnover',
    'gap_retention',
    'price_vs_open',
    'opening_range',
    'min_step_ratio',
    'allowed_tickers',
    'excluded_tickers',
]

export const DEFAULT_PIPELINE_FILTERS: Array<Omit<PipelineFilter, 'id'>> = [
    { type: 'security_status', eq: 'A' },
    { type: 'trading_status', eq: 'T' },
    { type: 'volume', min: 50_000_000 },
    { type: 'num_trades', min: 100 },
    { type: 'gap', max_percent: 2.5, direction: 'BOTH' },
    { type: 'spread', max_percent: 0.15 },
    { type: 'atr', min_percent: 1.5, period: 14 },
    { type: 'turnover', min_percent: 0.1 },
    { type: 'gap_retention', min_ratio: 0.5 },
]
