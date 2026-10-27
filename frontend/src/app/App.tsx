import React, { Suspense, lazy } from 'react'

import { Routes, Route, Navigate, useLocation } from 'react-router-dom'

import { useAuthStore } from '@/stores/authStore'

import { PageLayout } from '@/components/layout/PageLayout'

import { ToastProvider } from '@/components/ui/Toast'



const LoginPage = lazy(() => import('@/pages/LoginPage'))

const DemoPage = lazy(() => import('@/pages/DemoPage'))

const DashboardPage = lazy(() => import('@/pages/DashboardPage'))

const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))

const RobotsV2Layout = lazy(() => import('@/pages/robots-v2/RobotsV2Layout'))

const RobotsV2FleetPage = lazy(() => import('@/pages/robots-v2/RobotsV2FleetPage'))

const RobotV2WizardPage = lazy(() => import('@/pages/robots-v2/RobotV2WizardPage'))

const RobotV2MonitorPage = lazy(() => import('@/pages/robots-v2/RobotV2MonitorPage'))

const RobotV2LogsPage = lazy(() => import('@/pages/robots-v2/RobotV2LogsPage'))

const BacktestLabPage = lazy(() => import('@/pages/robots-v2/BacktestLabPage'))

const BacktestRunPage = lazy(() => import('@/pages/robots-v2/BacktestRunPage'))

const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))

const SettingsPage = lazy(() => import('@/pages/SettingsPage'))



function ProtectedRoute({ children }: { children: React.ReactNode }) {

    const token = useAuthStore(s => s.token)

    if (!token) return <Navigate to="/login" replace />

    return <>{children}</>

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

            <Suspense fallback={<PageFallback />}>

                <Routes>

                    <Route path="/login" element={<LoginPage />} />

                    <Route path="/reset" element={<LoginPage />} />

                    <Route path="/demo" element={<DemoPage />} />

                    <Route element={<ProtectedRoute><PageLayout /></ProtectedRoute>}>

                        <Route index element={<Navigate to="/dashboard" replace />} />

                        <Route path="dashboard" element={<DashboardPage />} />

                        <Route path="portfolio" element={<PortfolioPage />} />

                        <Route path="robots/settings" element={<Navigate to="/robots" replace />} />

                        <Route path="backtest" element={<BacktestLabPage />} />

                        <Route path="backtest/:runId" element={<BacktestRunPage />} />

                        <Route path="robots/backtest" element={<RedirectToBacktestLab />} />

                        <Route path="robots" element={<RobotsV2Layout />}>

                            <Route index element={<RobotsV2FleetPage />} />

                            <Route path="new" element={<RobotV2WizardPage />} />

                            <Route path="edit/:id" element={<RobotV2WizardPage />} />

                            <Route path=":id/monitor" element={<RobotV2MonitorPage />} />

                            <Route path=":id/logs" element={<RobotV2LogsPage />} />

                            <Route path=":id/backtest" element={<Navigate to="/backtest" replace />} />

                        </Route>

                        <Route path="robots-v2/*" element={<RedirectRobotsV2 />} />

                        <Route path="analytics" element={<AnalyticsPage />} />

                        <Route path="settings" element={<SettingsPage />} />

                        <Route path="testing" element={<Navigate to="/robots" replace />} />

                        <Route path="testing-v2" element={<Navigate to="/robots" replace />} />

                        <Route path="live" element={<Navigate to="/robots" replace />} />

                    </Route>

                    <Route path="*" element={<Navigate to="/dashboard" replace />} />

                </Routes>

            </Suspense>

        </ToastProvider>

    )

}

