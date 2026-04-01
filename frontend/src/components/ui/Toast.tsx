import React, { createContext, useContext, useState, useCallback } from 'react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
    id: number
    message: string
    type: ToastType
}

interface ToastCtx {
    show: (message: string, type?: ToastType) => void
}

const Ctx = createContext<ToastCtx>({ show: () => {} })

export const useToast = () => useContext(Ctx)

let nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<ToastItem[]>([])

    const show = useCallback((message: string, type: ToastType = 'info') => {
        const id = ++nextId
        setToasts(prev => [...prev, { id, message, type }])
        setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000)
    }, [])

    return (
        <Ctx.Provider value={{ show }}>
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
