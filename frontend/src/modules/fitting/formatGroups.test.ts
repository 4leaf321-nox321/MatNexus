import { describe, expect, it } from 'vitest'

import { groupBySolver, solverOf } from '@/modules/fitting/formatGroups'

describe('solverOf', () => {
  it('괄호 앞이 솔버다', () => {
    expect(solverOf('LS-DYNA (속도 의존)')).toBe('LS-DYNA')
    expect(solverOf('Abaqus (선형탄성구간 · DMA)')).toBe('Abaqus')
  })

  it('괄호가 없으면 이름 전체 — 정의로 붙인 형식은 그 꼴이 아닐 수 있다', () => {
    expect(solverOf('중립 JSON')).toBe('중립 JSON')
    expect(solverOf('Altair OptiStruct')).toBe('Altair OptiStruct')
  })
})

describe('groupBySolver', () => {
  it('처음 나온 차례로 묶는다', () => {
    const groups = groupBySolver([
      { key: 'b1', label: 'B (하나)' },
      { key: 'a1', label: 'A (하나)' },
      { key: 'b2', label: 'B (둘)' },
    ])
    expect(groups.map((one) => one.solver)).toEqual(['B', 'A'])
    expect(groups[0].items.map((one) => one.key)).toEqual(['b1', 'b2'])
  })
})
