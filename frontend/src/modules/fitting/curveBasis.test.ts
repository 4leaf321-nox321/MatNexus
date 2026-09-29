/**
 * 대표 곡선의 기준 — **요청에 무엇이 실리나.**
 *
 * 평균은 안 싣는다(서버 기본). 상·하한은 방법까지 있어야 싣는다 — 반쯤 고른 기준을 보내면
 * 서버가 거절하고, 사람에게는 「고르는 중인데 오류」 로 보인다.
 */

import { describe, expect, it } from 'vitest'

import {
  basisReady,
  basisRequest,
  basisSuffix,
  boundOptions,
} from '@/modules/fitting/curveBasis'

describe('basisRequest', () => {
  it('평균이면 안 싣는다 — 전과 같은 카드는 전과 같은 근거를 든다', () => {
    expect(basisRequest({ kind: 'mean' })).toBeNull()
  })

  it('하한은 방법(과 배수)까지 있어야 싣는다', () => {
    expect(basisRequest({ kind: 'lower' })).toBeNull()
    expect(basisRequest({ kind: 'lower', method: 'sd' })).toBeNull()
    expect(basisRequest({ kind: 'lower', method: 'sd', k: 2 })).toEqual({
      kind: 'lower',
      method: 'sd',
      k: 2,
    })
    // 표준편차가 아닌 방법에는 배수를 안 싣는다 — 서버가 거절한다.
    expect(basisRequest({ kind: 'upper', method: 'envelope', k: 2 })).toEqual({
      kind: 'upper',
      method: 'envelope',
    })
    expect(basisRequest({ kind: 'median' })).toEqual({ kind: 'median' })
  })
})

describe('basisReady · basisSuffix · boundOptions', () => {
  it('준비가 됐나를 가른다', () => {
    expect(basisReady({ kind: 'mean' })).toBe(true)
    expect(basisReady({ kind: 'upper' })).toBe(false)
    expect(basisReady({ kind: 'upper', method: 'tolerance' })).toBe(true)
  })

  it('카드 이름 뒤에 붙일 말', () => {
    expect(basisSuffix({ kind: 'mean' })).toBe('')
    expect(basisSuffix({ kind: 'lower', method: 'sd', k: 2 })).toBe(' · 하한 -2σ')
    expect(basisSuffix({ kind: 'upper', method: 'specimen' })).toBe(' · 상한 최고 시편')
  })

  it('방향에 맞는 말과 필요한 시편 수를 준다', () => {
    const lower = boundOptions('lower')
    expect(lower.map((one) => one.label)).toContain('평균 - 2σ')
    expect(lower.find((one) => one.method === 'envelope')?.label).toBe('포락선 (점마다 최솟값)')
    expect(lower.find((one) => one.method === 'tolerance')?.minSamples).toBe(3)
    expect(boundOptions('upper').map((one) => one.label)).toContain('평균 + 1σ')
  })
})
