import type { RobotHistoryBacktestResult } from '@/types/robot'
import type { TestingMarket } from '@/pages/testing/refactored/types/forms'

export function parseTickers(v: string): string[] {
    return v.split(',').map(x => x.trim().toUpperCase()).filter(Boolean)
}

/** Парсинг числа из поля ввода (запятая как десятичный разделитель, min/max). */
export function parseNum(raw: string, allowDecimal: boolean, min?: number, max?: number): number {
    const cleaned = allowDecimal ? raw.replace(/[^0-9.,-]/g, '').replace(',', '.') : raw.replace(/[^0-9-]/g, '')
    let normalized = cleaned.replace(/^(-?)0+(\d)/, '$1$2')
    if (normalized === '' || normalized === '-' || normalized === '.') normalized = '0'
    let n = Number(normalized)
    if (!Number.isFinite(n)) n = 0
    if (min != null && n < min) n = min
    if (max != null && n > max) n = max
    return n
}

export function toApiDate(d: string): string {
    const dt = new Date(d)
    if (Number.isNaN(dt.getTime())) return new Date().toISOString().slice(0, 10)
    const y = dt.getFullYear()
    const m = String(dt.getMonth() + 1).padStart(2, '0')
    const day = String(dt.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
}

export function toInputDate(value: Date): string {
    const y = value.getFullYear()
    const m = String(value.getMonth() + 1).padStart(2, '0')
    const d = String(value.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
}

/** Период по умолчанию: 30 дней назад → вчера. */
export function defaultBacktestPeriod(): { fromDate: string; toDate: string } {
    const today = new Date()
    const to = new Date(today.getFullYear(), today.getMonth(), today.getDate())
    to.setDate(to.getDate() - 1)
    const from = new Date(to)
    from.setDate(from.getDate() - 30)
    return { fromDate: toInputDate(from), toDate: toInputDate(to) }
}

export function defaultTestName(market: TestingMarket): string {
    const label = market === 'crypto' ? 'ByBit' : 'MOEX'
    const d = new Date().toLocaleDateString('ru-RU')
    return `Бэктест ${label} ${d}`
}

export function clampDateToToday(v: string): string {
    if (!v) return v
    const d = new Date(v)
    if (!Number.isFinite(d.getTime())) return v
    const now = new Date()
    const max = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999)
    return d.getTime() > max.getTime() ? toInputDate(max) : v
}

export function normalizeBacktestResult(payload: unknown): RobotHistoryBacktestResult {
    const p = (payload || {}) as Record<string, unknown>
    return {
        run_id: p.run_id as number | undefined,
        initial_capital: Number(p.initial_capital ?? 0),
        final_equity: Number(p.final_equity ?? 0),
        total_return_percent: Number(p.total_return_percent ?? 0),
        max_drawdown_percent: p.max_drawdown_percent != null ? Number(p.max_drawdown_percent) : null,
        trades: Array.isArray(p.trades) ? (p.trades as RobotHistoryBacktestResult['trades']) : [],
        equity_curve: Array.isArray(p.equity_curve) ? (p.equity_curve as RobotHistoryBacktestResult['equity_curve']) : [],
        stages: Array.isArray(p.stages) ? (p.stages as string[]) : [],
        history_stats: p.history_stats as RobotHistoryBacktestResult['history_stats'],
    }
}

export function fmtErr(e: unknown): string {
    const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
    const d = err?.response?.data?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join('; ')
    if (d && typeof d === 'object') return JSON.stringify(d)
    return err?.message ?? String(e)
}
