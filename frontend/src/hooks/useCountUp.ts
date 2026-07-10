///@EPIC Frontend.ITEM Hooks.TOPIC FrontendSrcHooksUsecountup [1]
///@ Исходный модуль `frontend/src/hooks/useCountUp.ts` — автоматическая разметка для Obsidian Source Scanner.

import { useEffect, useRef, useState } from 'react'

export function useCountUp(target: number, duration = 800): number {
    const [current, setCurrent] = useState(0)
    const prev = useRef(0)
    const raf = useRef(0)

    useEffect(() => {
        const start = prev.current
        const diff = target - start
        if (Math.abs(diff) < 0.01) {
            setCurrent(target)
            prev.current = target
            return
        }
        const startTime = performance.now()

        const tick = (now: number) => {
            const elapsed = now - startTime
            const progress = Math.min(elapsed / duration, 1)
            const eased = 1 - Math.pow(1 - progress, 3)
            const val = start + diff * eased
            setCurrent(val)
            if (progress < 1) {
                raf.current = requestAnimationFrame(tick)
            } else {
                prev.current = target
            }
        }
        raf.current = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(raf.current)
    }, [target, duration])

    return current
}
