/**
 * Ashby 지도의 보는 범위 — **커서 자리가 남는가 · 데이터 밖으로 안 나가는가.**
 *
 * 곡선 차트에 있던 두 결함(세로 고정점 어긋남 · 이동이 데이터 밖으로)을 베끼지 않았는지를
 * 숫자로 묶는다(2026-11-15).
 */

import { describe, expect, it } from 'vitest'

import { MAX_ZOOM, panBy, settle, toViewBox, zoomAt } from '@/modules/catalog/ashbyView'

const FULL = { x0: 0, x1: 10, y0: 0, y1: 4 }

describe('확대', () => {
  it('커서가 가리킨 값이 가로 · 세로 모두 그 자리에 남는다', () => {
    let box = FULL
    // 판의 오른쪽 아래(가로 0.8 · 세로 0.1)를 가리키고 열 번 당긴다.
    for (let i = 0; i < 10; i += 1) box = zoomAt(box, FULL, 0.8, 0.1, 0.85) ?? FULL
    expect(box.x0 + (box.x1 - box.x0) * 0.8).toBeCloseTo(8, 9)
    expect(box.y0 + (box.y1 - box.y0) * 0.1).toBeCloseTo(0.4, 9)
    expect(box.x1 - box.x0).toBeLessThan(10 * 0.85 ** 9)
  })

  it('전체보다 넓게 밀면 전체 보기(null)로 돌아간다', () => {
    const zoomed = zoomAt(FULL, FULL, 0.5, 0.5, 0.5)
    expect(zoomed).not.toBeNull()
    expect(zoomAt(zoomed!, FULL, 0.5, 0.5, 4)).toBeNull()
  })

  it('너무 파고들지 못한다', () => {
    let box = FULL
    for (let i = 0; i < 200; i += 1) box = zoomAt(box, FULL, 0.5, 0.5, 0.5) ?? FULL
    expect(box.x1 - box.x0).toBeCloseTo(10 / MAX_ZOOM, 9)
  })
})

describe('이동', () => {
  it('끈 만큼 반대로 옮긴다', () => {
    const box = { x0: 4, x1: 6, y0: 1, y1: 2 }
    expect(panBy(box, FULL, 0.5, 0)).toEqual({ x0: 3, x1: 5, y0: 1, y1: 2 })
  })

  it('멀리 끌어도 데이터 밖으로 안 나가고 폭은 그대로다', () => {
    const box = { x0: 4, x1: 6, y0: 1, y1: 2 }
    expect(panBy(box, FULL, -30, 0)).toEqual({ x0: 8, x1: 10, y0: 1, y1: 2 })
    expect(panBy(box, FULL, 0, 30)).toEqual({ x0: 4, x1: 6, y0: 0, y1: 1 })
  })

  it('전체를 보고 있으면 옮길 것이 없다', () => {
    expect(settle(FULL, FULL)).toBeNull()
  })
})

describe('화면 좌표 → viewBox', () => {
  it('틀이 viewBox 와 같은 비율이면 그대로다', () => {
    expect(toViewBox(430, 240, { left: 0, top: 0, width: 860, height: 480 }, 860, 480)).toEqual([
      430, 240,
    ])
  })

  it('틀이 더 넓으면 양옆 빈 자리를 뺀다', () => {
    // 폭 1200 · 높이 480 — 그림은 860 폭으로 가운데에 서고 양옆이 170 씩 빈다.
    const rect = { left: 100, top: 50, width: 1200, height: 480 }
    expect(toViewBox(100 + 170, 50, rect, 860, 480)).toEqual([0, 0])
    expect(toViewBox(100 + 170 + 860, 50 + 480, rect, 860, 480)).toEqual([860, 480])
  })

  it('크기가 없으면 못 바꾼다', () => {
    expect(toViewBox(1, 1, { left: 0, top: 0, width: 0, height: 0 }, 860, 480)).toBeNull()
  })
})
