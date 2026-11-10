///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutPagelayout [1]
///@ Исходный модуль `frontend/src/components/layout/PageLayout.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { MobileTabBar } from './MobileTabBar'
import { api } from '@/services/api'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'

function PageFallback() {
    return (
        <div className="page-loader">
            <div className="page-loader__spinner" />
        </div>
    )
}

export function PageLayout() {
    const [hasExpiredToken, setHasExpiredToken] = React.useState(false)
    const featuresLoaded = useAuthStore(s => s.featuresLoaded)
    const features = useAuthStore(s => s.features)

    React.useEffect(() => {
        void authService.bootstrapSession().catch(() => {
            const state = useAuthStore.getState()
            if (state.featuresLoaded) return
            // Migration lag / transient error: unlock shell with safe full package until retry.
            if (state.user) {
                state.setMeInfo({
                    user: state.user,
                    packageCode: state.packageCode ?? 1,
                    features: {
                        dashboard: true,
                        portfolio: true,
                        robots: true,
                        backtest: true,
                    },
                })
            }
        })
    }, [])

    React.useEffect(() => {
        let active = true
        const load = async () => {
            try {
                const { data } = await api.post('/apikey/data', {})
                const keys = Array.isArray(data?.keys) ? data.keys : []
                const hasExpired = keys.some((k: { status?: number }) => Number(k?.status || 0) === 3)
                if (active) setHasExpiredToken(hasExpired)
            } catch {
                if (active) setHasExpiredToken(false)
            }
        }
        void load()
        return () => {
            active = false
        }
    }, [])

    // Warm the robots fleet chunk so the first dock tap does not flash PageFallback.
    React.useEffect(() => {
        if (features.robots) {
            void import('@/pages/robots-v2/RobotsV2FleetPage')
        }
    }, [features.robots])

    if (!featuresLoaded) {
        return <PageFallback />
    }

    return (
        <div className="app-shell">
            <Navbar hasExpiredToken={hasExpiredToken} />
            <main className="main-content">
                {/* Keep shell mounted while lazy route chunks load (avoids full-page “refresh”). */}
                <Suspense fallback={<PageFallback />}>
                    <Outlet />
                </Suspense>
            </main>
            <MobileTabBar hasExpiredToken={hasExpiredToken} />
        </div>
    )
}
