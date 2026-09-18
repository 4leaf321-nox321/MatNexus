/**
 * 컨테이너 크기 — ForceGraph2D 는 **명시적 width/height** 가 필요하다.
 *
 * 처음 그릴 때 0 으로 재면 캔버스가 0x0 으로 만들어지고, 그 뒤로 아무것도 안 보인다.
 * 동기 측정 → 다음 프레임 재측정 → ResizeObserver 로 세 겹 보강한다.
 */

import { useLayoutEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const measure = () => {
      const rect = el.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setSize((prev) =>
          prev.width === rect.width && prev.height === rect.height
            ? prev
            : { width: rect.width, height: rect.height },
        )
      }
    }
    measure()
    const raf = requestAnimationFrame(measure)
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => {
      cancelAnimationFrame(raf)
      observer.disconnect()
    }
  }, [])

  return [ref, size] as const
}

/**
 * **화면 아래까지 채우는 높이.**
 *
 * 고정값(`640px`)으로 두면 큰 화면에서 그래프가 위쪽 구석에 웅크리고, 그 아래는
 * 빈 채로 남는다 — 그래프는 넓을수록 읽히는 그림이라 그 여백이 곧 손해다. 반대로
 * `calc(100vh - 220px)` 처럼 **머리 높이를 어림하면** 제목 줄이 한 줄 더 접히는
 * 날 어긋나고, 어긋난 것은 아무도 안 고친다.
 *
 * 그래서 잰다: 이 요소의 윗변이 화면의 어디인지 보고, 거기서 아래 여백만 뺀다.
 * 위에 무엇이 오든 스스로 맞는다.
 */
export function useFillHeight<T extends HTMLElement>(
  ref: RefObject<T | null>,
  { min = 420, gap = 24 }: { min?: number; gap?: number } = {},
): number {
  const [height, setHeight] = useState(min)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const measure = () => {
      const top = el.getBoundingClientRect().top
      const next = Math.max(min, Math.round(window.innerHeight - top - gap))
      // 1px 차이로는 안 바꾼다 — 소수점 반올림이 오갈 때마다 다시 그리면 캔버스가
      // 깜빡인다.
      setHeight((prev) => (Math.abs(prev - next) <= 1 ? prev : next))
    }
    measure()
    // 첫 프레임에는 위쪽 것들이 아직 자리를 안 잡았을 수 있다.
    const raf = requestAnimationFrame(measure)
    window.addEventListener('resize', measure)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', measure)
    }
  }, [ref, min, gap])

  return height
}
