import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Flask API reads APP_PORT too, so one variable moves both — useful where
// Windows reserves port 5000 (`netsh interface ipv4 show excludedportrange`).
const apiPort = process.env.APP_PORT ?? '5000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
