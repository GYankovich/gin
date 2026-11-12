import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Props = {
    value: string
    onChange: (value: string) => void
    className?: string
    disabled?: boolean
    'aria-label'?: string
}

const ITEM_H = 36
const VISIBLE = 5
const PAD = Math.floor(VISIBLE / 2)
const WHEEL_H = ITEM_H * VISIBLE

const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)

function pad2(n: number): string {
    return String(n).padStart(2, '0')
}

function parseHm(raw: string): { hour: number; minute: number } {
    const [h, m] = String(raw || '').split(':')
    const hour = Math.min(23, Math.max(0, Number.parseInt(h || '0', 10) || 0))
    const minute = Math.min(59, Math.max(0, Number.parseInt(m || '0', 10) || 0))
    return { hour, minute }
}

function indexFromScroll(scrollTop: number, maxIndex: number): number {
    return Math.min(maxIndex, Math.max(0, Math.round(scrollTop / ITEM_H)))
}

type WheelProps = {
    values: number[]
    initial: number
    ariaLabel: string
    onSettle: (next: number) => void
}

function Wheel({ values, initial, ariaLabel, onSettle }: WheelProps) {
    const scrollerRef = useRef<HTMLDivElement>(null)
    const settlingRef = useRef(false)
    const timerRef = useRef<number | null>(null)
    const lastEmittedRef = useRef(initial)
    const onSettleRef = useRef(onSettle)
    const [active, setActive] = useState(initial)
    const dragRef = useRef<{ pointerId: number; startY: number; startTop: number } | null>(null)

    onSettleRef.current = onSettle

    const scrollToIndex = useCallback((next: number, behavior: ScrollBehavior = 'auto') => {
        const el = scrollerRef.current
        if (!el) return
        settlingRef.current = true
        el.scrollTo({ top: next * ITEM_H, behavior })
        window.setTimeout(() => {
            settlingRef.current = false
        }, behavior === 'smooth' ? 240 : 40)
    }, [])

    const emit = useCallback((next: number) => {
        setActive(next)
        if (lastEmittedRef.current === next) return
        lastEmittedRef.current = next
        onSettleRef.current(next)
    }, [])

    useLayoutEffect(() => {
        lastEmittedRef.current = initial
        setActive(initial)
        scrollToIndex(initial, 'auto')
        // Remounted via key on each open; do not re-sync when parent draft updates.
        // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only
    }, [])

    const settleFromScroll = useCallback(() => {
        const el = scrollerRef.current
        if (!el) return
        const next = indexFromScroll(el.scrollTop, values.length - 1)
        const snapped = next * ITEM_H
        if (Math.abs(el.scrollTop - snapped) > 0.5) {
            settlingRef.current = true
            el.scrollTo({ top: snapped, behavior: 'smooth' })
            window.setTimeout(() => {
                settlingRef.current = false
            }, 200)
        }
        emit(next)
    }, [emit, values.length])

    const handleScroll = () => {
        if (settlingRef.current || dragRef.current) return
        const el = scrollerRef.current
        if (!el) return
        const live = indexFromScroll(el.scrollTop, values.length - 1)
        setActive(live)
        if (timerRef.current != null) window.clearTimeout(timerRef.current)
        timerRef.current = window.setTimeout(() => {
            settleFromScroll()
        }, 90)
    }

    useEffect(() => () => {
        if (timerRef.current != null) window.clearTimeout(timerRef.current)
    }, [])

    const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
        // Custom drag only for mouse; touch/pen use native overflow scrolling.
        if (event.pointerType !== 'mouse' || event.button !== 0) return
        const el = scrollerRef.current
        if (!el) return
        dragRef.current = {
            pointerId: event.pointerId,
            startY: event.clientY,
            startTop: el.scrollTop,
        }
        el.setPointerCapture(event.pointerId)
        if (timerRef.current != null) window.clearTimeout(timerRef.current)
    }

    const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
        const drag = dragRef.current
        const el = scrollerRef.current
        if (!drag || drag.pointerId !== event.pointerId || !el) return
        el.scrollTop = drag.startTop - (event.clientY - drag.startY)
        setActive(indexFromScroll(el.scrollTop, values.length - 1))
    }

    const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
        const drag = dragRef.current
        const el = scrollerRef.current
        if (!drag || drag.pointerId !== event.pointerId) return
        dragRef.current = null
        if (el?.hasPointerCapture(event.pointerId)) {
            el.releasePointerCapture(event.pointerId)
        }
        settleFromScroll()
    }

    return (
        <div className="gin-time-wheel">
            <div
                ref={scrollerRef}
                className="gin-time-wheel__scroller"
                role="listbox"
                aria-label={ariaLabel}
                aria-activedescendant={`${ariaLabel}-${active}`}
                tabIndex={0}
                onScroll={handleScroll}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
            >
                <div className="gin-time-wheel__spacer" aria-hidden style={{ height: PAD * ITEM_H }} />
                {values.map(item => (
                    <div
                        key={item}
                        id={`${ariaLabel}-${item}`}
                        role="option"
                        aria-selected={item === active}
                        className={[
                            'gin-time-wheel__item',
                            item === active ? 'gin-time-wheel__item--active' : '',
                        ].filter(Boolean).join(' ')}
                        style={{ height: ITEM_H }}
                        onClick={() => {
                            scrollToIndex(item, 'smooth')
                            emit(item)
                        }}
                    >
                        {pad2(item)}
                    </div>
                ))}
                <div className="gin-time-wheel__spacer" aria-hidden style={{ height: PAD * ITEM_H }} />
            </div>
        </div>
    )
}

