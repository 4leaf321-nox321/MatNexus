/**
 * 프론트 검증 (개발계획 §8.5).
 *
 * **65의 재작업 44건이 이 축에서 나왔다.** 이 저장소도 같은 길을 가고 있었다 —
 * 최근 결함이 거의 전부 프론트였고 전부 사용자가 발견했다. 백엔드는 287개
 * 테스트가 지키는데 프론트는 0개였다.
 *
 * `vite.config.ts` 를 재사용하지 않고 파일을 나눈 이유: 개발 서버 설정(프록시·
 * 포트)이 테스트에 섞이면, 테스트가 도는 조건과 브라우저가 도는 조건이 은근히
 * 달라진다. 별칭(`@`)만 같게 맞춘다.
 */

import path from 'node:path'
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(root, 'src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // 결과를 조용히 흘리지 않는다. CI 가 읽을 수 있어야 한다.
    reporters: ['default'],
  },
})
