///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiBadge [1]
///@ Исходный модуль `frontend/src/components/ui/Badge.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'

interface BadgeProps {
    children: React.ReactNode
    variant?: 'cyan' | 'magenta' | 'up' | 'down' | 'warn' | 'neutral'
}

export function Badge({ children, variant = 'neutral' }: BadgeProps) {
    return <span className={`badge badge--${variant}`}>{children}</span>
}
