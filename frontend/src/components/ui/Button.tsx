import React from 'react'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
    size?: 'sm' | 'md' | 'lg'
    glow?: boolean
    loading?: boolean
}

export function Button({
    variant = 'primary',
    size = 'md',
    glow = false,
    loading = false,
    children,
    className = '',
    disabled,
    ...rest
}: ButtonProps) {
    const cls = [
        'btn',
        `btn--${variant}`,
        `btn--${size}`,
        glow && 'btn--glow',
        loading && 'btn--loading',
        className,
    ].filter(Boolean).join(' ')

    return (
        <button className={cls} disabled={disabled || loading} {...rest}>
            {loading && <span className="btn__spinner" />}
            {children}
        </button>
    )
}
