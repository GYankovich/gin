import type { ApiKeyItem, BrokerKind, TokenConnectionStatus } from '@/pages/settings/types'

export async function copyText(value: string): Promise<boolean> {
    const text = String(value || '').trim()
    if (!text) return false
    try {
        await navigator.clipboard.writeText(text)
        return true
    } catch {
        const area = document.createElement('textarea')
        area.value = text
        area.style.position = 'fixed'
        area.style.opacity = '0'
        document.body.appendChild(area)
        area.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(area)
        return ok
    }
}

export function detectBrokerKind(token: ApiKeyItem): BrokerKind {
    const typeName = String(token.token_type?.typeName || '').toLowerCase()
    const typeNum = Number(token.token_type?.type || 0)
    if (typeNum === 1 || typeName.includes('t-invest') || typeName.includes('tinvest') || typeName.includes('tinkoff')) {
        return 'tinvest'
    }
    if (typeNum === 2 || typeName.includes('bybit')) return 'bybit'
    if (typeName.includes('binance')) return 'binance'
    return 'other'
}

export function brokerLabel(kind: BrokerKind): string {
    if (kind === 'tinvest') return 'Т-Инвестиции'
    if (kind === 'bybit') return 'ByBit'
    if (kind === 'binance') return 'Binance'
    return 'Брокер'
}

export function brokerWrapClass(kind: BrokerKind): string {
    return `settings-token-wrap--${kind}`
}

export function tokenStatusWrapClass(status: TokenConnectionStatus): string {
    return `settings-token-wrap--status-${status}`
}

export function inferTokenRights(token: ApiKeyItem): { label: string; level: 'safe' | 'medium' | 'danger' } {
    const kind = detectBrokerKind(token)
    const desc = String(token.token_type?.typeDesc || '').toLowerCase()
    if (desc.includes('read') || desc.includes('чтен')) {
        return { label: 'Только чтение', level: 'safe' }
    }
    if (kind === 'bybit') {
        return { label: 'Торговля', level: 'medium' }
    }
    if (kind === 'tinvest') {
        return { label: 'Торговля', level: 'medium' }
    }
    return { label: 'Полный доступ', level: 'danger' }
}

export function connectionStatusLabel(status: TokenConnectionStatus): string {
    if (status === 'active') return 'Активен'
    if (status === 'expired') return 'Истекший'
    if (status === 'error') return 'Ошибка'
    if (status === 'inactive') return 'Неактивен'
    return 'Не проверен'
}

export function connectionStatusVariant(status: TokenConnectionStatus): 'up' | 'warn' | 'down' | 'neutral' {
    if (status === 'active') return 'up'
    if (status === 'expired') return 'down'
    if (status === 'error') return 'warn'
    if (status === 'inactive') return 'down'
    return 'neutral'
}

export function sortTokens(tokens: ApiKeyItem[]): ApiKeyItem[] {
    return [...tokens].sort((a, b) => {
        if (a.status !== b.status) return a.status === 1 ? -1 : 1
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
}

export function formatRelativeTime(iso: string | null | undefined): string | null {
    if (!iso) return null
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return null
    const diffMs = Date.now() - date.getTime()
    const mins = Math.floor(diffMs / 60_000)
    if (mins < 1) return 'только что'
    if (mins < 60) return `${mins} мин назад`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} ч назад`
    const days = Math.floor(hours / 24)
    if (days === 1) return 'вчера'
    if (days < 7) return `${days} дн назад`
    return date.toLocaleDateString('ru-RU')
}

export function formatLoginTime(iso: string | null | undefined): string {
    if (!iso) return '—'
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return '—'
    const today = new Date()
    const sameDay =
        date.getFullYear() === today.getFullYear()
        && date.getMonth() === today.getMonth()
        && date.getDate() === today.getDate()
    const time = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    return sameDay ? `сегодня ${time}` : `${date.toLocaleDateString('ru-RU')} ${time}`
}

export function tokenCountLabel(count: number): string {
    const mod10 = count % 10
    const mod100 = count % 100
    if (mod10 === 1 && mod100 !== 11) return `${count} токен`
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${count} токена`
    return `${count} токенов`
}