export function TimeSelect({
    value,
    onChange,
    className = '',
    disabled = false,
    'aria-label': ariaLabel,
}: Props) {
    const parsed = useMemo(() => parseHm(value), [value])
    const [open, setOpen] = useState(false)
    const [draftHour, setDraftHour] = useState(parsed.hour)
    const [draftMinute, setDraftMinute] = useState(parsed.minute)
    const [openToken, setOpenToken] = useState(0)
    const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({})
    const triggerRef = useRef<HTMLButtonElement>(null)
    const dropdownRef = useRef<HTMLDivElement>(null)
    const draftRef = useRef({ hour: parsed.hour, minute: parsed.minute })
    const openRef = useRef(false)

    const commit = useCallback((nextHour: number, nextMinute: number) => {
        onChange(`${pad2(nextHour)}:${pad2(nextMinute)}`)
    }, [onChange])

    const updateDropdownPosition = useCallback(() => {
        const trigger = triggerRef.current
        if (!trigger) return
        const rect = trigger.getBoundingClientRect()
        const gap = 6
        const width = Math.max(rect.width, 196)
        const height = WHEEL_H + 52
        const spaceBelow = window.innerHeight - rect.bottom - gap
        const spaceAbove = rect.top - gap
        const openUp = spaceBelow < height && spaceAbove > spaceBelow
        const left = Math.min(window.innerWidth - 8 - width, Math.max(8, rect.left))

        setDropdownStyle({
            position: 'fixed',
            left,
            width,
            ...(openUp
                ? { top: 'auto', bottom: window.innerHeight - rect.top + gap }
                : { bottom: 'auto', top: rect.bottom + gap }),
        })
    }, [])

    useLayoutEffect(() => {
        if (open && !openRef.current) {
            draftRef.current = { hour: parsed.hour, minute: parsed.minute }
            setDraftHour(parsed.hour)
            setDraftMinute(parsed.minute)
            setOpenToken(prev => prev + 1)
            updateDropdownPosition()
        }
        openRef.current = open
    }, [open, parsed.hour, parsed.minute, updateDropdownPosition])

    useEffect(() => {
        if (!open) return
        const onLayout = (event: Event) => {
            const target = event.target
            if (target instanceof Node && dropdownRef.current?.contains(target)) return
            updateDropdownPosition()
        }
        window.addEventListener('resize', updateDropdownPosition)
        window.addEventListener('scroll', onLayout, true)
        return () => {
            window.removeEventListener('resize', updateDropdownPosition)
            window.removeEventListener('scroll', onLayout, true)
        }
    }, [open, updateDropdownPosition])

    useEffect(() => {
        if (!open) return
        const onPointerDown = (event: MouseEvent) => {
            const target = event.target as Node
            if (triggerRef.current?.contains(target)) return
            if (dropdownRef.current?.contains(target)) return
            const { hour, minute } = draftRef.current
            commit(hour, minute)
            setOpen(false)
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false)
            if (event.key === 'Enter') {
                const { hour, minute } = draftRef.current
                commit(hour, minute)
                setOpen(false)
            }
        }
        document.addEventListener('mousedown', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        return () => {
            document.removeEventListener('mousedown', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [open, commit])

    return (
        <div className={['gin-time-select', open ? 'gin-time-select--open' : '', className].filter(Boolean).join(' ')}>
            <button
                ref={triggerRef}
                type="button"
                className="gin-time-select__trigger"
                disabled={disabled}
                aria-label={ariaLabel}
                aria-haspopup="dialog"
                aria-expanded={open}
                onClick={() => {
                    if (disabled) return
                    setOpen(prev => !prev)
                }}
            >
                <span className="gin-time-select__value">{`${pad2(parsed.hour)}:${pad2(parsed.minute)}`}</span>
                <span className={`gin-time-select__arrow ${open ? 'gin-time-select__arrow--up' : ''}`} aria-hidden>
                    <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                        <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                </span>
            </button>

            {open
                ? createPortal(
                    <div
                        ref={dropdownRef}
                        className="gin-time-select__dropdown gin-time-select__dropdown--ios"
                        style={dropdownStyle}
                        role="dialog"
                        aria-label={ariaLabel || 'Выбор времени'}
                    >
                        <div className="gin-time-select__wheels" style={{ height: WHEEL_H }}>
                            <div className="gin-time-select__highlight" aria-hidden />
                            <div className="gin-time-select__fade gin-time-select__fade--top" aria-hidden />
                            <div className="gin-time-select__fade gin-time-select__fade--bottom" aria-hidden />
                            <Wheel
                                key={`h-${openToken}`}
                                values={HOURS}
                                initial={draftHour}
                                ariaLabel="Часы"
                                onSettle={next => {
                                    draftRef.current = { ...draftRef.current, hour: next }
                                    setDraftHour(next)
                                    commit(next, draftRef.current.minute)
                                }}
                            />
                            <div className="gin-time-select__colon" aria-hidden>:</div>
                            <Wheel
                                key={`m-${openToken}`}
                                values={MINUTES}
                                initial={draftMinute}
                                ariaLabel="Минуты"
                                onSettle={next => {
                                    draftRef.current = { ...draftRef.current, minute: next }
                                    setDraftMinute(next)
                                    commit(draftRef.current.hour, next)
                                }}
                            />
                        </div>
                        <button
                            type="button"
                            className="gin-time-select__done"
                            onClick={() => {
                                const { hour, minute } = draftRef.current
                                commit(hour, minute)
                                setOpen(false)
                            }}
                        >
                            Готово
                        </button>
                    </div>,
                    document.body,
                )
                : null}
        </div>
    )
}
