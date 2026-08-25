import React, { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { PageHero } from '@/components/ui/PageHero'
import { Skeleton } from '@/components/ui/Skeleton'
import { RobotIllustration } from '@/components/ui/RobotIllustration'
import { robotV2Service } from '@/services/robotV2Service'
import { isRobotsV2DisabledError, ROBOTS_V2_DISABLED_MESSAGE } from '@/pages/robots-v2/robotsV2ModuleGuard'

/** Guards /robots-v2/* when the v2 API module is disabled on backend. */
export default function RobotsV2Layout() {
    const [checking, setChecking] = useState(true)
    const [disabled, setDisabled] = useState(false)

    useEffect(() => {
        let cancelled = false
        void robotV2Service
            .checkModule()
            .then(() => {
                if (!cancelled) {
                    setDisabled(false)
                    setChecking(false)
                }
            })
            .catch(e => {
                if (!cancelled) {
                    setDisabled(isRobotsV2DisabledError(e))
                    setChecking(false)
                }
            })
        return () => {
            cancelled = true
        }
    }, [])

    if (checking) {
        return (
            <div className="page" data-page="robots-v2">
                <PageHero eyebrow="ROBOT NODE" title="РОБОТЫ V2" subtitle="Проверка модуля…" />
                <div className="dashboard-layout">
                    <Card className="dashboard-totals-card">
                        <Skeleton height="88px" />
                    </Card>
                </div>
            </div>
        )
    }

    if (disabled) {
        return (
            <div className="page" data-page="robots-v2">
                <PageHero eyebrow="ROBOT NODE" title="РОБОТЫ V2" subtitle="Модуль недоступен" />
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
