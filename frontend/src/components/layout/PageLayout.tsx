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
