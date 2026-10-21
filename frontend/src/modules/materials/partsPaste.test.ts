/**
 * 적용 부품 붙여넣기 — **열 짐작이 조용히 틀리지 않는가**(ADR 0064).
 *
 *   탭으로만 나눈다                쉼표는 파트명의 일부다
 *   머리글로 열을 짐작한다          품번 → 부품코드, 품명 → 파트명, 재질 → 재질
 *   한 칸은 한 열에만               뒤 열이 앞 열을 덮지 않는다
 *   사업부 기본값은 빈 칸에만        BOM 의 사업부 열을 덮으면 그 구분이 사라진다
 *   고치기는 바뀐 칸만              안 보낸 것과 비운 것을 가른다
 */

import { describe, expect, it } from 'vitest'

import type { BomPartImport, MaterialPart } from '@/modules/materials/api'
import {
  changesOf,
  formOf,
  guessColumns,
  linesOf,
  looksLikeHeader,
  merge,
  parseCells,
  pending,
  toRecords,
} from '@/modules/materials/partsPaste'

describe('붙여넣은 범위', () => {
  it('탭으로만 나누고 빈 줄은 뺀다', () => {
    const cells = parseCells('품명\t품번\r\n도어 이너, 아우터\tP-1\n\n\t\n')
    expect(cells).toEqual([
      ['품명', '품번'],
      ['도어 이너, 아우터', 'P-1'],
    ])
  })

  it('머리글로 열을 짐작한다', () => {
    const header = ['No', '품번', '품명', '재질', '모델', '사업부']
    expect(looksLikeHeader(header)).toBe(true)
    expect(guessColumns(header, 6)).toEqual([
      null,
      'part_code',
      'part',
      'material',
      'product',
      'division',
    ])
    // 대소문자 · 공백 · 기호는 가리지 않는다.
    expect(guessColumns(['Part No.', 'Part Name'], 2)).toEqual(['part_code', 'part'])
  })

  it('한 칸은 앞 열에만 — 뒤 열이 덮지 않는다', () => {
    expect(guessColumns(['품명', '부품명'], 2)).toEqual(['part', null])
  })

  it('머리글이 없으면 칸 차례대로 둔다', () => {
    expect(looksLikeHeader(['도어 이너', 'P-1'])).toBe(false)
    const fields = [
      { key: 'part' as const, label: '파트명', names: [] },
      { key: 'part_code' as const, label: '부품코드', names: [] },
    ]
    expect(guessColumns(null, 3, fields)).toEqual(['part', 'part_code', null])
  })

  it('고르지 않은 열과 빈 칸은 싣지 않는다', () => {
    expect(
      toRecords(
        [
          ['도어', '', 'x'],
          ['', 'P-2', 'y'],
        ],
        ['part', 'part_code', null]
      )
    ).toEqual([{ part: '도어' }, { part_code: 'P-2' }])
  })

  it('사업부 기본값은 사업부 칸이 빈 줄에만 채운다', () => {
    const lines = linesOf([{ part: 'A', division: '전장' }, { part: 'B' }], ' 가전 ')
    expect(lines.map((one) => one.division)).toEqual(['전장', '가전'])
    expect(linesOf([{ part: 'C' }], '')[0].division).toBeNull()
  })
})

describe('줄 고치기', () => {
  const row = {
    id: 'p1',
    part: '범퍼',
    product: '차 A',
    part_code: 'B-1',
    division: '자동차',
    note: null,
    source: 'bom',
    position: 0,
    created_at: '2026-10-21T00:00:00Z',
  } as MaterialPart

  it('바뀐 칸만 보내고, 비운 칸은 null 로 보낸다', () => {
    const form = { ...formOf(row), division: '', note: '사업부 미정' }
    expect(changesOf(row, form)).toEqual({ division: null, note: '사업부 미정' })
  })

  it('앞뒤 공백만 다르면 안 바뀐 것이다', () => {
    expect(changesOf(row, { ...formOf(row), part: ' 범퍼 ' })).toEqual({})
  })
})

describe('BOM 재질 짝', () => {
  const row = (index: number, material: string, status: string) => ({
    index,
    material,
    part: `파트 ${index}`,
    product: null,
    part_code: null,
    division: null,
    status,
    candidates: status === 'ambiguous' ? [{ id: 'm1', name: 'SGCC_A' }] : [],
  })

  it('재질마다 한 번만 묻고 줄 수를 센다', () => {
    const result = {
      applied: false,
      counts: {},
      materials: [],
      rows: [
        row(0, 'SGCC', 'ambiguous'),
        row(1, 'sgcc ', 'ambiguous'),
        row(2, '없는 재질', 'unmatched'),
        row(3, 'SECC', 'new'),
      ],
    } as unknown as BomPartImport
    const asks = pending(result)
    expect(asks.map((one) => [one.material, one.status, one.count])).toEqual([
      ['SGCC', 'ambiguous', 2],
      ['없는 재질', 'unmatched', 1],
    ])
    expect(asks[0].candidates).toEqual([{ id: 'm1', name: 'SGCC_A' }])
  })

  it('앞에서 물은 재질은 남기고 새로 물을 것만 더한다', () => {
    const before = [{ material: 'SGCC', status: 'ambiguous' as const, count: 2, candidates: [] }]
    const now = [
      { material: 'sgcc', status: 'ambiguous' as const, count: 2, candidates: [] },
      { material: 'X', status: 'unmatched' as const, count: 1, candidates: [] },
    ]
    expect(merge(before, now).map((one) => one.material)).toEqual(['SGCC', 'X'])
  })
})
