/**
 * 묶음 ↔ 줄 — **접었다 펴도 같은 줄이다.** 저장 형식은 줄이고, 묶음은 보는 방식일 뿐이다.
 */

import { describe, expect, it } from 'vitest'

import type { DeckLine } from '@/modules/fitting/deckLines'
import { fromSections, lineRanges, summarize, toSections } from '@/modules/fitting/deckSections'

const LINES: DeckLine[] = [
  { kind: 'text', text: '*MATERIAL, NAME={name}' },
  { kind: 'block', block: 'header' },
  { kind: 'text', text: '*ELASTIC' },
  { kind: 'fields', fields: [{ value: 'elastic.youngs_modulus' }, { value: 'elastic.poisson_ratio' }] },
  { kind: 'text', text: '*DENSITY', when: 'elastic.density', note: '밀도가 없으면 뺀다' },
  { kind: 'fields', fields: [{ value: 'elastic.density' }], when: 'elastic.density' },
  { kind: 'text', text: '*PLASTIC' },
  { kind: 'rows', rows: 'table', x: 'plastic_strain', y: 'true_stress', fields: [{ value: 'true_stress' }] },
]

describe('접기', () => {
  it('키워드마다 묶고, 코드 묶음은 혼자 선다', () => {
    const sections = toSections(LINES)
    expect(sections.map((one) => one.keyword?.text ?? (one.body[0]?.block ?? '?'))).toEqual([
      '*MATERIAL, NAME={name}',
      'header',
      '*ELASTIC',
      '*DENSITY',
      '*PLASTIC',
    ])
    expect(sections[3].body).toHaveLength(1)
    expect(sections[4].body[0].kind).toBe('rows')
  })

  it('줄들의 조건이 같으면 묶음 조건으로, 메모는 머리에서 읽는다', () => {
    const density = toSections(LINES)[3]
    expect(density.when).toBe('elastic.density')
    expect(density.mixedWhen).toBe(false)
    expect(density.note).toBe('밀도가 없으면 뺀다')
  })

  it('줄마다 조건이 다르면 그대로 두고 그렇다고 표시한다', () => {
    const sections = toSections([
      { kind: 'text', text: '*X', when: 'a.b' },
      { kind: 'fields', fields: [{ value: 'a.b' }] },
    ])
    expect(sections[0].mixedWhen).toBe(true)
    expect(fromSections(sections)).toEqual([
      { kind: 'text', text: '*X', when: 'a.b' },
      { kind: 'fields', fields: [{ value: 'a.b' }] },
    ])
  })

  it('글자 줄(plain)은 새 묶음을 열지 않고 몸에 붙는다 — *MAT 아래 1, 0, 0', () => {
    const lines: DeckLine[] = [
      { kind: 'text', text: '*MAT_ELASTIC' },
      { kind: 'plain', text: '1, 0, 0' },
      { kind: 'fields', fields: [{ expr: 'elastic.youngs_modulus / 1000' }] },
    ]
    const sections = toSections(lines)
    expect(sections).toHaveLength(1)
    expect(sections[0].body.map((one) => one.kind)).toEqual(['plain', 'fields'])
    expect(summarize(sections[0])).toBe('값 줄 1 · 글자 줄 1')
    expect(fromSections(sections)).toEqual(lines)
  })

  it('머리 없이 시작한 값 줄은 머리 없는 묶음이 된다', () => {
    const sections = toSections([{ kind: 'fields', fields: [{ value: 'a.b' }] }])
    expect(sections[0].keyword).toBeNull()
    expect(summarize(sections[0])).toBe('값 줄 1')
  })
})

describe('펴기', () => {
  it('접었다 펴면 같은 줄이다', () => {
    expect(fromSections(toSections(LINES))).toEqual(LINES)
  })

  it('묶음 조건은 모든 줄에, 메모는 머리에만 적힌다', () => {
    const sections = toSections([
      { kind: 'text', text: '*DENSITY' },
      { kind: 'fields', fields: [{ value: 'elastic.density' }] },
    ])
    sections[0].when = 'elastic.density'
    sections[0].note = '없으면 뺌'
    expect(fromSections(sections)).toEqual([
      { kind: 'text', text: '*DENSITY', when: 'elastic.density', note: '없으면 뺌' },
      { kind: 'fields', fields: [{ value: 'elastic.density' }], when: 'elastic.density' },
    ])
  })

  it('묶음마다 정의 줄 구간을 안다 — 미리보기 줄과 잇는다', () => {
    expect(lineRanges(toSections(LINES))).toEqual([
      { start: 0, end: 1 },
      { start: 1, end: 2 },
      { start: 2, end: 4 },
      { start: 4, end: 6 },
      { start: 6, end: 8 },
    ])
  })
})
