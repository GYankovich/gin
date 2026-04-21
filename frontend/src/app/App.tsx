import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { PageLayout } from '@/components/layout/PageLayout'
import { ToastProvider } from '@/components/ui/Toast'

const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))
const RobotsPage = lazy(() => import('@/pages/RobotsPage'))
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
                        <Route path="analytics" element={<AnalyticsPage />} />
                        <Route path="settings" element={<SettingsPage />} />
                        <Route path="testing" element={<TestingPage />} />
                        <Route path="live" element={<LivePage />} />
                    </Route>
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
            </Suspense>
        </ToastProvider>
    )
}
