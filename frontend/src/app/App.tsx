import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { PageLayout } from '@/components/layout/PageLayout'
import { ToastProvider } from '@/components/ui/Toast'

///@EPIC Frontend.ITEM Routing.TOPIC App Shell And Guards [1]
///@ Корневой роутинг фронтенда: lazy pages, protected layout, fallback loader
///@ и redirect-логика для публичных/приватных маршрутов.
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))
const RobotsPage = lazy(() => import('@/pages/RobotsPage'))
const RobotsV2FleetPage = lazy(() => import('@/pages/robots-v2/RobotsV2FleetPage'))
const RobotV2WizardPage = lazy(() => import('@/pages/robots-v2/RobotV2WizardPage'))
const RobotV2MonitorPage = lazy(() => import('@/pages/robots-v2/RobotV2MonitorPage'))
const RobotV2LogsPage = lazy(() => import('@/pages/robots-v2/RobotV2LogsPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const LivePage = lazy(() => import('@/pages/LivePage'))
const TestingPage = lazy(() => import('@/pages/TestingPage'))

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

export function App() {
    return (
        <ToastProvider>
            <Suspense fallback={<PageFallback />}>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />
                    <Route element={<ProtectedRoute><PageLayout /></ProtectedRoute>}>
                        <Route index element={<Navigate to="/dashboard" replace />} />
                        <Route path="dashboard" element={<DashboardPage />} />
                        <Route path="portfolio" element={<PortfolioPage />} />
                        <Route path="robots" element={<RobotsPage />} />
                        <Route path="robots/settings" element={<Navigate to="/robots" replace />} />
                        <Route path="robots-v2" element={<RobotsV2FleetPage />} />
                        <Route path="robots-v2/new" element={<RobotV2WizardPage />} />
                        <Route path="robots-v2/edit/:id" element={<RobotV2WizardPage />} />
                        <Route path="robots-v2/:id/monitor" element={<RobotV2MonitorPage />} />
                        <Route path="robots-v2/:id/logs" element={<RobotV2LogsPage />} />
                        <Route path="analytics" element={<AnalyticsPage />} />
                        <Route path="settings" element={<SettingsPage />} />
                        <Route path="testing" element={<TestingPage />} />
                        <Route path="testing-v2" element={<Navigate to="/testing" replace />} />
                        <Route path="live" element={<LivePage />} />
                    </Route>
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
            </Suspense>
        </ToastProvider>
    )
}
