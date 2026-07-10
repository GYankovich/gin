///@EPIC Frontend.ITEM Src.TOPIC FrontendSrcMain [1]
///@ Исходный модуль `frontend/src/main.tsx` — автоматическая разметка для Obsidian Source Scanner.

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from '@/app/App'
import '@/stores/themeStore'
import '@/styles/variables.css'
import '@/styles/global.css'
import '@/styles/animations.css'
import '@/styles/responsive.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <BrowserRouter>
        <App />
    </BrowserRouter>,
)
