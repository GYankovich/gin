export type PipelineStageId = 'p1' | 'p2' | 'p3'

export type PipelineStageVisualStatus = 'ok' | 'pending' | 'stale' | 'error' | 'disabled'

export type PipelineStageStatusView = {
    id: PipelineStageId
    status: PipelineStageVisualStatus
    label: string
    detail: string
}

const STALE_MS = 24 * 60 * 60 * 1000

function parseIso(iso: string | null | undefined): number | null {
    if (!iso) return null
    const t = new Date(iso).getTime()
    return Number.isNaN(t) ? null : t
}

function isStale(iso: string | null | undefined): boolean {
    const t = parseIso(iso)
    if (t == null) return true
    return Date.now() - t > STALE_MS
}

export function derivePipelineStageStatuses(opts: {
    robotType: number
    universeMode: string
    historicalEnabled: boolean
    candidatePoolCount: number
    allowedFigisCount: number
    lastHistoricalRun: string | null
    lastPaperRun: string | null
    strategy: string
    interval: string
    tokenId: number
    lastError?: string | null
}): PipelineStageStatusView[] {
    if (Number(opts.robotType) !== 2) return []

    const fixed = opts.universeMode === 'fixed'
    const p1Disabled = fixed || !opts.historicalEnabled

    let p1: PipelineStageStatusView
    if (p1Disabled) {
        p1 = {
            id: 'p1',
            status: 'disabled',
            label: 'Поиск идей — не используется',
            detail: fixed ? 'Режим: фиксированный список' : 'Исторический скрининг выключен',
        }
    } else if (opts.lastError) {
        p1 = {
            id: 'p1',
            status: 'error',
            label: 'Поиск идей — ошибка',
            detail: opts.lastError.slice(0, 120),
        }
    } else if (opts.candidatePoolCount > 0 && !isStale(opts.lastHistoricalRun)) {
        p1 = {
            id: 'p1',
            status: 'ok',
            label: 'Поиск идей — выполнен',
            detail: `Найдено ${opts.candidatePoolCount} кандидатов`,
        }
    } else if (opts.candidatePoolCount > 0 && isStale(opts.lastHistoricalRun)) {
        p1 = {
            id: 'p1',
            status: 'stale',
            label: 'Поиск идей — устарел',
            detail: `${opts.candidatePoolCount} в пуле, перезапустите скрининг`,
        }
    } else {
        p1 = {
            id: 'p1',
            status: 'pending',
            label: 'Поиск идей — не запускался',
            detail: 'candidate_pool пуст · нажмите «Запустить»',
        }
    }

    let p2: PipelineStageStatusView
    if (fixed) {
        p2 = {
            id: 'p2',
            status: 'disabled',
            label: 'Отбор бумаг — не используется',
            detail: 'Список тикеров задан вручную',
        }
    } else if (opts.allowedFigisCount > 0 && !isStale(opts.lastPaperRun)) {
        p2 = {
            id: 'p2',
            status: 'ok',
            label: 'Отбор бумаг — выполнен',
            detail: `${opts.allowedFigisCount} FIGI в allowed_figis`,
        }
    } else if (opts.allowedFigisCount > 0 && isStale(opts.lastPaperRun)) {
        p2 = {
            id: 'p2',
            status: 'stale',
            label: 'Отбор бумаг — устарел',
            detail: `${opts.allowedFigisCount} FIGI · пересоберите отбор`,
        }
    } else if (opts.candidatePoolCount === 0 && !p1Disabled) {
        p2 = {
            id: 'p2',
            status: 'pending',
            label: 'Отбор бумаг — ждёт П1',
            detail: 'Сначала заполните candidate_pool',
        }
    } else {
        p2 = {
            id: 'p2',
            status: 'pending',
            label: 'Отбор бумаг — не запускался',
            detail: 'allowed_figis пуст · нажмите «Запустить»',
        }
    }

    const p3Ok = Boolean(opts.strategy && opts.interval && opts.tokenId > 0)
    const p3: PipelineStageStatusView = {
        id: 'p3',
        status: p3Ok ? 'ok' : 'pending',
        label: p3Ok ? 'Торговая логика — настроена' : 'Торговая логика — не настроена',
        detail: p3Ok
            ? `${opts.strategy} · ${opts.interval.replace('CANDLE_INTERVAL_', '').replace('_', ' ')}`
            : 'Укажите стратегию, интервал и токен',
    }

    return [p1, p2, p3]
}
