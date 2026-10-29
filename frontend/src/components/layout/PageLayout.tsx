///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutPagelayout [1]
///@ Исходный модуль `frontend/src/components/layout/PageLayout.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React, { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { MobileTabBar } from './MobileTabBar'
import { api } from '@/services/api'

function PageFallback() {
    return (
        <div className="page-loader">
            <div className="page-loader__spinner" />
        </div>
    )
}

export function PageLayout() {
    const [hasExpiredToken, setHasExpiredToken] = React.useState(false)

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
        void import('@/pages/robots-v2/RobotsV2FleetPage')
    }, [])

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
