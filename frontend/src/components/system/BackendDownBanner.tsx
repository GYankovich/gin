import React, { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { checkBackendReachable, probeBackendHealth } from '@/services/backendHealth'
import { useBackendStatusStore } from '@/stores/backendStatusStore'

const PROBE_MS = 5000

///@EPIC Frontend.ITEM Shell.TOPIC Backend Unavailability Banner [1]
///@ Один баннер на всё приложение, когда API недоступен. Локальные
///@ dashboard-error-card в этом состоянии скрыты стилями.
export function BackendDownBanner() {
    const down = useBackendStatusStore(s => s.down)
    const markReachable = useBackendStatusStore(s => s.markReachable)
    const [checking, setChecking] = useState(false)
    const bannerRef = React.useRef<HTMLDivElement>(null)

    useEffect(() => {
        const root = document.documentElement
        if (down) root.dataset.backend = 'down'
        else delete root.dataset.backend
        return () => {
            delete root.dataset.backend
        }
    }, [down])

    useEffect(() => {
        const el = bannerRef.current
        const root = document.documentElement
        if (!down || !el) {
            root.style.removeProperty('--backend-banner-h')
            return
        }
        const apply = () => {
            root.style.setProperty('--backend-banner-h', `${el.offsetHeight}px`)
        }
        apply()
        const observer = new ResizeObserver(apply)
        observer.observe(el)
        return () => {
            observer.disconnect()
            root.style.removeProperty('--backend-banner-h')
        }
    }, [down])

    useEffect(() => {
        if (!down) return
        let cancelled = false
        const tick = async () => {
            const ok = await probeBackendHealth()
            if (!cancelled && ok) markReachable()
        }
        void tick()
        const timer = window.setInterval(() => { void tick() }, PROBE_MS)
        return () => {
            cancelled = true
            window.clearInterval(timer)
        }
    }, [down, markReachable])

    if (!down) return null

    const onCheck = async () => {
        setChecking(true)
        try {
            await checkBackendReachable()
        } finally {
            setChecking(false)
        }
    }

    return (
        <div
            ref={bannerRef}
            className="backend-down-banner"
            role="status"
            aria-live="polite"
        >
            <p className="backend-down-banner__text">
                <strong>Сервис временно недоступен.</strong>
                {' '}
                Нет связи с сервером — экраны обновятся, когда он ответит.
            </p>
            <Button
                type="button"
                variant="secondary"
                size="sm"
                loading={checking}
                onClick={() => { void onCheck() }}
            >
                Проверить
            </Button>
        </div>
    )
}
