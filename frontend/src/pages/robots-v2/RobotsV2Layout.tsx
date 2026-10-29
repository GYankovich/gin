import React, { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { PageHero } from '@/components/ui/PageHero'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { robotV2Service } from '@/services/robotV2Service'
import { isRobotsV2DisabledError, ROBOTS_V2_DISABLED_MESSAGE } from '@/pages/robots-v2/robotsV2ModuleGuard'
import { usePageCacheStore } from '@/stores/pageCacheStore'
import '@/pages/DashboardPage.css'

/**
 * Guards /robots/* when the v2 API module is disabled on backend.
 * Keep this module sync-imported from App: a lazy layout + lazy index child
 * double-suspends and remounts the tree (spinner flash that feels like a refresh).
 */
export default function RobotsV2Layout() {
    const cachedModule = usePageCacheStore(s => s.robotsModule)
    const setRobotsModule = usePageCacheStore(s => s.setRobotsModule)
    const [disabled, setDisabled] = useState(cachedModule?.disabled ?? false)

    useEffect(() => {
        if (cachedModule != null) {
            setDisabled(cachedModule.disabled)
            return
        }

        let cancelled = false
        void robotV2Service
            .checkModule()
            .then(() => {
                if (cancelled) return
                setRobotsModule({ disabled: false })
                setDisabled(false)
            })
            .catch(e => {
                if (cancelled) return
                const isDisabled = isRobotsV2DisabledError(e)
                setRobotsModule({ disabled: isDisabled })
                setDisabled(isDisabled)
            })
        return () => {
            cancelled = true
        }
    }, [cachedModule, setRobotsModule])

    if (disabled) {
        return (
            <div className="page" data-page="robots">
                <PageHero className="dashboard-hero--node" title="Роботы" subtitle="Модуль недоступен" />
                <div className="dashboard-layout">
                    <Card className="dashboard-totals-card dashboard-error-card">
                        <div className="dashboard-error-card__robot" aria-hidden>
                            <RobotIllustration size={96} mode="inactive" interactive={false} />
                        </div>
                        <p className="dashboard-empty">{ROBOTS_V2_DISABLED_MESSAGE}</p>
                    </Card>
                </div>
            </div>
        )
    }

    return <Outlet />
}
