///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsUiToast [1]
///@ Исходный модуль `frontend/src/components/ui/Toast.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
    id: number
    message: string
    type: ToastType
}

interface ToastCtx {
    show: (message: string, type?: ToastType, durationMs?: number) => void
}

const Ctx = createContext<ToastCtx>({ show: () => {} })

export const useToast = () => useContext(Ctx)

let nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<ToastItem[]>([])

    const show = useCallback((message: string, type: ToastType = 'info', durationMs = 4000) => {
        const id = ++nextId
        setToasts(prev => [...prev, { id, message, type }])
        setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), durationMs)
    }, [])

    const value = useMemo(() => ({ show }), [show])

    return (
        <Ctx.Provider value={value}>
            {children}
            <div className="toast-container">
                {toasts.map(t => (
                    <div key={t.id} className={`toast toast--${t.type}`}>
                        {t.message}
                        <button className="toast__close" onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}>×</button>
                    </div>
                ))}
            </div>
        </Ctx.Provider>
    )
}

export function ToastContainer() {
    return null
}
