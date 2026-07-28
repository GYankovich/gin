import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const WS_PORT = Number(process.env.VITE_WS_PORT || process.env.WS_PORT || 8001)

export default defineConfig({
    plugins: [react()],
    root: resolve(__dirname, './'),
    resolve: {
        alias: { '@': resolve(__dirname, 'frontend/src') },
    },
    server: {
        port: 5173,
        // Dual-stack so http://localhost and http://127.0.0.1 both work.
        host: true,
        strictPort: true,
        hmr: {
            protocol: 'ws',
            // Match whatever host the browser used for the page.
            clientPort: 5173,
        },
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // Live monitor: browser stays same-origin; Vite upgrades WS → gateway.
            '/ws': {
                target: `http://127.0.0.1:${WS_PORT}`,
                changeOrigin: true,
                ws: true,
                secure: false,
                // Avoid buffering / hanging upgrades on Windows.
                timeout: 0,
                proxyTimeout: 0,
            },
        },
    },
    build: {
        outDir: resolve(__dirname, 'dist'),
        emptyOutDir: true,
    },
})
