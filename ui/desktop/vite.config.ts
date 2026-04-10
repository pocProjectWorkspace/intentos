import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const isTauriBuild = !!process.env.TAURI_ENV_PLATFORM;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7891',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      // When building outside Tauri (plain web), externalize Tauri-only imports
      external: isTauriBuild
        ? []
        : [
            '@tauri-apps/api/core',
            '@tauri-apps/api/event',
            '@tauri-apps/plugin-shell',
          ],
    },
  },
})
