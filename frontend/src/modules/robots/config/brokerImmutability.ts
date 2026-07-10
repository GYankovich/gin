/** Сообщение при попытке сменить broker_type у существующего робота (target §15.3). */
export const BROKER_CHANGE_BLOCKED_MESSAGE =
    'Для смены брокера создайте нового робота'

export function isBrokerTypeLocked(robotId: number | null | undefined): boolean {
    return robotId != null && Number(robotId) > 0
}

export function brokerTypeLabel(broker: string): string {
    const key = String(broker || 'tinvest').trim().toLowerCase()
    if (key === 'tinvest') return 'T-Invest'
    if (key === 'bybit') return 'ByBit'
    if (key === 'sandbox') return 'Sandbox'
    return String(broker || 'tinvest')
}

export function isBrokerTypeConflictError(err: unknown): boolean {
    const ax = err as { response?: { status?: number; data?: { detail?: unknown } } }
    if (ax.response?.status !== 409) return false
    const detail = String(ax.response.data?.detail ?? '').toLowerCase()
    return detail.includes('broker_type') || detail.includes('брокер')
}
