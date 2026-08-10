import { useCallback, useRef, type KeyboardEvent, type MouseEvent, type SyntheticEvent } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { copyText } from '@/pages/settings/utils'

type LongPressOptions = {
    delayMs?: number
}

/** Generic long-press (touch) action. */
export function useLongPress(handler: () => void | Promise<void>, options: LongPressOptions = {}) {
    const { delayMs = 450 } = options
    const timerRef = useRef<number | null>(null)
    const firedAtRef = useRef(0)
    const handlerRef = useRef(handler)
    handlerRef.current = handler

    const clear = useCallback(() => {
        if (timerRef.current != null) {
            window.clearTimeout(timerRef.current)
            timerRef.current = null
        }
    }, [])

    const start = useCallback(() => {
        clear()
        timerRef.current = window.setTimeout(() => {
            timerRef.current = null
            firedAtRef.current = Date.now()
            try {
                navigator.vibrate?.(12)
            } catch {
                /* ignore */
            }
            void handlerRef.current()
        }, delayMs)
    }, [clear, delayMs])

    const onContextMenu = useCallback((e: SyntheticEvent) => {
        if (Date.now() - firedAtRef.current < 800) {
            e.preventDefault()
        }
    }, [])

    return {
        onTouchStart: start,
        onTouchEnd: clear,
        onTouchCancel: clear,
        onTouchMove: clear,
        onContextMenu,
    }
}

type CopyGestureOptions = {
    delayMs?: number
}

/**
 * Copy gesture on a field:
 * - desktop: click
 * - mobile (≤768px): long-press
 */
export function useCopyGesture(handler: () => void | Promise<void>, options: CopyGestureOptions = {}) {
    const isMobile = useMediaQuery('(max-width: 768px)')
    const handlerRef = useRef(handler)
    handlerRef.current = handler

    const run = useCallback(() => handlerRef.current(), [])
    const longPress = useLongPress(run, options)

    const onClick = useCallback(
        (e: MouseEvent) => {
            if (isMobile) return
            e.preventDefault()
            e.stopPropagation()
            void run()
        },
        [isMobile, run],
    )

    const onKeyDown = useCallback(
        (e: KeyboardEvent) => {
            if (isMobile) return
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                void run()
            }
        },
        [isMobile, run],
    )

    if (isMobile) {
        return {
            className: 'settings-copyable',
            ...longPress,
        }
    }

    return {
        className: 'settings-copyable settings-copyable--click',
        onClick,
        onKeyDown,
        role: 'button' as const,
        tabIndex: 0,
    }
}

type CopyFieldOptions = CopyGestureOptions & {
    onCopied?: () => void
    onFailed?: () => void
}

/** Copy a string value via click (desktop) / long-press (mobile). */
export function useCopyableField(value: string | null | undefined, options: CopyFieldOptions = {}) {
    const { onCopied, onFailed, delayMs } = options
    return useCopyGesture(async () => {
        const text = String(value || '').trim()
        if (!text || text === '—') {
            onFailed?.()
            return
        }
        const ok = await copyText(text)
        if (ok) onCopied?.()
        else onFailed?.()
    }, { delayMs })
}
