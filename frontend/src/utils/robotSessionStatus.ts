import type { Robot } from '@/types/robot'

/** Краткий статус последней сессии для карточки в списке роботов. */
export function formatRobotSessionStatus(r: Robot, opts?: { noEmoji?: boolean }): string {
    if (r.last_error) {
        const msg = r.last_error.length > 56 ? `${r.last_error.slice(0, 56)}…` : r.last_error
        return `Ошибка: ${msg}`
    }
    const iso = r.last_started || r.date_modification
    if (!iso) return 'Цикл не запускался'
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return 'Цикл не запускался'
    const mins = Math.max(0, Math.round((Date.now() - t) / 60_000))
    let text: string
    if (mins < 1) text = 'Последний цикл: только что'
    else if (mins < 60) text = `Последний цикл: ${mins} мин назад`
    else {
        const hours = Math.round(mins / 60)
        if (hours < 48) text = `Последний цикл: ${hours} ч назад`
        else {
            const days = Math.round(hours / 24)
            text = `Последний цикл: ${days} дн. назад`
        }
    }
    if (opts?.noEmoji) return text
    return `${text} ✅`
}
