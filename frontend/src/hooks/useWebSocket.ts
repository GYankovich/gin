///@EPIC Frontend.ITEM Hooks.TOPIC FrontendSrcHooksUsewebsocket [1]
///@ Исходный модуль `frontend/src/hooks/useWebSocket.ts` — автоматическая разметка для Obsidian Source Scanner.

import { useEffect, useRef, useCallback, useState } from 'react'

interface UseWebSocketOptions {
    url: string
    onMessage?: (data: any) => void
    enabled?: boolean
    reconnectInterval?: number
}

export function useWebSocket({ url, onMessage, enabled = true, reconnectInterval = 3000 }: UseWebSocketOptions) {
    const wsRef = useRef<WebSocket | null>(null)
    const [connected, setConnected] = useState(false)
    const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
    const reconnectAttempt = useRef(0)
    const onMessageRef = useRef<UseWebSocketOptions['onMessage']>(onMessage)
    const shouldReconnectRef = useRef<boolean>(enabled)
    const connVersionRef = useRef(0)

    useEffect(() => {
        onMessageRef.current = onMessage
    }, [onMessage])

    const scheduleReconnect = useCallback((connectFn: () => void) => {
        reconnectAttempt.current += 1
        const delay = Math.min(
            reconnectInterval * Math.pow(2, reconnectAttempt.current - 1),
            30000,
        )
        reconnectTimer.current = setTimeout(connectFn, delay)
    }, [reconnectInterval])

    const connect = useCallback(() => {
        if (!enabled || !url) return
        shouldReconnectRef.current = true
        clearTimeout(reconnectTimer.current)
        const version = ++connVersionRef.current
        try {
            if (wsRef.current) {
                try { wsRef.current.close() } catch { /* noop */ }
                wsRef.current = null
            }
            const ws = new WebSocket(url)
            wsRef.current = ws
            ws.onopen = () => {
                if (connVersionRef.current !== version || wsRef.current !== ws) return
                reconnectAttempt.current = 0
                setConnected(true)
            }
            ws.onmessage = (ev) => {
                if (connVersionRef.current !== version || wsRef.current !== ws) return
                const cb = onMessageRef.current
                if (!cb) return
                try { cb(JSON.parse(ev.data)) } catch { cb(ev.data) }
            }
            ws.onclose = () => {
                if (connVersionRef.current !== version) return
                setConnected(false)
                if (shouldReconnectRef.current) {
                    scheduleReconnect(connect)
                }
            }
            ws.onerror = () => {
                if (connVersionRef.current !== version) return
                ws.close()
            }
        } catch {
            if (shouldReconnectRef.current) {
                scheduleReconnect(connect)
            }
        }
    }, [url, enabled, scheduleReconnect])

    useEffect(() => {
        shouldReconnectRef.current = enabled
        connect()
        return () => {
            shouldReconnectRef.current = false
            clearTimeout(reconnectTimer.current)
            connVersionRef.current += 1
            wsRef.current?.close()
            wsRef.current = null
            setConnected(false)
        }
    }, [connect])

    const send = useCallback((data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
        }
    }, [])

    return { connected, send }
}
