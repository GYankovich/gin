import React, { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlus } from '@fortawesome/free-solid-svg-icons'
import { Card } from '@/components/ui/Card'
import { CollapsibleSection } from '@/components/ui/CollapsibleSection'
import { PageHero } from '@/components/ui/PageHero'
import { authService } from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { ProfileSection } from '@/pages/settings/components/ProfileSection'
import { ThemeSection } from '@/pages/settings/components/ThemeSection'
import { TokensSection } from '@/pages/settings/components/TokensSection'

///@EPIC Frontend.ITEM Settings.TOPIC Profile Tokens Theme [1]
///@ Экран пользовательских настроек: профиль, API токены, оформление.
export default function SettingsPage() {
    const user = useAuthStore(s => s.user)
    const loginAt = useAuthStore(s => s.loginAt)
    const updateUser = useAuthStore(s => s.updateUser)
    const { preference, setPreference } = useThemeStore()
    const [createOpen, setCreateOpen] = useState(false)
    const [tokenCount, setTokenCount] = useState(0)

    useEffect(() => {
        let cancelled = false
        void authService.me().then((fresh) => {
            if (!cancelled) updateUser(fresh)
        }).catch(() => { /* keep cached user */ })
        return () => { cancelled = true }
    }, [updateUser])

    return (
        <div className="page settings-page" data-page="settings">
            <PageHero
                eyebrow="CONTROL NODE"
                title="НАСТРОЙКИ"
                subtitle="Профиль · токены · оформление"
            />

            <div className="dashboard-layout settings-page__stack">
                <div className="settings-top-grid">
                    <Card className="dashboard-account-card settings-profile-card">
                        <ProfileSection
                            login={user?.login}
                            email={user?.email}
                            phone={user?.phone}
                            createdAt={user?.created_at}
                            loginAt={loginAt}
                        />
                    </Card>

                    <Card className="dashboard-assets-card settings-theme-card">
                        <div className="dashboard-assets-card__head">
                            <h3 className="dashboard-panel-title">Оформление</h3>
                        </div>
                        <ThemeSection preference={preference} onChange={setPreference} />
                    </Card>
                </div>

                <CollapsibleSection
                    id="tokens"
                    className="portfolio-collapse settings-tokens-collapse"
                    title="API токены "
                    badge={
                        <span className="portfolio-collapse__count">{tokenCount}</span>
                    }
                    headerEnd={(
                        <button
                            type="button"
                            className="settings-tokens__add"
                            onClick={() => setCreateOpen(true)}
                            aria-label="Добавить токен"
                        >
                            <FontAwesomeIcon icon={faPlus} className="settings-tokens__add-icon" />
                        </button>
                    )}
                    keepMounted
                >
                    <TokensSection
                        createOpen={createOpen}
                        onCreateOpenChange={setCreateOpen}
                        onCountChange={setTokenCount}
                    />
                </CollapsibleSection>
            </div>
        </div>
    )
}
