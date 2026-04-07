import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? '')
  .split(',')
  .map(host => host.trim())
  .filter(Boolean)

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'FrTikTok',
        short_name: 'FrTikTok',
        theme_color: '#000000',
        background_color: '#000000',
        display: 'fullscreen',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }
        ]
      }
    })
  ],
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
