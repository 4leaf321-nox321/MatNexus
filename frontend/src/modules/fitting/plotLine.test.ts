/**
 * 블록 그래프의 계수 선 — **한 직선은 그대로, 2구간은 꺾임에서 이어서**(VOC 61, 2026-11-14).
 */

import { describe, expect, it } from 'vitest'

import { LINE_POINTS, plotLine } from '@/modules/fitting/plotLine'
import type { components } from '@/shared/api/schema'

type BlockPlot = components['schemas']['BlockPlotOut']

const STRAIGHT: BlockPlot = {
  x: 'cycles',
  y: 'stress',
  log_x: true,
  log_y: true,
  hollow: null,
  line: { coefficient: 'a', exponent: 'b' },
}

const BENT: BlockPlot = {
  ...STRAIGHT,
  line: { coefficient: 'a1', exponent: 'b1', knee: 'knee', exponent2: 'b2' },
}

describe('plotLine', () => {
  it('꺾임이 없으면 한 직선, 점이 있는 범위만', () => {
    const line = plotLine(STRAIGHT, { a: 1e9, b: -0.1 }, 1e3, 1e7)
    expect(line).toHaveLength(LINE_POINTS)
    expect(line[0][0]).toBeCloseTo(1e3)
    expect(line.at(-1)?.[0]).toBeCloseTo(1e7)
    for (const [x, y] of line) expect(y).toBeCloseTo(1e9 * x ** -0.1, 0)
  })

  it('꺾임 뒤는 둘째 지수로 이어지고, 꺾임 자리를 그대로 지난다', () => {
    const values = { a1: 1e9, b1: -0.1, knee: 1e5, b2: -0.05 }
    const line = plotLine(BENT, values, 1e3, 1e8)
    const kneeStress = 1e9 * 1e5 ** -0.1
    expect(line).toHaveLength(LINE_POINTS + 1)
    const corner = line.find(([x]) => x === 1e5)
    expect(corner?.[1]).toBeCloseTo(kneeStress, 0)
    for (const [x, y] of line) {
      const expected = x <= 1e5 ? 1e9 * x ** -0.1 : kneeStress * (x / 1e5) ** -0.05
      expect(y / expected).toBeCloseTo(1, 10)
    }
    // 둘째 구간은 한 직선보다 완만하다 — 1e8 에서 한 직선의 값보다 높다.
    expect(line.at(-1)![1]).toBeGreaterThan(1e9 * 1e8 ** -0.1)
  })

  it('꺾임 값이 비면 한 직선으로 그린다 — 옛 카드 · 한 직선 결과', () => {
    const line = plotLine(BENT, { a1: 1e9, b1: -0.1 }, 1e3, 1e8)
    expect(line).toHaveLength(LINE_POINTS)
    for (const [x, y] of line) expect(y / (1e9 * x ** -0.1)).toBeCloseTo(1, 10)
  })

  it('계수가 없으면 선이 없다', () => {
    expect(plotLine(BENT, {}, 1e3, 1e8)).toEqual([])
  })
})
