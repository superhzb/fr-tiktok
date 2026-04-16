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

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts,
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: path => path.replace(/^\/api/, '') },
      '/output': 'http://localhost:8000'
    }
  },
  preview: {
    host: true
  }
})
