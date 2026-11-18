import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../backend')

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const backendEnv = loadEnv(mode, backendDir, '')
  const apiPort = process.env.APP_PORT || backendEnv.APP_PORT || '5001'

  return {
    plugins: [react()],
    base: './',
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
