import React, { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { SettingsBlock } from '@/pages/settings/components/SettingsBlock'
import { ProfileSection } from '@/pages/settings/components/ProfileSection'
import { ThemeSection } from '@/pages/settings/components/ThemeSection'
import { TokensSection } from '@/pages/settings/components/TokensSection'
import cyberHero from '@/assets/dashboard/cyber-hero.png'

const ONBOARDING_KEY = 'gin-settings-onboarding-dismissed'

///@EPIC Frontend.ITEM Settings.TOPIC Profile Tokens Theme [1]
///@ Экран пользовательских настроек: профиль, API токены, оформление.
export default function SettingsPage() {
    const user = useAuthStore(s => s.user)
    const token = useAuthStore(s => s.token)
    const loginAt = useAuthStore(s => s.loginAt)
    const { preference, setPreference } = useThemeStore()
    const [createOpen, setCreateOpen] = useState(false)
    const [showOnboarding, setShowOnboarding] = useState(false)

    useEffect(() => {
        setShowOnboarding(localStorage.getItem(ONBOARDING_KEY) !== '1')
    }, [])

    const dismissOnboarding = () => {
        localStorage.setItem(ONBOARDING_KEY, '1')
        setShowOnboarding(false)
    }

    return (
        <div className="page settings-page" data-page="settings">
            <header className="settings-hero">
                <div className="settings-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
                <div className="settings-hero__veil" aria-hidden />
                <div className="settings-hero__content">
                    <p className="settings-hero__eyebrow">GIN // CONTROL NODE</p>
                    <h1 className="settings-hero__title">
                        <span className="settings-hero__title-glitch" data-text="НАСТРОЙКИ">НАСТРОЙКИ</span>
                    </h1>
                    <p className="settings-hero__sub">Токены · оформление · профиль</p>
                </div>
            </header>

            {showOnboarding && (
                <div className="settings-onboarding" role="note">
                    <div>
                        <strong>API токены</strong> — ключи для подключения роботов к брокерам.
                        Без них торговые роботы не смогут работать.
                    </div>
                    <button type="button" className="settings-onboarding__close" onClick={dismissOnboarding}>
                        Понятно
                    </button>
                </div>
            )}

            <div className="settings-page__stack">
                <SettingsBlock
                    id="tokens"
                    title="API токены"
                    action={(
                        <Button variant="primary" size="sm" className="settings-block__action" onClick={() => setCreateOpen(true)}>
                            + Токен
                        </Button>
                    )}
                >
                    <TokensSection
                        createOpen={createOpen}
                        onCreateOpenChange={setCreateOpen}
                    />
                </SettingsBlock>

                <SettingsBlock id="theme" title="Оформление">
                    <ThemeSection preference={preference} onChange={setPreference} />
                </SettingsBlock>

                <SettingsBlock id="profile" title="Профиль" className="settings-block--profile" hideHeader>
                    <ProfileSection
                        login={user?.login}
                        email={user?.email}
                        phone={user?.phone}
                        loginAt={loginAt}
                        sessionActive={Boolean(token)}
                    />
                </SettingsBlock>
            </div>

            <button
                type="button"
                className="settings-fab"
                aria-label="Добавить токен"
                onClick={() => {
                    document.getElementById('tokens')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    setCreateOpen(true)
                }}
            >
                +
            </button>
        </div>
    )
}
