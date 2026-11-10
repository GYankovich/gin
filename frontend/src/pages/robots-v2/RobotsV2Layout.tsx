import React from 'react'
import { Outlet } from 'react-router-dom'
import '@/pages/DashboardPage.css'

/**
 * Layout shell for /robots/*. Feature gating lives in App FeatureRoute + /auth/me-info.
 * Keep sync-imported from App to avoid double-suspend remount flash.
 */
export default function RobotsV2Layout() {
    return <Outlet />
}
