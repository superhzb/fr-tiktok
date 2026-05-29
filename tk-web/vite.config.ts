import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const allowedHosts = Array.from(
  new Set([
    'fr-tok.brettbot.ca',
    ...(process.env.VITE_ALLOWED_HOSTS ?? '')
      .split(',')
      .map(host => host.trim())
      .filter(Boolean)
  ])
)
const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:19099'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts,
    proxy: {
      '/api': { target: apiTarget, rewrite: path => path.replace(/^\/api/, '') },
      '/output': apiTarget
    }
  },
  preview: {
    host: true
  }
})
