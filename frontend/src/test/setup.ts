/** 테스트 공통 준비. */

import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

/**
 * `findBy*`·`waitFor` 가 얼마나 기다리나. 기본값은 1초다.
 *
 * **1초는 부하 걸린 머신에서 모자란다.** 빌드와 스위트를 함께 돌렸을 때
 * `ProcessingPanel` 의 한 시험이 1,110ms 에서 시간 초과로 깨졌다 — 그 화면은
 * 자원 여럿을 읽고 큰 트리를 그린다. 코드는 멀쩡했다.
 *
 * **늘려도 통과하는 시험은 안 느려진다.** `waitFor` 는 조건이 맞는 순간 끝나고,
 * 이 값은 실패할 때만 쓰인다 — 진짜로 깨진 시험이 3초 뒤에 깨질 뿐이다.
 *
 * 흔들리는 시험은 스위트에 대한 신뢰를 갉아먹는다. 그것이 여기서 막으려는 것이다.
 */
configure({ asyncUtilTimeout: 3000 })

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

// Radix 의 Select·DropdownMenu 는 포인터 캡처 API 로 연다. jsdom 에 그것이
// 없어서 **누르면 아무 일도 안 일어났다** — 그래서 "선택지에 X 가 없다" 는
// 시험이 목록을 한 번도 열어 보지 않고 통과했다. 없는 것을 검사한 것이 아니라
// 아무것도 안 검사한 것이다.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}
