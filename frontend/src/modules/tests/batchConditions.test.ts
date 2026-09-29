/**
 * 일괄 등록의 조건 — **줄마다 다른 조건이 그대로 실리는가.**
 *
 * 전에는 종류마다 한 벌이라 23 °C · 80 °C 파일을 한 배치로 올리면 둘 다 같은 조건으로
 * 올라갔다(오류 없이). 조건은 통계·카드의 묶음(온도별·속도별)을 가르는 값이라, 틀리면
 * 다른 온도의 곡선이 같은 묶음에 조용히 섞인다.
 */

import { describe, expect, it } from 'vitest'

import type { TestType } from '@/modules/tests/api'
import { overrideCount, rowConditions } from '@/modules/tests/batchConditions'

const TENSILE = {
  key: 'tensile',
  conditions: [
    { key: 'temperature', label: '온도', value_type: 'number', si_unit: 'K' },
    { key: 'strain_rate', label: '변형률 속도', value_type: 'number', si_unit: '1/s' },
    { key: 'note', label: '비고', value_type: 'text', si_unit: null },
  ],
} as unknown as TestType
const DMA = {
  key: 'dma_sweep',
  conditions: [{ key: 'frequency', label: '주파수', value_type: 'number', si_unit: 'Hz' }],
} as unknown as TestType
const TYPES = [TENSILE, DMA]

const DEFAULTS = { tensile: { temperature: '23', strain_rate: '0.001' } }

describe('rowConditions', () => {
  it('줄에 적은 값이 종류 기본값을 이기고, 비운 칸은 기본값을 따른다', () => {
    expect(rowConditions('tensile', DEFAULTS, { temperature: '80' }, TYPES)).toEqual({
      temperature: 80,
      strain_rate: 0.001,
    })
    expect(rowConditions('tensile', DEFAULTS, { temperature: '' }, TYPES)).toEqual({
      temperature: 23,
      strain_rate: 0.001,
    })
  })

  it('같은 배치의 두 줄이 서로 다른 조건으로 실린다', () => {
    const first = rowConditions('tensile', DEFAULTS, {}, TYPES)
    const second = rowConditions('tensile', DEFAULTS, { temperature: '80', strain_rate: '0.1' }, TYPES)
    expect(first).toEqual({ temperature: 23, strain_rate: 0.001 })
    expect(second).toEqual({ temperature: 80, strain_rate: 0.1 })
  })

  it('그 종류가 선언하지 않은 칸은 싣지 않는다 — 종류를 바꾼 줄에 옛 칸이 남아도', () => {
    expect(rowConditions('dma_sweep', DEFAULTS, { temperature: '80', frequency: '1' }, TYPES)).toEqual({
      frequency: 1,
    })
  })

  it('글자 칸은 글자 그대로, 모르는 종류는 빈 조건', () => {
    expect(rowConditions('tensile', {}, { note: '재시험' }, TYPES)).toEqual({ note: '재시험' })
    expect(rowConditions('unknown', DEFAULTS, { temperature: '1' }, TYPES)).toEqual({})
  })
})

describe('overrideCount', () => {
  it('적은 칸만 센다', () => {
    expect(overrideCount({})).toBe(0)
    expect(overrideCount({ temperature: '80', strain_rate: '' })).toBe(1)
  })
})
