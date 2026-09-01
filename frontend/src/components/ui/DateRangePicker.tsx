///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiDaterangepicker [1]
///@ Исходный модуль `frontend/src/components/ui/DateRangePicker.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Select } from '@/components/ui/Select'

interface DateRangePickerProps {
    fromValue: string
    toValue: string
    onFromChange: (value: string) => void
    onToChange: (value: string) => void
    fromLabel?: string
    toLabel?: string
    /** When false, the form-label above the trigger is omitted. */
    showLabel?: boolean
    /** popover — read-only trigger; fields — one text field with inline clear. */
    variant?: 'popover' | 'fields'
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

function formatRangeDisplay(fromValue: string, toValue: string): string {
    if (fromValue && toValue) return `${formatRuDate(fromValue)} — ${formatRuDate(toValue)}`
    if (fromValue) return `${formatRuDate(fromValue)} — `
    if (toValue) return `— ${formatRuDate(toValue)}`
    return ''
}

function parseRuDateToken(token: string): string | null {
    const t = token.trim()
    if (!t) return null
    const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(t)
    if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`
    const ru = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(t)
    if (ru) return `${ru[3]}-${pad(Number(ru[2]))}-${pad(Number(ru[1]))}`
    return null
}

function parseRangeText(text: string): { from: string; to: string } | null {
    const trimmed = text.trim()
    if (!trimmed) return null
    const parts = trimmed.split(/\s*[—–-]\s*/)
    if (parts.length !== 2) return null
    const from = parseRuDateToken(parts[0])
    const to = parseRuDateToken(parts[1])
    if (!from || !to) return null
    return from <= to ? { from, to } : { from: to, to: from }
}

function fromIsoDate(iso: string): string {
    return iso ? `${iso}T00:00` : ''
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
    showLabel = true,
    variant = 'popover',
}: DateRangePickerProps) {
    const rootRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const popoverRef = useRef<HTMLDivElement>(null)
    const [open, setOpen] = useState(false)
    const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({})
    const [draft, setDraft] = useState('')
    const [editing, setEditing] = useState(false)
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
        if (!editing) {
            setDraft(formatRangeDisplay(fromValue, toValue))
        }
    }, [fromValue, toValue, editing])

    const updatePopoverPosition = useCallback(() => {
        const trigger = variant === 'fields' ? inputRef.current : triggerRef.current
        if (!trigger) return
        const rect = trigger.getBoundingClientRect()
        const gap = 6
        const width = Math.min(280, window.innerWidth - 24)
        let left = rect.left
        if (left + width > window.innerWidth - 12) {
            left = window.innerWidth - width - 12
        }
        left = Math.max(12, left)
        const spaceBelow = window.innerHeight - rect.bottom - gap
        const openUp = spaceBelow < 300 && rect.top > spaceBelow
        setPopoverStyle({
            position: 'fixed',
            left,
            width,
            ...(openUp
                ? { bottom: window.innerHeight - rect.top + gap, top: 'auto' }
                : { top: rect.bottom + gap, bottom: 'auto' }),
        })
    }, [variant])

    useLayoutEffect(() => {
        if (!open) return
        updatePopoverPosition()
    }, [open, updatePopoverPosition])

    useEffect(() => {
        if (!open) return
        const onLayout = () => updatePopoverPosition()
        window.addEventListener('resize', onLayout)
        window.addEventListener('scroll', onLayout, true)
        return () => {
            window.removeEventListener('resize', onLayout)
            window.removeEventListener('scroll', onLayout, true)
        }
    }, [open, updatePopoverPosition])

    useEffect(() => {
        const onDocClick = (e: MouseEvent) => {
            const target = e.target as Node
            if (rootRef.current?.contains(target)) return
            if (popoverRef.current?.contains(target)) return
            setOpen(false)
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
            setOpen(false)
        }
    }
    const commitDraft = () => {
        setEditing(false)
        if (!draft.trim()) {
            onFromChange('')
            onToChange('')
            setDraft('')
            return
        }
        const parsed = parseRangeText(draft)
        if (!parsed) {
            setDraft(formatRangeDisplay(fromValue, toValue))
            return
        }
        onFromChange(fromIsoDate(parsed.from))
        onToChange(fromIsoDate(parsed.to))
        setDraft(formatRangeDisplay(fromIsoDate(parsed.from), fromIsoDate(parsed.to)))
    }
    const grid = monthGrid(cursor)
    const yOptions = years.map(y => ({ value: String(y), label: String(y) }))
    const periodText = fromValue && toValue
        ? `${formatRuDate(fromValue)} — ${formatRuDate(toValue)}`
        : fromValue
            ? `${formatRuDate(fromValue)} — ...`
            : toValue
                ? `... — ${formatRuDate(toValue)}`
                : 'Выберите период'

    const calendarPopover = open ? createPortal(
        <div
            ref={popoverRef}
            className="date-popover date-popover-range date-popover--portal"
            style={popoverStyle}
        >
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
        </div>,
        document.body,
    ) : null

    const hasValue = Boolean(fromValue || toValue)

    const handleClear = (e: React.MouseEvent<HTMLButtonElement>) => {
        e.preventDefault()
        e.stopPropagation()
        setEditing(false)
        setOpen(false)
        onFromChange('')
        onToChange('')
        setDraft('')
    }

    const openCalendar = () => {
        setOpen(true)
        updatePopoverPosition()
    }

    if (variant === 'fields') {
        return (
            <div className="form-group date-range-picker date-range-picker--fields" ref={rootRef}>
                {showLabel ? <label className="form-label">{fromLabel} — {toLabel}</label> : null}
                <div className={`date-range-picker__combo${hasValue ? ' date-range-picker__combo--has-clear' : ''}`}>
                    <input
                        ref={inputRef}
                        type="text"
                        className="form-input date-range-picker__input"
                        value={draft}
                        placeholder="дд.мм.гггг — дд.мм.гггг"
                        aria-label={`${fromLabel} — ${toLabel}`}
                        aria-expanded={open}
                        onChange={e => {
                            setEditing(true)
                            setDraft(e.target.value)
                        }}
                        onFocus={() => setEditing(true)}
                        onBlur={commitDraft}
                        onClick={openCalendar}
                        onKeyDown={e => {
                            if (e.key === 'Enter') {
                                e.currentTarget.blur()
                            }
                            if (e.key === 'Escape') {
                                setOpen(false)
                            }
                        }}
                    />
                    {hasValue ? (
                        <button
                            type="button"
                            className="date-range-picker__clear"
                            aria-label="Сбросить период"
                            onMouseDown={handleClear}
                        >
                            ×
                        </button>
                    ) : null}
                </div>
                {calendarPopover}
            </div>
        )
    }

    return (
        <div className="form-group date-range-picker date-range-picker--popover" ref={rootRef} style={{ position: 'relative' }}>
            {showLabel && <label className="form-label">{fromLabel} - {toLabel}</label>}
            <button
                ref={triggerRef}
                type="button"
                className="form-input date-popover-trigger"
                aria-label={showLabel ? undefined : `${fromLabel} - ${toLabel}`}
                onClick={() => setOpen(v => !v)}
            >
                {periodText}
            </button>
            {calendarPopover}
        </div>
    )
}
