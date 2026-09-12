/**
 * 카드 종류 — **블록 선언의 `kind_priority` 로 고른다.** 화면이 블록 이름을 안 든다.
 */

import { describe, expect, it } from 'vitest'

import { DECLARED_KIND, cardKind } from '@/modules/fitting/cardKind'
import type { BlockSpec, PropertyCard } from '@/modules/fitting/api'

function spec(key: string, label: string, kind_priority: number | null): BlockSpec {
  return { key, label, help: '', produces: [], rows: [], in_deck: true, curve: null, kind_priority }
}

const SPECS = [
  spec('elastic', '탄성', null),
  spec('hardening', '경화식', 3),
  spec('rate_table', '속도 의존', 1),
  // 확장이 더한 블록 — 기본 우선순위 50, 이름은 선언에서.
  spec('creep_norton', '크리프 (Norton)', 50),
]

function card(blocks: string[], testType: string | null = 'tensile'): PropertyCard {
  return {
    blocks: Object.fromEntries(blocks.map((one) => [one, {}])),
    test_type_key: testType,
  } as unknown as PropertyCard
}

describe('cardKind', () => {
  it('우선순위가 작은 블록이 종류가 되고, 경화식은 「탄소성」 으로 읽힌다', () => {
    expect(cardKind(card(['elastic', 'hardening', 'rate_table']), SPECS)).toBe('속도 의존')
    expect(cardKind(card(['elastic', 'hardening']), SPECS)).toBe('탄소성')
  })

  it('확장이 더한 블록도 선언만으로 종류가 된다', () => {
    expect(cardKind(card(['elastic', 'creep_norton']), SPECS)).toBe('크리프 (Norton)')
  })

  it('탄성뿐이면 시험에서 왔는지로 가른다', () => {
    expect(cardKind(card(['elastic']), SPECS)).toBe('탄성')
    expect(cardKind(card(['elastic'], null), SPECS)).toBe(DECLARED_KIND)
  })
})
