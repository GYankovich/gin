/** Дни недели в `allowed_weekdays` / `weekdaysMask` (биты, пн = 1). */

export type WeekdayDef = {
    bit: number
    short: string
    label: string
}

export const WEEKDAYS: WeekdayDef[] = [
    { bit: 1, short: 'пн', label: 'Понедельник' },
    { bit: 2, short: 'вт', label: 'Вторник' },
    { bit: 4, short: 'ср', label: 'Среда' },
    { bit: 8, short: 'чт', label: 'Четверг' },
    { bit: 16, short: 'пт', label: 'Пятница' },
    { bit: 32, short: 'сб', label: 'Суббота' },
    { bit: 64, short: 'вс', label: 'Воскресенье' },
]

/** Все семь дней: 1+2+4+8+16+32+64 */
export const WEEKDAYS_MASK_FULL_WEEK = 127

export const WEEKDAY_FULL_WEEK_OPTION = {
    short: 'вся неделя',
    label: 'Вся неделя (пн–вс)',
    mask: WEEKDAYS_MASK_FULL_WEEK,
} as const

export function clampWeekdaysMask(raw: number): number {
    return Math.max(0, Math.min(127, Math.trunc(Number(raw) || 0)))
}

export function isFullWeekMask(mask: number): boolean {
    return clampWeekdaysMask(mask) === WEEKDAYS_MASK_FULL_WEEK
}

export function isWeekdaySelected(mask: number, bit: number): boolean {
    return (clampWeekdaysMask(mask) & bit) !== 0
}

export function toggleWeekday(mask: number, bit: number, selected: boolean): number {
    const m = clampWeekdaysMask(mask)
    return selected ? m | bit : m & ~bit
}

export function toggleFullWeek(mask: number, selected: boolean): number {
    if (selected) return WEEKDAYS_MASK_FULL_WEEK
    return isFullWeekMask(mask) ? 0 : clampWeekdaysMask(mask)
}

/** Человекочитаемое описание выбранных дней: «вт–чт», «ср, чт», «вся неделя». */
export function formatWeekdaysMask(mask: number): string {
    const m = clampWeekdaysMask(mask)
    if (m === 0) return 'нет дней'
    if (isFullWeekMask(m)) return WEEKDAY_FULL_WEEK_OPTION.short

    const indices: number[] = []
    WEEKDAYS.forEach((d, i) => {
        if (m & d.bit) indices.push(i)
    })

    const parts: string[] = []
    let start = indices[0]
    let prev = indices[0]
    for (let i = 1; i <= indices.length; i++) {
        const cur = indices[i]
        if (cur === prev + 1) {
            prev = cur
            continue
        }
        if (start === prev) {
            parts.push(WEEKDAYS[start].short)
        } else {
            parts.push(`${WEEKDAYS[start].short}–${WEEKDAYS[prev].short}`)
        }
        start = cur
        prev = cur
    }
    return parts.join(', ')
}

export function weekdaysMaskHint(mask: number): string {
    const m = clampWeekdaysMask(mask)
    if (isFullWeekMask(m)) {
        return `Маска ${m} — все дни (пн+вт+ср+чт+пт+сб+вс)`
    }
    const selected = WEEKDAYS.filter(d => m & d.bit)
    const breakdown = selected.map(d => `${d.short}=${d.bit}`).join(' + ')
    return breakdown
        ? `Маска ${m} = ${breakdown} · ${formatWeekdaysMask(m)}`
        : `Маска 0 — робот не будет запускаться по расписанию`
}
