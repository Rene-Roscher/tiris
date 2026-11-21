import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Dev: UI on :5173, API from the tiris backend (TIRIS_API, default :8080).
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { proxy: { '/api': { target: process.env.TIRIS_API ?? 'http://127.0.0.1:8080', changeOrigin: false } } },
  build: { target: 'es2022', chunkSizeWarningLimit: 900 },
})
