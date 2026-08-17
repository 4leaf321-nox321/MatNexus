/**
 * 요약값 짝짓기 — **나란히 두는 것이 source 를 나눈 이유다.**
 *
 * `TestSummary` 는 `(시험, key, source)` 로 유일해서 같은 항목에 장비 값과 우리
 * 값이 나란히 서게 돼 있었다. 그런데 화면이 한 줄씩 평평하게 그려서, 같은
 * 항복강도가 표의 다른 자리에 떨어져 있었다 — 실측으로 56% 차이가 났는데
 * 눈으로 훑어 짝을 찾아야 알 수 있었다.
 */

import { describe, expect, it } from 'vitest'

import { pairSummaries } from '@/modules/tests/summaries'
import type { SummaryRow } from '@/modules/tests/summaries'

const row = (over: Partial<SummaryRow>): SummaryRow => ({
  key: 'proof_stress',
  label: null,
  source: 'instrument',
  value: null,
  text: null,
  si_unit: 'Pa',
  ...over,
})

describe('요약값 짝짓기', () => {
  it('같은 키의 장비·우리 값을 한 줄로 묶는다', () => {
    const pairs = pairSummaries([
      row({ source: 'instrument', value: 159.979e6 }),
      row({ source: 'matnexus', value: 249.5e6, label: '항복강도' }),
    ])
    expect(pairs).toHaveLength(1)
    expect(pairs[0].instrument?.value).toBe(159.979e6)
    expect(pairs[0].ours?.value).toBe(249.5e6)
  })

  it('차이를 장비 기준으로 센다', () => {
    // 장비 값이 먼저 있던 값이다. 우리 계산이 나중이므로 그 기준에서 읽는다.
    const pairs = pairSummaries([
      row({ source: 'instrument', value: 100 }),
      row({ source: 'matnexus', value: 156 }),
    ])
    expect(pairs[0].differencePercent).toBeCloseTo(56, 6)
  })

  it('한쪽만 있으면 차이가 없다', () => {
    const only = pairSummaries([row({ source: 'matnexus', value: 205e9 })])
    expect(only[0].differencePercent).toBeNull()
    expect(only[0].instrument).toBeNull()
  })

  it('기준이 0 이면 몇 %인지 묻지 않는다', () => {
    // 0 으로 나누면 Infinity 가 나오고, 화면은 그것을 그대로 그린다.
    const pairs = pairSummaries([
      row({ source: 'instrument', value: 0 }),
      row({ source: 'matnexus', value: 5 }),
    ])
    expect(pairs[0].differencePercent).toBeNull()
  })

  it('숫자가 아닌 값(Unknown)은 차이를 내지 않는다', () => {
    // `.tra` 는 "Unknown" 을 그대로 적어 보낸다.
    const pairs = pairSummaries([
      row({ key: 'upper_yield', source: 'instrument', value: null, text: 'Unknown' }),
      row({ key: 'upper_yield', source: 'matnexus', value: 300e6 }),
    ])
    expect(pairs[0].differencePercent).toBeNull()
    expect(pairs[0].instrument?.text).toBe('Unknown')
  })

  it('짝이 있는 것이 위로 온다', () => {
    // 비교가 이 표의 목적이다. 한쪽만 있는 값은 참고다.
    const pairs = pairSummaries([
      row({ key: 'hardening_n', source: 'instrument', value: 0.23 }),
      row({ key: 'proof_stress', source: 'instrument', value: 160e6 }),
      row({ key: 'proof_stress', source: 'matnexus', value: 249e6 }),
    ])
    expect(pairs[0].key).toBe('proof_stress')
  })

  it('라벨은 우리 것을 먼저 쓴다', () => {
    // 장비 라벨은 원문 그대로라 영어이고 `k{lo 10 - 15}` 같은 표기가 붙는다.
    const pairs = pairSummaries([
      row({ source: 'instrument', label: 'Force at proof stress 0.2%' }),
      row({ source: 'matnexus', label: '항복강도' }),
    ])
    expect(pairs[0].label).toBe('항복강도')
  })

  it('차원은 우리 것이 우선이다', () => {
    // 장비 값에는 차원이 비어 있다 — 파서가 알려 주지 않는다.
    const pairs = pairSummaries([
      row({ key: 'proof_strain', source: 'instrument', si_unit: '1', value: 0.06 }),
      row({
        key: 'proof_strain',
        source: 'matnexus',
        si_unit: '1',
        dimension: 'strain',
        value: 0.068,
      }),
    ])
    expect(pairs[0].dimension).toBe('strain')
  })
})
