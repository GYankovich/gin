import React from 'react'

interface BadgeProps {
    children: React.ReactNode
    variant?: 'cyan' | 'magenta' | 'up' | 'down' | 'warn' | 'neutral'
}

export function Badge({ children, variant = 'neutral' }: BadgeProps) {
    return <span className={`badge badge--${variant}`}>{children}</span>
}
