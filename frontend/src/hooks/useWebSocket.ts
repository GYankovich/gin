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

    const connect = useCallback(() => {
        if (!enabled) return
        try {
            const ws = new WebSocket(url)
            wsRef.current = ws
            ws.onopen = () => setConnected(true)
            ws.onmessage = (ev) => {
                try { onMessage?.(JSON.parse(ev.data)) } catch { onMessage?.(ev.data) }
            }
            ws.onclose = () => {
                setConnected(false)
                reconnectTimer.current = setTimeout(connect, reconnectInterval)
            }
            ws.onerror = () => ws.close()
        } catch {
            reconnectTimer.current = setTimeout(connect, reconnectInterval)
        }
    }, [url, enabled, onMessage, reconnectInterval])

    useEffect(() => {
        connect()
        return () => {
            clearTimeout(reconnectTimer.current)
            wsRef.current?.close()
        }
    }, [connect])

    const send = useCallback((data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
        }
    }, [])

    return { connected, send }
}
