import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuthStore, type AuthFeatures } from '@/stores/authStore'
import { PageLayout } from '@/components/layout/PageLayout'
import { ToastProvider } from '@/components/ui/Toast'
import RobotsV2Layout from '@/pages/robots-v2/RobotsV2Layout'
import RobotQuietShell from '@/pages/robots-v2/RobotQuietShell'

const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DemoPage = lazy(() => import('@/pages/DemoPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))
const RobotsV2FleetPage = lazy(() => import('@/pages/robots-v2/RobotsV2FleetPage'))
const RobotV2WizardPage = lazy(() => import('@/pages/robots-v2/RobotV2WizardPage'))
const RobotV2MonitorPage = lazy(() => import('@/pages/robots-v2/RobotV2MonitorPage'))
const RobotV2LogsPage = lazy(() => import('@/pages/robots-v2/RobotV2LogsPage'))
const BacktestLabPage = lazy(() => import('@/pages/robots-v2/BacktestLabPage'))
const BacktestRunPage = lazy(() => import('@/pages/robots-v2/BacktestRunPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))

function firstAllowedPath(features: AuthFeatures): string {
    if (features.dashboard) return '/dashboard'
    if (features.portfolio) return '/portfolio'
    if (features.robots) return '/robots'
    if (features.backtest) return '/backtest'
    return '/settings'
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const token = useAuthStore(s => s.token)
    if (!token) return <Navigate to="/login" replace />
    return <>{children}</>
}

function FeatureRoute({
    tab,
    children,
}: {
    tab: keyof AuthFeatures
    children: React.ReactNode
}) {
    const features = useAuthStore(s => s.features)
    const featuresLoaded = useAuthStore(s => s.featuresLoaded)
    if (!featuresLoaded) return null
    if (!features[tab]) {
        return <Navigate to={firstAllowedPath(features)} replace />
    }
    return <>{children}</>
}

function HomeRedirect() {
    const features = useAuthStore(s => s.features)
    const featuresLoaded = useAuthStore(s => s.featuresLoaded)
    if (!featuresLoaded) return null
    return <Navigate to={firstAllowedPath(features)} replace />
}

function PageFallback() {
    return (
        <div className="page-loader">
            <div className="page-loader__spinner" />
        </div>
    )
}

function RedirectRobotsV2() {
    const { pathname, search } = useLocation()
    const next = pathname.replace(/^\/robots-v2/, '/robots')
    return <Navigate to={`${next}${search}`} replace />
}

function RedirectToBacktestLab() {
    const { search } = useLocation()
    const params = new URLSearchParams(search)
    const run = Number(params.get('run') || params.get('runId') || '')
    if (Number.isFinite(run) && run > 0) {
        return <Navigate to={`/backtest/${run}`} replace />
    }
    return <Navigate to={`/backtest${search}`} replace />
}

export function App() {
    return (
        <ToastProvider>
            <Routes>
                <Route
                    path="/login"
                    element={(
                        <Suspense fallback={<PageFallback />}>
                            <LoginPage />
                        </Suspense>
                    )}
                />
                <Route
                    path="/reset"
                    element={(
                        <Suspense fallback={<PageFallback />}>
                            <LoginPage />
                        </Suspense>
                    )}
                />
                <Route
                    path="/demo"
                    element={(
                        <Suspense fallback={<PageFallback />}>
                            <DemoPage />
                        </Suspense>
                    )}
                />
                <Route element={<ProtectedRoute><PageLayout /></ProtectedRoute>}>
                    <Route index element={<HomeRedirect />} />
                    <Route
                        path="dashboard"
                        element={<FeatureRoute tab="dashboard"><DashboardPage /></FeatureRoute>}
                    />
                    <Route
                        path="portfolio"
                        element={<FeatureRoute tab="portfolio"><PortfolioPage /></FeatureRoute>}
                    />
                    <Route path="robots/settings" element={<Navigate to="/robots" replace />} />
                    <Route
                        path="backtest"
                        element={<FeatureRoute tab="backtest"><BacktestLabPage /></FeatureRoute>}
                    />
                    <Route
                        path="backtest/:runId"
                        element={<FeatureRoute tab="backtest"><BacktestRunPage /></FeatureRoute>}
                    />
                    <Route path="robots/backtest" element={<RedirectToBacktestLab />} />
                    <Route
                        path="robots"
                        element={<FeatureRoute tab="robots"><RobotsV2Layout /></FeatureRoute>}
                    >
                        <Route index element={<RobotsV2FleetPage />} />
                        <Route path="new" element={<RobotV2WizardPage />} />
                        <Route path="edit/:id" element={<RobotV2WizardPage />} />
                        <Route path=":id" element={<RobotQuietShell />}>
                            <Route path="monitor" element={<RobotV2MonitorPage />} />
                            <Route path="logs" element={<RobotV2LogsPage />} />
                        </Route>
                        <Route path=":id/backtest" element={<Navigate to="/backtest" replace />} />
                    </Route>
                    <Route path="robots-v2/*" element={<RedirectRobotsV2 />} />
                    <Route path="analytics" element={<Navigate to="/dashboard" replace />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="testing" element={<Navigate to="/robots" replace />} />
                    <Route path="testing-v2" element={<Navigate to="/robots" replace />} />
                    <Route path="live" element={<Navigate to="/robots" replace />} />
                </Route>
                <Route path="*" element={<HomeRedirect />} />
            </Routes>
        </ToastProvider>
    )
}
