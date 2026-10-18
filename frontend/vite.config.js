import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev: the Vue app runs on :5173 and forwards API calls to Django on :8008.
// Build: output goes to frontend/dist, which Django serves in production.
const backend = process.env.THREEFORM_BACKEND || 'http://127.0.0.1:8008'
const proxied = ['/api', '/goods', '/stock', '/binset', '/warehouse', '/asn', '/dn', '/cyclecount']

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(proxied.map((p) => [p, { target: backend, changeOrigin: false }])),
  },
  build: { outDir: 'dist', assetsDir: 'assets', emptyOutDir: true },
})
