import React from 'react'

interface CardProps {
    children: React.ReactNode
    className?: string
    onClick?: () => void
    glow?: boolean
}

export function Card({ children, className = '', onClick, glow }: CardProps) {
    const cls = ['card', glow && 'card--glow', onClick && 'card--clickable', className].filter(Boolean).join(' ')
    return (
        <div className={cls} onClick={onClick}>
            {children}
        </div>
    )
}
