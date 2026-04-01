import React, { useState, useRef, useEffect, useCallback } from 'react'

export interface SelectOption {
    value: string | number
    label: string
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
}: SelectProps) {
    const [open, setOpen] = useState(false)
    const [search, setSearch] = useState('')
    const containerRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    const selected = options.find(o => String(o.value) === String(value))

    const filtered = search
        ? options.filter(o => o.label.toLowerCase().includes(search.toLowerCase()))
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

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false)
                setSearch('')
            }
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
            <div className="gin-select__trigger" onClick={handleToggle}>
                {selected ? (
                    <span className="gin-select__value">
                        {selected.icon && <span className="gin-select__icon">{selected.icon}</span>}
                        {selected.label}
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

            {open && (
                <div className="gin-select__dropdown">
                    {options.length > 6 && (
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
                                {opt.label}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
