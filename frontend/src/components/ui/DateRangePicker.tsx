import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Select } from '@/components/ui/Select'

interface DateRangePickerProps {
    fromValue: string
    toValue: string
    onFromChange: (value: string) => void
    onToChange: (value: string) => void
    fromLabel?: string
    toLabel?: string
}

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function parseDate(v: string): Date {
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return new Date()
    return d
}

function pad(n: number): string {
    return String(n).padStart(2, '0')
}

function toLocalDateTime(d: Date): string {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatRuDate(v: string): string {
    if (!v) return ''
    const d = parseDate(v)
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}

function monthGrid(cursor: Date): Array<{ day: number; inMonth: boolean }> {
    const firstDay = (cursor.getDay() + 6) % 7
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate()
    const cells: Array<{ day: number; inMonth: boolean }> = []
    for (let i = 0; i < firstDay; i++) cells.push({ day: 0, inMonth: false })
    for (let i = 1; i <= daysInMonth; i++) cells.push({ day: i, inMonth: true })
    while (cells.length % 7 !== 0) cells.push({ day: 0, inMonth: false })
    return cells
}

export function DateRangePicker({
    fromValue,
    toValue,
    onFromChange,
    onToChange,
    fromLabel = 'С',
    toLabel = 'По',
}: DateRangePickerProps) {
    const rootRef = useRef<HTMLDivElement>(null)
    const [open, setOpen] = useState(false)
    const fromDate = parseDate(fromValue)
    const toDate = parseDate(toValue)
    const [cursor, setCursor] = useState(new Date(fromDate.getFullYear(), fromDate.getMonth(), 1))
    const [pickPhase, setPickPhase] = useState<'from' | 'to'>('from')
    const years = useMemo(() => {
        const now = new Date().getFullYear()
        const out: number[] = []
        for (let y = 2010; y <= now; y++) out.push(y)
        return out
    }, [])

    useEffect(() => {
        const onDocClick = (e: MouseEvent) => {
            if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
        }
        document.addEventListener('mousedown', onDocClick)
        return () => document.removeEventListener('mousedown', onDocClick)
    }, [])

    const pick = (day: number) => {
        if (!day) return
        const picked = new Date(cursor.getFullYear(), cursor.getMonth(), day, fromDate.getHours(), fromDate.getMinutes())
        if (pickPhase === 'from') {
            onFromChange(toLocalDateTime(picked))
            if (picked.getTime() > toDate.getTime()) onToChange(toLocalDateTime(picked))
            setPickPhase('to')
        } else {
            if (picked.getTime() < fromDate.getTime()) {
                onToChange(toLocalDateTime(fromDate))
                onFromChange(toLocalDateTime(picked))
            } else {
                onToChange(toLocalDateTime(picked))
            }
            setPickPhase('from')
        }
    }
    const grid = monthGrid(cursor)
    const yOptions = years.map(y => ({ value: String(y), label: String(y) }))
    const periodText = fromValue && toValue
        ? `${formatRuDate(fromValue)} - ${formatRuDate(toValue)}`
        : fromValue
            ? `${formatRuDate(fromValue)} - ...`
            : toValue
                ? `... - ${formatRuDate(toValue)}`
                : 'Выберите период'

    return (
        <div className="form-group" ref={rootRef} style={{ position: 'relative' }}>
            <label className="form-label">{fromLabel} - {toLabel}</label>
            <button type="button" className="form-input date-popover-trigger" onClick={() => setOpen(v => !v)}>
                {periodText}
            </button>
            {open && (
                <div className="date-popover date-popover-range">
                    <div className="date-popover__head">
                        <button type="button" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>◀</button>
                        <div className="date-popover-range__head-center">
                            <span>{MONTHS[cursor.getMonth()]}</span>
                            <Select
                                options={yOptions}
                                value={String(cursor.getFullYear())}
                                onChange={v => setCursor(new Date(Number(v), cursor.getMonth(), 1))}
                                size="sm"
                                className="date-year-select"
                                searchable={false}
                            />
                        </div>
                        <button type="button" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>▶</button>
                    </div>
                    <div className="date-popover__grid date-popover__grid--week">{WEEKDAYS.map(w => <div key={w}>{w}</div>)}</div>
                    <div className="date-popover__grid">
                        {grid.map((c, i) => {
                            if (!c.inMonth) return <button key={`x-${i}`} type="button" className="date-popover__day date-popover__day--muted" />
                            const d = new Date(cursor.getFullYear(), cursor.getMonth(), c.day, 12, 0, 0, 0)
                            const inRange = d.getTime() >= new Date(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate(), 12, 0, 0, 0).getTime()
                                && d.getTime() <= new Date(toDate.getFullYear(), toDate.getMonth(), toDate.getDate(), 12, 0, 0, 0).getTime()
                            const isEdge = d.getTime() === new Date(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate(), 12, 0, 0, 0).getTime()
                                || d.getTime() === new Date(toDate.getFullYear(), toDate.getMonth(), toDate.getDate(), 12, 0, 0, 0).getTime()
                            return (
                                <button
                                    key={`d-${c.day}-${i}`}
                                    type="button"
                                    className={`date-popover__day ${inRange ? 'date-popover__day--range' : ''} ${isEdge ? 'date-popover__day--active' : ''}`}
                                    onClick={() => pick(c.day)}
                                >
                                    {c.day}
                                </button>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}
