import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
    // root указываем на корень проекта, а не на frontend
    root: resolve(__dirname, './'),
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true
            }
        }
    },
    build: {
        outDir: resolve(__dirname, 'dist'),
        emptyOutDir: true
    }
})