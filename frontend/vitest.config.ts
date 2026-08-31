/**
 * 프론트 검증 (개발계획 §8.5).
 *
 * **65의 재작업 44건이 이 축에서 나왔다.** 이 저장소도 같은 길을 가고 있었다 —
 * 최근 결함이 거의 전부 프론트였고 전부 사용자가 발견했다. 백엔드는 287개
 * 테스트가 지키는데 프론트는 0개였다.
 *
 * `vite.config.ts` 를 재사용하지 않고 파일을 나눈 이유: 개발 서버 설정(프록시·
 * 포트)이 테스트에 섞이면, 테스트가 도는 조건과 브라우저가 도는 조건이 은근히
 * 달라진다. **별칭(`@`)과 `define` 만 같게 맞춘다.**
 *
 * `define` 이 빠져 있어서 `__APP_VERSION__` 을 쓰는 컴포넌트가 시험에서 통째로
 * 터졌다(2026-08-28). 화면은 빈 `<div>` 만 남기고, 오류는 「글자를 못 찾았다」 로
 * 나와서 원인이 안 보였다 — 나눠 둔 설정은 이렇게 어긋난다.
 */

import path from 'node:path'
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

import pkg from './package.json' with { type: 'json' }

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(`v${pkg.version}`) },
  resolve: {
    alias: { '@': path.resolve(root, 'src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    /**
     * **시험 하나의 예산은 `asyncUtilTimeout` 보다 커야 한다.**
     *
     * 기본값 5초는 setup 의 8초보다 짧다 — `waitFor` 가 8초까지 기다릴 수 있는데
     * 시험은 5초에 죽으므로, 조건이 6초에 맞아도 실패한다. 그때 나오는 말은
     * 「Test timed out in 5000ms」 라 **무엇을 기다리다 죽었는지 안 보인다.**
     *
     * 실측(2026-08-31): 부하가 걸린 머신에서 `PropertiesPanel` 과
     * `ProcessingPanel` 이 번갈아 흔들렸다 — 매번 다른 시험이었고, 단독으로
     * 돌리면 전부 통과했다. 코드가 아니라 예산이 문제였다.
     *
     * **통과하는 시험은 안 느려진다.** 이 값은 실패할 때만 쓰인다.
     */
    testTimeout: 25000,

    // 결과를 조용히 흘리지 않는다. CI 가 읽을 수 있어야 한다.
    reporters: ['default'],
  },
})
