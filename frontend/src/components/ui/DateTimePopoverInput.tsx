///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiDatetimepopoverinput [1]
///@ Исходный модуль `frontend/src/components/ui/DateTimePopoverInput.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useEffect, useMemo, useRef, useState } from 'react'

interface Props {
    label: string
    value: string
    onChange: (value: string) => void
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

function parseLocalDateTime(v: string): Date {
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return new Date()
    return d
}

function pad(n: number): string {
    return String(n).padStart(2, '0')
}

function toLocalDateTimeString(d: Date): string {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function DateTimePopoverInput({ label, value, onChange }: Props) {
    const rootRef = useRef<HTMLDivElement>(null)
    const selected = useMemo(() => parseLocalDateTime(value), [value])
    const [open, setOpen] = useState(false)
    const [cursor, setCursor] = useState(new Date(selected.getFullYear(), selected.getMonth(), 1))
    const [time, setTime] = useState(`${pad(selected.getHours())}:${pad(selected.getMinutes())}`)

    useEffect(() => {
        setCursor(new Date(selected.getFullYear(), selected.getMonth(), 1))
        setTime(`${pad(selected.getHours())}:${pad(selected.getMinutes())}`)
    }, [value])

    useEffect(() => {
        const onClickOutside = (e: MouseEvent) => {
            if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
        }
        document.addEventListener('mousedown', onClickOutside)
        return () => document.removeEventListener('mousedown', onClickOutside)
    }, [])

    const firstDay = (cursor.getDay() + 6) % 7
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate()
    const cells: Array<{ day: number; inMonth: boolean }> = []
    for (let i = 0; i < firstDay; i++) cells.push({ day: 0, inMonth: false })
    for (let i = 1; i <= daysInMonth; i++) cells.push({ day: i, inMonth: true })
    while (cells.length % 7 !== 0) cells.push({ day: 0, inMonth: false })

    const pickDay = (day: number) => {
        if (!day) return
        const [hh, mm] = time.split(':').map(x => Number.parseInt(x || '0', 10))
        const d = new Date(cursor.getFullYear(), cursor.getMonth(), day, Number.isFinite(hh) ? hh : 0, Number.isFinite(mm) ? mm : 0)
        onChange(toLocalDateTimeString(d))
    }

    const applyTime = (nextTime: string) => {
        setTime(nextTime)
        const d = parseLocalDateTime(value)
        const [hh, mm] = nextTime.split(':').map(x => Number.parseInt(x || '0', 10))
        d.setHours(Number.isFinite(hh) ? hh : 0)
        d.setMinutes(Number.isFinite(mm) ? mm : 0)
        onChange(toLocalDateTimeString(d))
    }

    return (
        <div className="form-group" ref={rootRef}>
            <label className="form-label">{label}</label>
            <button type="button" className="form-input date-popover-trigger" onClick={() => setOpen(v => !v)}>
                {value.replace('T', ' ')}
            </button>
            {open && (
                <div className="date-popover">
                    <div className="date-popover__head">
                        <button type="button" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>◀</button>
                        <span>{MONTHS[cursor.getMonth()]} {cursor.getFullYear()}</span>
                        <button type="button" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>▶</button>
                    </div>
                    <div className="date-popover__grid date-popover__grid--week">{WEEKDAYS.map(w => <div key={w}>{w}</div>)}</div>
                    <div className="date-popover__grid">
                        {cells.map((c, i) => (
                            <button
                                key={`${c.day}-${i}`}
                                type="button"
                                className={`date-popover__day ${c.inMonth ? '' : 'date-popover__day--muted'} ${c.inMonth && c.day === selected.getDate() && cursor.getMonth() === selected.getMonth() && cursor.getFullYear() === selected.getFullYear() ? 'date-popover__day--active' : ''}`}
                                onClick={() => pickDay(c.day)}
                            >
                                {c.day || ''}
                            </button>
                        ))}
                    </div>
                    <div className="date-popover__time">
                        <span>Время</span>
                        <input type="time" value={time} onChange={e => applyTime(e.target.value)} />
                    </div>
                </div>
            )}
        </div>
    )
}
