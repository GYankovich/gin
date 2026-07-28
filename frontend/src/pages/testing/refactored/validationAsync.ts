import { marketService } from '@/services/marketService'
import { parseFixedTickersInput } from '@/utils/universeMode'
import type { TestingFormState, ValidationIssue } from '@/pages/testing/refactored/types/forms'
import { periodSpanDays, validateTestingForm } from '@/pages/testing/refactored/validation'
import { suggestedMoexIntervalForSignal } from '@/pages/testing/testingPipeline'
import { toApiDate } from '@/pages/testing/testingUtils'

const MIN_COVERAGE_PCT = 50

function estimateCoveragePct(
    bucketCount: number,
    fromDate: string,
    toDate: string,
    interval: string,
): number {
    const span = periodSpanDays(fromDate, toDate)
    if (!span || span <= 0) return 0
    const barsPerDay =
        interval === '5m' ? 168 : interval === '10m' ? 84 : interval === '1h' ? 14 : 1
    const expected = span * barsPerDay
    if (expected <= 0) return 0
    return Math.min(100, (bucketCount / expected) * 100)
}

/** Server-backed checks: TQBR tickers, MOEX candle coverage (fixed universe). */
export async function validateTestingFormAsync(
    form: TestingFormState,
    opts?: { robotType?: number | null },
): Promise<ValidationIssue[]> {
    const issues = validateTestingForm(form, opts)
    const tickers = parseFixedTickersInput(form.fixedTickersText)

    if (form.market !== 'crypto' && form.universeMode === 'fixed' && tickers.length > 0) {
        try {
            const { items } = await marketService.listTqbrSecuritiesBulk(15_000)
            const known = new Set(items.map(row => String(row.secid || '').trim().toUpperCase()).filter(Boolean))
            for (const t of tickers) {
                if (!known.has(t)) {
                    issues.push({
                        field: 'fixedTickersText',
                        message: `Тикер ${t} не найден в справочнике TQBR`,
                    })
                }
            }
        } catch {
            issues.push({
                field: 'fixedTickersText',
                message: 'Не удалось проверить тикеры TQBR (справочник недоступен)',
            })
        }
    }

    if (
        form.market !== 'crypto' &&
        form.universeMode === 'fixed' &&
        tickers.length > 0 &&
        form.fromDate &&
        form.toDate
    ) {
        try {
            const interval = suggestedMoexIntervalForSignal(form.interval)
            const cov = await marketService.getCandlesCoverageSummary({
                tickers,
                board: 'TQBR',
                interval,
                from: toApiDate(form.fromDate),
                to: toApiDate(form.toDate),
            })
            const byTicker = new Map(cov.items.map(row => [row.ticker.toUpperCase(), row]))
            for (const t of tickers) {
                const row = byTicker.get(t)
                if (!row || row.bucket_count <= 0) {
                    issues.push({
                        field: 'period',
                        message: `Нет свечей в БД для ${t} за выбранный период`,
                    })
                    continue
                }
                const pct = estimateCoveragePct(row.bucket_count, form.fromDate, form.toDate, interval)
                if (pct < MIN_COVERAGE_PCT) {
                    issues.push({
                        field: 'period',
                        message: `Покрытие данных для ${t} ~${pct.toFixed(0)}% (< ${MIN_COVERAGE_PCT}%)`,
                    })
                }
            }
        } catch {
            // coverage API optional — sync validation still applies
        }
    }

    if (form.market === 'crypto' && form.leverage > 3) {
        issues.push({
            field: 'leverage',
            message: `Плечо ${form.leverage}x повышает риск маржин-колла (рекомендуется ≤ 3)`,
            severity: 'warning',
        })
    }

    return issues
}

export function hasBlockingValidationIssues(issues: ValidationIssue[]): boolean {
    return issues.some(i => i.severity !== 'warning')
}
