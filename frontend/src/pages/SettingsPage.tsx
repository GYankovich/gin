import React, { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { EditUserModal } from '@/pages/settings/components/ProfileModals'
import { ProfileSection } from '@/pages/settings/components/ProfileSection'
import { SessionsSection } from '@/pages/settings/components/SessionsSection'
import {
    IconThemeMark,
    SettingsSectionLabel,
} from '@/pages/settings/components/SettingsSectionLabel'
import { ThemeSection } from '@/pages/settings/components/ThemeSection'
import { TokensSection } from '@/pages/settings/components/TokensSection'
import './DashboardPage.css'
import './SettingsPage.css'

///@EPIC Frontend.ITEM Settings.TOPIC Profile Tokens Theme [1]
///@ Настройки в языке дашборда/портфеля: профиль, тема и брокеры (токены + счета).
export default function SettingsPage() {
    const navigate = useNavigate()
    const user = useAuthStore(s => s.user)
    const updateUser = useAuthStore(s => s.updateUser)
    const logout = useAuthStore(s => s.logout)
    const { preference, setPreference } = useThemeStore()
    const [createOpen, setCreateOpen] = useState(false)
    const [editOpen, setEditOpen] = useState(false)
    const location = useLocation()
    const isMobile = useMediaQuery('(max-width: 767px)')

    useEffect(() => {
        const hash = location.hash.replace(/^#/, '').toLowerCase()
        if (hash !== 'tokens') return
        const scroll = () => document.getElementById('tokens')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        window.requestAnimationFrame(() => {
            scroll()
            window.setTimeout(scroll, 80)
        })
    }, [location.pathname, location.hash])

    useEffect(() => {
        let cancelled = false
        void authService.me().then((fresh) => {
            if (!cancelled) updateUser(fresh)
        }).catch(() => { /* keep cached user */ })
        return () => { cancelled = true }
    }, [updateUser])

    const onLogoutCurrent = () => {
        logout()
        navigate('/login')
    }

    return (
        <div
            className="page settings-page"
            data-page="settings"
            data-settings-layout={isMobile ? 'sheet' : 'rail'}
        >
            <h1 className="dash-sr-only">Настройки</h1>

            <div className="dashboard-layout settings-page__stack">
                <div className="settings-top-grid">
                    <Card className="dashboard-assets-card settings-profile-card">
                        <ProfileSection
                            login={user?.login}
                            email={user?.email}
                            createdAt={user?.created_at}
                            onEdit={() => setEditOpen(true)}
                            sheet={isMobile}
                        />
                    </Card>

                    {isMobile ? (
                        <div className="settings-theme-bare">
                            <SettingsSectionLabel icon={<IconThemeMark />}>Тема</SettingsSectionLabel>
                            <ThemeSection preference={preference} onChange={setPreference} />
                        </div>
                    ) : (
                        <Card className="dashboard-assets-card settings-theme-card">
                            <ThemeSection preference={preference} onChange={setPreference} />
                        </Card>
                    )}
                </div>

                <TokensSection
                    createOpen={createOpen}
                    onCreateOpenChange={setCreateOpen}
                    sheet={isMobile}
                />

                <SessionsSection
                    onLogoutCurrent={onLogoutCurrent}
                    sheet={isMobile}
                />
            </div>

            <EditUserModal
                open={editOpen}
                onClose={() => setEditOpen(false)}
                login={user?.login}
                email={user?.email}
                phone={user?.phone}
            />
        </div>
    )
}
