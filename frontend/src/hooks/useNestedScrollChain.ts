import { useEffect, useRef } from 'react'

/**
 * Pause between wheel events that counts as a new gesture (finger lift / mouse idle).
 * Trackpad inertia keeps events closer than this; a real restart is longer.
 */
const GESTURE_GAP_MS = 220

function scrollPageBy(dy: number) {
    const root = document.scrollingElement ?? document.documentElement
    root.scrollTop += dy
}

/**
 * Nested table ↔ page scroll:
 * 1) Scroll the table until it hits an edge.
 * 2) Same gesture past the edge: stop (do not chain to the page).
 * 3) New gesture without moving the cursor, still at that edge: scroll the page.
 * 4) After an idle pause, the next gesture starts over — table first when it can
 *    still move; page only when already at the edge in that direction.
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

            if (isNewGesture) {
                // Idle restart: prefer the table again on the next cycle.
                latchRef.current = null
            }

            const top = el.scrollTop
            const atTop = top <= 0
            const atBottom = top >= maxScroll - 1
            const pushingPastEdge = (dy < 0 && atTop) || (dy > 0 && atBottom)

            if (!pushingPastEdge) {
                // Table can still move in this direction.
                latchRef.current = 'inner'
                return
            }

            // At edge, wheel pushes further out.
            if (isNewGesture || latchRef.current === null || latchRef.current === 'outer') {
                latchRef.current = 'outer'
                event.preventDefault()
                scrollPageBy(dy)
                return
            }

            // Same gesture that was scrolling the table — absorb at the edge.
            if (latchRef.current === 'inner') {
                event.preventDefault()
            }
        }

        el.addEventListener('wheel', onWheel, { passive: false })
        return () => el.removeEventListener('wheel', onWheel)
    }, [])

    return ref
}
