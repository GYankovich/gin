import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const WS_PORT = Number(process.env.VITE_WS_PORT || process.env.WS_PORT || 8001)

/** Dead upstream → 502 (nginx-like). Default Vite/http-proxy answers with 500. */
function proxyTo(target: string, extra: Record<string, unknown> = {}) {
    return {
        target,
        changeOrigin: true,
        ...extra,
        configure: (proxy: { on: (event: string, fn: (...args: any[]) => void) => void }) => {
            proxy.on('error', (_err: Error, _req: unknown, res: { headersSent?: boolean; writeHead?: Function; end?: Function }) => {
                if (!res || res.headersSent || typeof res.writeHead !== 'function') return
                res.writeHead(502, { 'Content-Type': 'application/json' })
                res.end(JSON.stringify({ detail: 'Bad gateway' }))
            })
        },
    }
}

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
            '/api': proxyTo('http://127.0.0.1:8000', {
                ws: true,
                timeout: 0,
                proxyTimeout: 0,
            }),
            '/health': proxyTo('http://127.0.0.1:8000'),
            '/ws': proxyTo(`http://127.0.0.1:${WS_PORT}`, {
                ws: true,
                timeout: 0,
                proxyTimeout: 0,
            }),
        },
    },
    build: {
        outDir: resolve(__dirname, 'dist'),
        emptyOutDir: true,
    },
})
