///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiCombobox [1]
///@ Исходный модуль `frontend/src/components/ui/Combobox.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { SelectOption } from '@/components/ui/Select'

export type ComboboxOption = SelectOption

interface ComboboxProps {
    options: ComboboxOption[]
    value: string | number | null | undefined
    onChange: (value: string) => void
    placeholder?: string
    disabled?: boolean
    size?: 'sm' | 'md'
    className?: string
    style?: React.CSSProperties
    /** Filter dropdown options by current draft (default true). */
    filterOptions?: boolean
    /** Normalize value when committing (blur / Enter / pick). */
    commitValue?: (raw: string) => string
    inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
    /** Prefer text + inputMode=numeric for free-form numbers (avoids number-input focus quirks). */
    type?: 'text' | 'number'
    min?: number
    max?: number
    step?: number | string
    'aria-label'?: string
}

export function Combobox({
    options,
    value,
    onChange,
    placeholder = 'Выберите или введите…',
    disabled = false,
    size = 'md',
    className = '',
    style,
    filterOptions = true,
    commitValue,
    inputMode,
    type = 'text',
    min,
    max,
    step,
    'aria-label': ariaLabel,
}: ComboboxProps) {
    const listboxId = useId()
    const [open, setOpen] = useState(false)
    const [draft, setDraft] = useState(() => (value == null ? '' : String(value)))
    const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({
        position: 'fixed',
        visibility: 'hidden',
    })
    const [cyberDropdown, setCyberDropdown] = useState(false)
    const [aboveModal, setAboveModal] = useState(false)
    const containerRef = useRef<HTMLDivElement>(null)
    const triggerRef = useRef<HTMLDivElement>(null)
    const dropdownRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)
    const focusedRef = useRef(false)
    const draftRef = useRef(draft)
    const pickingRef = useRef(false)

    const valueStr = value == null ? '' : String(value)
    draftRef.current = draft

    useEffect(() => {
        if (!focusedRef.current) setDraft(valueStr)
    }, [valueStr])

    const commit = useCallback(
        (raw: string) => {
            const next = commitValue ? commitValue(raw) : raw
            setDraft(next)
            draftRef.current = next
            if (next !== valueStr) onChange(next)
            return next
        },
        [commitValue, onChange, valueStr],
    )

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
            width: Math.max(rect.width, 160),
            maxHeight: height,
            visibility: 'visible',
            ...(openUp
                ? { top: 'auto', bottom: window.innerHeight - rect.top + gap }
                : { bottom: 'auto', top: rect.bottom + gap }),
        })
    }, [])

    const filtered = (() => {
        if (!filterOptions || !draft.trim()) return options
        const q = draft.trim().toLowerCase()
        return options.filter(
            o =>
                o.label.toLowerCase().includes(q) ||
                String(o.value).toLowerCase().includes(q),
        )
    })()

    const openDropdown = () => {
        if (disabled) return
        setOpen(true)
    }

    const closeDropdown = () => setOpen(false)

    const handleSelect = (opt: ComboboxOption) => {
        if (opt.disabled) return
        pickingRef.current = true
        commit(String(opt.value))
        closeDropdown()
        inputRef.current?.blur()
        window.setTimeout(() => {
            pickingRef.current = false
        }, 0)
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Escape') {
            e.preventDefault()
            setDraft(valueStr)
            draftRef.current = valueStr
            closeDropdown()
            inputRef.current?.blur()
            return
        }
        if (e.key === 'Enter') {
            e.preventDefault()
            commit(draftRef.current)
            closeDropdown()
            inputRef.current?.blur()
            return
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault()
            openDropdown()
        }
    }

    useLayoutEffect(() => {
        if (!open) return
        const el = containerRef.current
        setCyberDropdown(!!el?.closest('.step-editor-panel, .cyber-select-wrap'))
        setAboveModal(!!el?.closest('.modal-backdrop, .modal'))
        updateDropdownPosition()
    }, [open, updateDropdownPosition, filtered.length])

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
        if (!open) return
        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as Node
            if (triggerRef.current?.contains(target)) return
            if (dropdownRef.current?.contains(target)) return
            commit(draftRef.current)
            closeDropdown()
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [open, commit])

    const activeValue = draft.trim() || valueStr

    return (
        <div
            ref={containerRef}
            className={`gin-select gin-combobox ${open ? 'gin-select--open' : ''} ${disabled ? 'gin-select--disabled' : ''} gin-select--${size} ${className}`}
            style={style}
        >
            <div
                ref={triggerRef}
                className="gin-select__trigger gin-combobox__trigger"
                onMouseDown={e => {
                    // Keep focus in the input; don't let the wrapper steal it.
                    if (disabled) return
                    if (e.target === inputRef.current) return
                    e.preventDefault()
                    inputRef.current?.focus()
                    openDropdown()
                }}
            >
                <input
                    ref={inputRef}
                    className="gin-combobox__input"
                    type={type}
                    inputMode={inputMode}
                    min={type === 'number' ? min : undefined}
                    max={type === 'number' ? max : undefined}
                    step={type === 'number' ? step : undefined}
                    value={draft}
                    disabled={disabled}
                    placeholder={placeholder}
                    aria-label={ariaLabel}
                    role="combobox"
                    aria-autocomplete="list"
                    aria-expanded={open}
                    aria-controls={open ? listboxId : undefined}
                    autoComplete="off"
                    onFocus={() => {
                        focusedRef.current = true
                        openDropdown()
                    }}
                    onBlur={() => {
                        focusedRef.current = false
                        // Commit on blur, but do not close here — outside mousedown owns close,
                        // so a focus flicker in a tight form-row cannot eat the list.
                        if (pickingRef.current) return
                        window.setTimeout(() => {
                            if (pickingRef.current) return
                            if (triggerRef.current?.contains(document.activeElement)) return
                            if (dropdownRef.current?.contains(document.activeElement)) return
                            commit(draftRef.current)
                        }, 0)
                    }}
                    onChange={e => {
                        setDraft(e.target.value)
                        if (!open) openDropdown()
                    }}
                    onKeyDown={handleKeyDown}
                    onClick={e => {
                        e.stopPropagation()
                        openDropdown()
                    }}
                />
                <span
                    className={`gin-select__arrow gin-combobox__arrow ${open ? 'gin-select__arrow--up' : ''}`}
                    aria-hidden
                >
                    <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                        <path
                            d="M1 1L5 5L9 1"
                            stroke="currentColor"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </svg>
                </span>
            </div>

            {open &&
                createPortal(
                    <div
                        ref={dropdownRef}
                        id={listboxId}
                        role="listbox"
                        className={`gin-select__dropdown gin-select__dropdown--portal gin-combobox__dropdown${cyberDropdown ? ' gin-select__dropdown--cyber' : ''}${aboveModal ? ' gin-select__dropdown--above-modal' : ''}`}
                        style={dropdownStyle}
                    >
                        <div className="gin-select__options">
                            {filtered.length === 0 && (
                                <div className="gin-select__empty">
                                    {draft.trim()
                                        ? `Своё значение: ${draft.trim()}`
                                        : 'Нет вариантов'}
                                </div>
                            )}
                            {filtered.map(opt => (
                                <div
                                    key={String(opt.value)}
                                    role="option"
                                    aria-selected={String(opt.value) === activeValue}
                                    className={`gin-select__option ${String(opt.value) === activeValue ? 'gin-select__option--active' : ''} ${opt.disabled ? 'gin-select__option--disabled' : ''}`}
                                    onMouseDown={e => {
                                        e.preventDefault()
                                        pickingRef.current = true
                                    }}
                                    onClick={() => handleSelect(opt)}
                                >
                                    {opt.label}
                                </div>
                            ))}
                        </div>
                    </div>,
                    document.body,
                )}
        </div>
    )
}
