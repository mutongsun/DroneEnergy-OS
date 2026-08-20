import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
// vitest/config 的 defineConfig 扩展了 vite 的类型（含 test 字段）
import { defineConfig } from 'vitest/config'

// 开发期代理：前端 5173 → 后端 8000，避免本地跨域；
// 生产由 nginx 承担同样的反向代理职责
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
  },
})
