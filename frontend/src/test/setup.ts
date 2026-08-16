/** 테스트 공통 준비. */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// 테스트마다 DOM 을 비운다. 안 하면 앞 테스트가 남긴 노드를 다음 테스트가 찾아
// **통과하지 말아야 할 것이 통과한다.**
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom 에 없는 것들. Radix 프리미티브가 이것들을 부른다 — 없으면 열리지도
// 않는 컴포넌트를 두고 "테스트가 어렵다" 고 결론 내리게 된다.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
