import { useEffect, useRef } from 'react'

/** Gap between wheel events that starts a new gesture (trackpad / mouse). */
const GESTURE_GAP_MS = 160

/**
 * Nested table scroll → page scroll rules:
 * - Mid-gesture hit of the table edge: stop (do not chain to the page).
 * - New gesture while already at the edge: scroll the page.
 */
export function useNestedScrollChain<T extends HTMLElement = HTMLDivElement>() {
    const ref = useRef<T | null>(null)
    const latchRef = useRef<'inner' | 'outer' | null>(null)
    const lastWheelAtRef = useRef(0)

    useEffect(() => {
        const el = ref.current
        if (!el) return

        const onWheel = (event: WheelEvent) => {
            if (event.ctrlKey || event.defaultPrevented) return
            const dy = event.deltaY
            if (dy === 0) return

            const maxScroll = el.scrollHeight - el.clientHeight
            if (maxScroll <= 1) return

            const now = performance.now()
            const isNewGesture = now - lastWheelAtRef.current > GESTURE_GAP_MS
            lastWheelAtRef.current = now

            const top = el.scrollTop
            const atTop = top <= 0
            const atBottom = top >= maxScroll - 1
            const atEdge = (dy < 0 && atTop) || (dy > 0 && atBottom)

            if (!atEdge) {
                latchRef.current = 'inner'
                return
            }

            if (isNewGesture) {
                latchRef.current = 'outer'
                event.preventDefault()
                window.scrollBy({ top: dy, left: 0, behavior: 'auto' })
                return
            }

            if (latchRef.current === 'inner') {
                // Same gesture that scrolled the table — absorb at the edge
                event.preventDefault()
                return
            }

            latchRef.current = 'outer'
            event.preventDefault()
            window.scrollBy({ top: dy, left: 0, behavior: 'auto' })
        }

        el.addEventListener('wheel', onWheel, { passive: false })
        return () => el.removeEventListener('wheel', onWheel)
    }, [])

    return ref
}
