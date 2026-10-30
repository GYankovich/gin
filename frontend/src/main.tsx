///@EPIC Frontend.ITEM Src.TOPIC FrontendSrcMain [1]
///@ Исходный модуль `frontend/src/main.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from '@/app/App'
import '@/stores/themeStore'
import '@/styles/fonts.css'
import '@/styles/variables.css'
import '@/styles/global.css'
import '@/styles/backtestLab.css'
import '@/styles/animations.css'
import '@/styles/responsive.css'

// After deploy, an open tab may still reference old hashed chunks. Missing /assets/*
// used to SPA-fallback as HTML → module parse error → blank #root. Reload once.
const PRELOAD_RELOAD_KEY = 'gin-vite-preload-reload'
window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    try {
        if (sessionStorage.getItem(PRELOAD_RELOAD_KEY) === '1') return
        sessionStorage.setItem(PRELOAD_RELOAD_KEY, '1')
    } catch {
        /* private mode */
    }
    window.location.reload()
})
window.addEventListener('load', () => {
    try {
        sessionStorage.removeItem(PRELOAD_RELOAD_KEY)
    } catch {
        /* ignore */
    }
})

ReactDOM.createRoot(document.getElementById('root')!).render(
    <BrowserRouter>
        <App />
    </BrowserRouter>,
)
