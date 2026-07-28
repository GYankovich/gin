import React from 'react'
import { Skeleton } from '@/components/ui/Skeleton'
import cyberHero from '@/assets/dashboard/cyber-hero.png'

export function TestingPageSkeleton() {
    return (
        <div className="page" data-page="testing">
            <header className="dashboard-hero">
                <div className="dashboard-hero__bg" style={{ backgroundImage: `url(${cyberHero})` }} aria-hidden />
                <div className="dashboard-hero__veil" aria-hidden />
                <div className="dashboard-hero__content">
                    <p className="dashboard-hero__eyebrow">GIN // BACKTEST NODE</p>
                    <h1 className="dashboard-hero__title">
                        <span className="dashboard-hero__title-glitch" data-text="ТЕСТИРОВАНИЕ">ТЕСТИРОВАНИЕ</span>
                    </h1>
                    <p className="dashboard-hero__sub">Загрузка…</p>
                </div>
            </header>
            <Skeleton height="48px" count={4} />
        </div>
    )
}
