/**
 * 그래프 색 — **늘어나도 회색이 안 나온다.**
 *
 * 마디 종류 21개 · 관계 26개인데 색이 열둘뿐이라, 탐색을 넓히면 열셋째 종류부터 전부
 * 같은 회색이 됐다(2026-10-03 지적). 무는 자리는 셋이다 — 앞 열둘은 그대로(이미 보던
 * 색이 바뀌지 않게), 그 뒤도 서로 다르고, 어느 것도 회색처럼 보이지 않는다.
 */

import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { colorScale, paletteColor, withAlpha } from '@/modules/graph/colors'
import { useCommunities } from '@/modules/graph/useCommunities'

/** 옛 회색(OVERFLOW_COLOR). */
const OLD_GRAY = '#9ca3af'

/** `#rrggbb` 의 HSL 채도 — 회색은 0 에 가깝다. */
function saturation(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const lightness = (max + min) / 2
  if (max === min) return 0
  return (max - min) / (1 - Math.abs(2 * lightness - 1))
}

describe('색 차례', () => {
  it('앞 열둘은 전과 같다 — 이미 보던 색이 안 바뀐다', () => {
    expect(paletteColor(0)).toBe('#6366f1')
    expect(paletteColor(11)).toBe('#ef4444')
  })

  it('지식 그래프의 마디 21종 · 관계 26종이 모두 다른 색이고 회색이 없다', () => {
    for (const count of [21, 26, 60]) {
      const keys = Array.from({ length: count }, (_, i) => `kind_${i}`)
      const scale = colorScale(keys)
      const colors = keys.map(scale)
      expect(new Set(colors).size).toBe(count)
      for (const color of colors) {
        expect(color).toMatch(/^#[0-9a-f]{6}$/)
        expect(color).not.toBe(OLD_GRAY)
        // 회색처럼 보이지 않는다 — 채도가 높다.
        expect(saturation(color)).toBeGreaterThan(0.5)
      }
    }
  })

  it('이웃한 색끼리 거의 같은 색이 없다 — 황금각으로 만들 때 열넷째가 바이올렛과 같았다', () => {
    // 옛 열넷째 #8b53ea 와 바이올렛 #8b5cf6 의 거리는 15 였다. 정해 둔 마흔여덟 색의 가장
    // 가까운 쌍은 23 이다(RGB 유클리드).
    const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
    const colors = Array.from({ length: 48 }, (_, i) => paletteColor(i))
    for (let i = 0; i < colors.length; i += 1) {
      for (let j = i + 1; j < colors.length; j += 1) {
        const [a, b] = [rgb(colors[i]), rgb(colors[j])]
        const distance = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
        expect(distance, `${colors[i]} · ${colors[j]}`).toBeGreaterThan(20)
      }
    }
  })

  it('목록에 없는 키도 회색이 아니고, 늘 같은 색이다', () => {
    const scale = colorScale(['material', 'sample'])
    expect(scale('unknown_kind')).not.toBe(OLD_GRAY)
    expect(scale('unknown_kind')).toBe(scale('unknown_kind'))
    expect(saturation(scale('unknown_kind'))).toBeGreaterThan(0.5)
  })

  it('만든 색도 투명도를 실을 수 있다 — 외곽선 · 흐린 선이 같은 색을 쓴다', () => {
    expect(withAlpha(paletteColor(20), 0.35)).toMatch(/^rgba\(\d+,\d+,\d+,0\.35\)$/)
  })
})

describe('커뮤니티 색', () => {
  /** 세 점짜리 무리 `groups` 개 + 홀로인 점 `singles` 개. 무리끼리는 안 잇는다. */
  function graph(groups: number, singles: number) {
    const nodeIds: string[] = []
    const edges: { src: string; dst: string }[] = []
    for (let g = 0; g < groups; g += 1) {
      const [a, b, c] = [`g${g}a`, `g${g}b`, `g${g}c`]
      nodeIds.push(a, b, c)
      edges.push({ src: a, dst: b }, { src: b, dst: c }, { src: c, dst: a })
    }
    for (let s = 0; s < singles; s += 1) nodeIds.push(`s${s}`)
    return { nodeIds, edges }
  }

  it('무리가 열둘을 넘어도, 홀로인 점도 회색이 아니다 — 외곽선은 세 점 이상만', () => {
    const { nodeIds, edges } = graph(14, 3)
    const { result } = renderHook(() => useCommunities(nodeIds, edges, true))
    const communities = result.current
    expect(communities.ready).toBe(true)
    expect(communities.count).toBe(14)

    const groupColors = new Set(
      Array.from({ length: 14 }, (_, g) => communities.colorOf(`g${g}a`)),
    )
    expect(groupColors.size).toBe(14) // 무리마다 다른 색
    for (const id of nodeIds) expect(communities.colorOf(id)).not.toBe(OLD_GRAY)
    // 같은 무리는 같은 색
    expect(communities.colorOf('g13a')).toBe(communities.colorOf('g13c'))
    // 홀로인 점은 색은 있지만 외곽선은 없다
    expect(communities.keyOf('s0')).toBeNull()
    expect(communities.keyOf('g0a')).not.toBeNull()
  })
})
