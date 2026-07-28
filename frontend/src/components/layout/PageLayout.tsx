///@EPIC Frontend.ITEM Components.TOPIC FrontendSrcComponentsLayoutPagelayout [1]
///@ Исходный модуль `frontend/src/components/layout/PageLayout.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { MobileTabBar } from './MobileTabBar'

export function PageLayout() {
    return (
        <div className="app-shell">
            <Navbar />
            <main className="main-content">
                <Outlet />
            </main>
            <MobileTabBar />
        </div>
    )
}
