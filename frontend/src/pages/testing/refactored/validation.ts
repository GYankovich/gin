import { parseFixedTickersInput } from '@/utils/universeMode'
import type { TestingFormState, ValidationIssue } from '@/pages/testing/refactored/types/forms'

export const MAX_BACKTEST_PERIOD_DAYS = 365
export const MAX_DAILY_LOSS_PCT = 100

export function periodSpanDays(fromDate: string, toDate: string): number | null {
    if (!fromDate || !toDate) return null
    const from = new Date(fromDate)
    const to = new Date(toDate)
    if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime())) return null
    return Math.ceil((to.getTime() - from.getTime()) / 86_400_000) + 1
}

export function validateTestingForm(form: TestingFormState, opts?: { robotType?: number | null }): ValidationIssue[] {
    const issues: ValidationIssue[] = []

    if (!form.fromDate || !form.toDate) {
        issues.push({ field: 'period', message: 'Выберите период бэктеста' })
    } else {
        const span = periodSpanDays(form.fromDate, form.toDate)
        if (span != null && span > MAX_BACKTEST_PERIOD_DAYS) {
            issues.push({
                field: 'period',
                message: `Период не должен превышать ${MAX_BACKTEST_PERIOD_DAYS} календарных дней`,
            })
        }
        if (span != null && span < 1) {
            issues.push({ field: 'period', message: 'Дата окончания должна быть не раньше начала' })
        }
    }

    if (form.maxDailyLossPct < 0 || form.maxDailyLossPct > MAX_DAILY_LOSS_PCT) {
        issues.push({
            field: 'maxDailyLossPct',
            message: `Макс. дневной убыток: 0–${MAX_DAILY_LOSS_PCT}%`,
        })
    }

    const symbols = parseFixedTickersInput(form.fixedTickersText)
    if (form.market === 'crypto') {
        if (form.cryptoUniverseMode === 'fixed' && symbols.length === 0) {
            issues.push({ field: 'fixedTickersText', message: 'Укажите символы ByBit (например BTCUSDT)' })
        }
        if (form.cryptoUniverseMode === 'auto' && form.cryptoMinVolume24hUsd <= 0) {
            issues.push({ field: 'cryptoMinVolume24hUsd', message: 'Min volume должен быть > 0' })
        }
    } else if (form.universeMode === 'fixed' && symbols.length === 0) {
        issues.push({ field: 'fixedTickersText', message: 'Укажите тикеры для режима «Фиксированный список»' })
    }

    if (opts?.robotType != null && opts.robotType !== 2) {
        issues.push({ field: 'robot', message: 'Backtest доступен только для торговых роботов type=2' })
    }

    return issues
}

export function validateTestingFormOrThrow(form: TestingFormState, opts?: { robotType?: number | null }): void {
    const issues = validateTestingForm(form, opts)
    if (issues.length > 0) {
        throw new Error(issues.map(i => i.message).join('; '))
    }
}
