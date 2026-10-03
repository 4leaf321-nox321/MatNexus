/**
 * 의뢰 항목의 수량은 **합계**다 — 방향에 고르게 나누고, 나머지는 앞 방향부터.
 */

import { describe, expect, it } from 'vitest'

import { splitByOrientation } from '@/modules/commissions/itemConditions'

describe('splitByOrientation', () => {
  it('나누어떨어지면 고르게', () => {
    expect(splitByOrientation({ orientations: ['MD', 'TD'], count: 6 })).toEqual([
      { orientation: 'MD', count: 3 },
      { orientation: 'TD', count: 3 },
    ])
  })

  it('나머지는 앞 방향부터 하나씩', () => {
    expect(splitByOrientation({ orientations: ['MD', 'TD', 'DD'], count: 5 })).toEqual([
      { orientation: 'MD', count: 2 },
      { orientation: 'TD', count: 2 },
      { orientation: 'DD', count: 1 },
    ])
  })

  it('방향을 안 정했으면 NA 하나에 전부', () => {
    expect(splitByOrientation({ orientations: [], count: 4 })).toEqual([
      { orientation: 'NA', count: 4 },
    ])
  })
})
