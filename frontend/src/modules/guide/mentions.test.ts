/**
 * 절에 나오는 물성 — 길잡이라 **시끄럽지 않게**: 두 글자 미만 · 더 긴 이름에 든 이름은 뺀다.
 */

import { describe, expect, it } from 'vitest'

import { mentionedProperties, textOf } from '@/modules/guide/mentions'
import type { MetrologyCoverageRow } from '@/modules/metrology/api'

function row(name: string, key = name): MetrologyCoverageRow {
  return {
    property_key: key,
    name,
    domain: 'mechanical',
    symbol: null,
    si_unit: 'Pa',
    technique_count: 1,
    instrument_count: 1,
    owned_instrument_count: 0,
    value_count: 1,
  }
}

describe('textOf', () => {
  it('글자만 뽑고, 블록 사이는 줄을 바꾼다 — 낱말이 붙지 않게', () => {
    const text = textOf({
      type: 'doc',
      content: [
        { type: 'heading', content: [{ type: 'text', text: '인장 시험' }] },
        { type: 'paragraph', content: [{ type: 'text', text: '항복' }, { type: 'text', text: '강도' }] },
        { type: 'paragraph', content: [{ type: 'text', text: '밀도' }] },
      ],
    })
    expect(text).toContain('인장 시험\n')
    expect(text).toContain('항복강도\n')
    expect(text).not.toContain('시험항복')
  })
})

describe('mentionedProperties', () => {
  it('처음 나온 차례로 세우고, 더 긴 이름에 든 짧은 이름 · 한 글자 이름은 뺀다', () => {
    const rows = [row('밀도'), row('강도'), row('항복강도'), row('E'), row('열전도율')]
    const found = mentionedProperties('열전도율과 항복강도, 그리고 밀도. E 는 탄성.', rows)
    expect(found.map((one) => one.name)).toEqual(['열전도율', '항복강도', '밀도'])
  })

  it('대소문자는 안 가린다', () => {
    expect(mentionedProperties('the Poisson ratio', [row('poisson ratio')])).toHaveLength(1)
  })
})
