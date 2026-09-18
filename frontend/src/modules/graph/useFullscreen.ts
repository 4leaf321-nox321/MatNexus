/**
 * 전체화면 — **브라우저 밖까지.**
 *
 * `fixed inset-0` 은 브라우저 **안쪽**만 덮는다. 주소창과 탭이 그대로 남아 그림이
 * 화면의 4분의 3에서 멈춘다 — 그래프는 넓을수록 읽히는 그림이라 그 차이가 크다.
 *
 * ## 막혀도 켠다
 *
 * 권한이 없거나(사용자 제스처 없이 부른 경우) 브라우저가 거절하면 `active` 는 그대로
 * true 다. 부르는 쪽이 `fixed` 로 덮으면 브라우저 안에서는 넓어진다 — **아무 일도
 * 안 일어나는 것이 가장 나쁘다.**
 *
 * ## 나가는 판단은 우리 상태로
 *
 * `document.fullscreenElement` 로만 보면, 거절당해 `fixed` 로만 넓어진 경우 그 값이
 * 비어 있어 「축소」 도 ESC 도 **다시 켜기**가 된다 — 나갈 길이 없는 화면에 갇힌다.
 */

import { useCallback, useEffect, useState } from 'react'
import type { RefObject } from 'react'

export function useFullscreen<T extends HTMLElement>(ref: RefObject<T | null>) {
  const [active, setActive] = useState(false)

  const toggle = useCallback(() => {
    if (active) {
      setActive(false)
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
      return
    }
    setActive(true)
    void ref.current?.requestFullscreen?.().catch(() => {})
  }, [active, ref])

  // 브라우저가 스스로 빠져나가면(ESC·F11·탭 전환) 우리 상태도 따라 내려온다. 안
  // 맞추면 단추는 「축소」 라고 적힌 채 화면은 이미 작아져 있다.
  useEffect(() => {
    const sync = () => {
      if (!document.fullscreenElement) setActive(false)
    }
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  return { active, toggle }
}
