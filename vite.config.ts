import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const WS_PORT = Number(process.env.VITE_WS_PORT || process.env.WS_PORT || 8001)

/** Local development only. Production UI is served by nginx from dist/. */
export default defineConfig({
    plugins: [react()],
    root: resolve(__dirname, './'),
    resolve: {
        alias: { '@': resolve(__dirname, 'frontend/src') },
    },
    server: {
        port: 5173,
        host: true,
        strictPort: true,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
                ws: true,
                timeout: 0,
                proxyTimeout: 0,
            },
            '/ws': {
                target: `http://127.0.0.1:${WS_PORT}`,
                changeOrigin: true,
                ws: true,
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
