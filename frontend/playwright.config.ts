/**
 * 스모크 — **연기가 나는가만 본다.**
 *
 * vitest 는 jsdom 에서 돈다. 요소가 있는지·클릭하면 함수가 불리는지는 보지만
 * **레이아웃 엔진이 없어** 어디에 그려지는지는 모르고, 서버·워커·DB 는 전부
 * 가짜다. 그래서 이런 것들을 원리상 못 잡는다.
 *
 *   드롭다운이 트리거를 덮은 채 떴다        요소는 있었고 클릭도 됐다. 위치만 틀렸다
 *   곡선 6벌이 저장됐는데 화면에 안 보였다  API 로만 확인해서 놓쳤다
 *   워커가 안 떠서 '대기' 에 멈췄다         워커가 없는 세계에서는 안 보인다
 *
 * 그래서 **진짜 브라우저 + 진짜 서버·워커·DB** 로 한 줄기를 끝까지 밟는다.
 * 세밀한 검증은 안 한다 — 그건 vitest 와 pytest 의 일이다.
 *
 * 시각 회귀(스크린샷 픽셀 비교)는 **일부러 넣지 않았다.** 폰트 렌더링·시각·
 * 애니메이션 때문에 거짓 실패가 잦고, 그것이 반복되면 사람들이 baseline 을
 * 습관적으로 갱신하게 되어 검사가 죽는다. 대신 **실패했을 때만 스크린샷과
 * 트레이스를 남긴다** — 거짓 실패는 0이면서 "무슨 화면이었는지" 는 남는다.
 */

import { defineConfig, devices } from '@playwright/test'

/**
 * 어디에 붙을지. 기본은 개발 서버(vite, 5190)다.
 *
 * CI 는 8010 을 준다 — 배포에서는 백엔드 한 프로세스가 SPA 까지 서빙하므로
 * **그쪽이 운영과 같은 모양**이다. 프록시가 끼지 않아 확인 대상도 하나 줄어든다.
 */
const baseURL = process.env.MNX_BASE_URL ?? 'http://127.0.0.1:5190'

export default defineConfig({
  testDir: './e2e',
  // 한 줄기가 데이터를 만들며 진행한다. 병렬로 돌리면 서로의 재료를 본다.
  workers: 1,
  fullyParallel: false,
  // 실패를 재시도로 덮지 않는다. 스모크가 흔들리면 그것 자체가 신호다.
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'ko-KR',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
