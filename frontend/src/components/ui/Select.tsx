///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiSelect [1]
///@ Исходный модуль `frontend/src/components/ui/Select.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'

export interface SelectOption {
    value: string | number
    label: string
    /** Optional trailing meta (e.g. platform tag). */
    tag?: string
    icon?: React.ReactNode
    disabled?: boolean
}

interface SelectProps {
    options: SelectOption[]
    value: string | number | null | undefined
    onChange: (value: string) => void
    placeholder?: string
    disabled?: boolean
    size?: 'sm' | 'md'
    className?: string
    style?: React.CSSProperties
    searchable?: boolean
}

export function Select({
    options,
    value,
    onChange,
    placeholder = 'Выберите...',
    disabled = false,
    size = 'md',
    className = '',
    style,
    searchable = true,
}: SelectProps) {
    const [open, setOpen] = useState(false)
    const [search, setSearch] = useState('')
    const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({})
    const [cyberDropdown, setCyberDropdown] = useState(false)
    const [aboveModal, setAboveModal] = useState(false)
    const containerRef = useRef<HTMLDivElement>(null)
    const triggerRef = useRef<HTMLDivElement>(null)
    const dropdownRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    const updateDropdownPosition = useCallback(() => {
        const trigger = triggerRef.current
        if (!trigger) return
        const rect = trigger.getBoundingClientRect()
        const gap = 4
        const maxHeight = 280
        const spaceBelow = window.innerHeight - rect.bottom - gap
        const spaceAbove = rect.top - gap
        const openUp = spaceBelow < 160 && spaceAbove > spaceBelow
        const height = Math.max(80, Math.min(maxHeight, openUp ? spaceAbove : spaceBelow))

        setDropdownStyle({
            position: 'fixed',
            left: rect.left,
            width: rect.width,
            maxHeight: height,
            ...(openUp
                ? { top: 'auto', bottom: window.innerHeight - rect.top + gap }
                : { bottom: 'auto', top: rect.bottom + gap }),
        })
    }, [])

    const selected = options.find(o => String(o.value) === String(value))

    const filtered = search
        ? options.filter(o => {
            const q = search.toLowerCase()
            return (
                o.label.toLowerCase().includes(q)
                || (o.tag ? o.tag.toLowerCase().includes(q) : false)
            )
        })
        : options

    const handleToggle = () => {
        if (disabled) return
        setOpen(prev => {
            if (!prev) {
                setSearch('')
                setTimeout(() => inputRef.current?.focus(), 10)
            }
            return !prev
        })
    }

    const handleSelect = (opt: SelectOption) => {
        if (opt.disabled) return
        onChange(String(opt.value))
        setOpen(false)
        setSearch('')
    }

    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            setOpen(false)
            setSearch('')
        }
    }, [])

    useLayoutEffect(() => {
        if (!open) return
        const el = containerRef.current
        setCyberDropdown(!!el?.closest('.step-editor-panel, .cyber-select-wrap'))
        setAboveModal(!!el?.closest('.modal-backdrop, .modal'))
        updateDropdownPosition()
    }, [open, updateDropdownPosition])

    useEffect(() => {
        if (!open) return
        const onLayout = () => updateDropdownPosition()
        window.addEventListener('resize', onLayout)
        window.addEventListener('scroll', onLayout, true)
        return () => {
            window.removeEventListener('resize', onLayout)
            window.removeEventListener('scroll', onLayout, true)
        }
    }, [open, updateDropdownPosition])

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as Node
            if (triggerRef.current?.contains(target)) return
            if (dropdownRef.current?.contains(target)) return
            setOpen(false)
            setSearch('')
        }
        document.addEventListener('mousedown', handleClickOutside)
        document.addEventListener('keydown', handleKeyDown)
        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [handleKeyDown])

    return (
        <div
            ref={containerRef}
            className={`gin-select ${open ? 'gin-select--open' : ''} ${disabled ? 'gin-select--disabled' : ''} gin-select--${size} ${className}`}
            style={style}
        >
            <div ref={triggerRef} className="gin-select__trigger" onClick={handleToggle}>
                {selected ? (
                    <span className="gin-select__value">
                        {selected.icon && <span className="gin-select__icon">{selected.icon}</span>}
                        <span className="gin-select__value-text">{selected.label}</span>
                        {selected.tag ? (
                            <span className="dashboard-settings-row__tag">{selected.tag}</span>
                        ) : null}
                    </span>
                ) : (
                    <span className="gin-select__placeholder">{placeholder}</span>
                )}
                <span className={`gin-select__arrow ${open ? 'gin-select__arrow--up' : ''}`}>
                    <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                        <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                </span>
            </div>

            {open &&
                createPortal(
                    <div
                        ref={dropdownRef}
                        className={`gin-select__dropdown gin-select__dropdown--portal${cyberDropdown ? ' gin-select__dropdown--cyber' : ''}${aboveModal ? ' gin-select__dropdown--above-modal' : ''}`}
                        style={dropdownStyle}
                    >
                        {searchable && options.length > 6 && (
                            <div className="gin-select__search-wrap">
                                <input
                                    ref={inputRef}
                                    className="gin-select__search"
                                    type="text"
                                    placeholder="Поиск..."
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    onClick={e => e.stopPropagation()}
                                />
                            </div>
                        )}
                        <div className="gin-select__options">
                            {filtered.length === 0 && (
                                <div className="gin-select__empty">Нет результатов</div>
                            )}
                            {filtered.map(opt => (
                                <div
                                    key={opt.value}
                                    className={`gin-select__option ${String(opt.value) === String(value) ? 'gin-select__option--active' : ''} ${opt.disabled ? 'gin-select__option--disabled' : ''}`}
                                    onClick={() => handleSelect(opt)}
                                >
                                    {opt.icon && <span className="gin-select__icon">{opt.icon}</span>}
                                    <span className="gin-select__option-label">{opt.label}</span>
                                    {opt.tag ? (
                                        <span className="dashboard-settings-row__tag">{opt.tag}</span>
                                    ) : null}
                                </div>
                            ))}
                        </div>
                    </div>,
                    document.body,
                )}
        </div>
    )
}
