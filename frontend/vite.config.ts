import path from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import pkg from './package.json' with { type: 'json' }

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // **이 빌드가 몇 번인지 굽는다.** 서버가 다른 버전이면 화면이 그것을 말할 수
  // 있어야 한다 — 개발과 운영이 같은 포트를 쓰던 동안, 프론트가 옛 서버에 붙어
  // 있는데도 아무 데도 티가 안 났다(2026-08-28).
  define: { __APP_VERSION__: JSON.stringify(`v${pkg.version}`) },
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
      //
      // **8011 이다. 운영이 8010 을 쓴다.**
      //
      // 전에는 둘 다 8010 이었다. 그래서 개발 백엔드를 내린 순간 이 프록시가
      // **운영 설치본(v1.115.0)에 그대로 붙었고**, 화면은 「존재하지 않는
      // 엔드포인트」 만 말했다. 원인을 찾는 데 한참 걸렸다 — 서버가 죽은 것도
      // 아니고 코드가 틀린 것도 아니어서, 볼 곳이 어디에도 없었다
      // (2026-08-28 실측).
      //
      // 더 나쁜 것은 조용히 붙는 쪽이다. 운영이 응답하는 동안 개발 화면은
      // **운영 DB(`matnexus_server`)를 보고 있었다.** 포트를 가르면 개발
      // 백엔드가 없을 때 연결 거부가 나고, 그것은 그 자리에서 알 수 있다.
      '/api': { target: 'http://127.0.0.1:8011', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // 번들 예산(개발계획 §8.5)의 1차 방어선. 곡선 차트를 넣을 때 여기가 먼저 운다.
    chunkSizeWarningLimit: 700,
  },
})
