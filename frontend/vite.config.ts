import path from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(root, 'src') },
  },
  server: {
    // 5173·5174·3000~3010 은 사내 개발 PC에서 다른 플랫폼이 쓰고 있다.
    port: 5190,
    strictPort: true,
    // 개발 중에만 필요하다. 배포에서는 백엔드 한 프로세스가 SPA까지 서빙하므로
    // 프론트는 항상 같은 출처의 /api 를 부른다 — API 주소를 빌드에 굽지 않는다.
    // (52는 VITE_API_URL 이 빠지면 localhost:5000 으로 굳는 사고를 막으려고
    //  빌드 산출물을 검사하는 단계를 따로 뒀다. 상대경로면 그 검사 자체가 불필요)
    proxy: {
      // localhost 가 아니라 127.0.0.1 — 백엔드는 0.0.0.0(IPv4)에 바인딩하는데
      // 윈도우의 localhost 는 ::1 로 먼저 풀려 연결이 거부된다.
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // 번들 예산(개발계획 §8.5)의 1차 방어선. 곡선 차트를 넣을 때 여기가 먼저 운다.
    chunkSizeWarningLimit: 700,
  },
})
