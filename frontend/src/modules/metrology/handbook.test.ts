/**
 * 측정법에서 핸드북을 찾을 말 — 규격 칸은 원본 글 그대로라 **나누고 깎아야** 걸린다.
 */

import { describe, expect, it } from 'vitest'

import { handbookTerms, standardCodes } from '@/modules/metrology/handbook'
import type { MetrologyProperty } from '@/modules/metrology/api'

describe('standardCodes', () => {
  it('연도 · 부 번호를 뗀다 — 본문은 대개 기본 번호로 적는다', () => {
    expect(standardCodes('ISO 22412:2017')).toEqual(['ISO 22412'])
    expect(standardCodes('ISO 6892-1')).toEqual(['ISO 6892'])
    expect(standardCodes('ISO 527-2:1993')).toEqual(['ISO 527'])
  })

  it('여럿을 나누고, 기관 이름만 있는 조각은 버린다', () => {
    expect(
      standardCodes('JIS B0601-2001 / JIS B0601-1994 / JIS B0601-1982 / ISO 1997 / ANSI / VDA')
    ).toEqual(['JIS B0601', 'ISO 1997'])
  })

  it('「ASTM D 2240」 은 「ASTM D2240」 으로도 찾는다', () => {
    expect(standardCodes('ASTM D 2240')).toEqual(['ASTM D 2240', 'ASTM D2240'])
  })

  it('비었으면 없다', () => {
    expect(standardCodes(null)).toEqual([])
    expect(standardCodes('사내 규정')).toEqual([])
  })
})

describe('handbookTerms', () => {
  it('규격이 먼저(자주 나온 것부터), 이름이 끝', () => {
    const capability = (standard: string | null) => ({ standard }) as never
    const detail = {
      property_key: 'mechanical.youngs_modulus',
      name: '탄성계수',
      domain: 'mechanical',
      symbol: 'E',
      si_unit: 'Pa',
      test_standard: 'ASTM E111',
      techniques: [
        {
          technique: 'tensile',
          capabilities: [capability('ISO 6892-1'), capability('ISO 6892'), capability(null)],
        },
      ],
    } as MetrologyProperty
    expect(handbookTerms(detail)).toEqual([
      { term: 'ISO 6892', kind: 'standard' },
      { term: 'ASTM E111', kind: 'standard' },
      { term: '탄성계수', kind: 'name' },
    ])
  })
})
