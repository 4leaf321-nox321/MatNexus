/**
 * 문헌 재료 상세의 모양 — **화면이 이은 선이 저장된 값과 어긋나지 않는가.**
 *
 *   한 축으로만 갈리는 값은 그 축을 따라 한 선      출처 · 방법 · 나머지 조건이 같아야 한다
 *   나머지 조건이 다르면 다른 선                   노화 조건 · 범위 하한/상한이 섞이면 거짓 곡선
 *   한 값은 한 선에만                              온도로도 속도로도 이을 수 있으면 긴 쪽
 *   직접 넣은 한 벌 · 계수 항 · 원본에서 빠진 값은 안 잇는다
 */

import { describe, expect, it } from 'vitest'

import {
  autoCurves,
  propertyGroups,
  seriesCurves,
  sourceRows,
  tierCounts,
} from '@/modules/catalog/catalogShape'
import type { CatalogSeries, CatalogValue } from '@/modules/catalog/api'

const SOURCE = {
  id: 's1',
  kind: 'journal',
  doi: null,
  url: null,
  title: '논문 A',
  year: 2014,
  publisher: null,
  license: null,
}

let next = 0

function value(over: Partial<CatalogValue> & { conditions?: Record<string, unknown> }): CatalogValue {
  next += 1
  return {
    id: `v${next}`,
    property_key: 'mechanical.youngs_modulus',
    property_name: '탄성계수',
    domain: 'mechanical',
    symbol: 'E',
    value_num: 1e9,
    value_text: null,
    unit: 'Pa',
    uncertainty: null,
    conditions: null,
    method: 'measured',
    quality_tier: 1,
    source: SOURCE,
    source_detail: null,
    notes: null,
    representative: false,
    n_candidates: 1,
    separated_by: null,
    origin: 'catalog',
    ...over,
  } as CatalogValue
}

describe('화면이 이은 선', () => {
  it('한 축으로만 갈리는 값을 그 축을 따라 x 차례로 잇는다', () => {
    const lines = autoCurves([
      value({ value_num: 3e10, conditions: { temperature_k: 373.15, aging_days: 120 } }),
      value({ value_num: 4e10, conditions: { temperature_k: 298.15, aging_days: 120 } }),
      value({ value_num: 2e10, conditions: { temperature_k: 423.15, aging_days: 120 } }),
      // 노화가 다르다 — 같은 선이 아니다(점 하나라 선도 안 된다).
      value({ value_num: 5e10, conditions: { temperature_k: 298.15, aging_days: 0 } }),
    ])
    expect(lines).toHaveLength(1)
    expect(lines[0].axis).toBe('temperature_k')
    expect(lines[0].points).toEqual([
      [298.15, 4e10],
      [373.15, 3e10],
      [423.15, 2e10],
    ])
    expect(lines[0].label).toContain('aging_days=120')
  })

  it('범위의 하한과 상한은 다른 선이다 — 섞으면 지그재그 거짓 곡선', () => {
    const rows = [293, 323, 353].flatMap((t) => [
      value({ value_num: 1, conditions: { temperature_k: t, bound: 'lower' } }),
      value({ value_num: 2, conditions: { temperature_k: t, bound: 'upper' } }),
    ])
    const lines = autoCurves(rows)
    expect(lines).toHaveLength(2)
    expect(lines.map((line) => line.points.map(([, y]) => y))).toEqual([
      [1, 1, 1],
      [2, 2, 2],
    ])
  })

  it('출처가 다르면 다른 선이다', () => {
    const other = { ...SOURCE, id: 's2', title: '논문 B' }
    const lines = autoCurves([
      value({ conditions: { temperature_k: 1 } }),
      value({ conditions: { temperature_k: 2 } }),
      value({ conditions: { temperature_k: 3 }, source: other }),
    ])
    expect(lines).toHaveLength(0)
  })

  it('한 값은 한 선에만 — 두 축 모두 선이 될 수 있어도 값을 두 번 쓰지 않는다', () => {
    // 온도 셋 × 속도 셋 — 온도를 따라서도 속도를 따라서도 3점 선 셋이 된다. 값을 두 번 쓰면
    // 선 여섯 · 점 열여덟이 서서 같은 값이 두 그래프에 겹친다.
    const rows = [298, 373, 423].flatMap((t) =>
      [0.001, 0.1, 10].map((rate) => value({ conditions: { temperature_k: t, strain_rate_s: rate } }))
    )
    const lines = autoCurves(rows)
    expect(lines).toHaveLength(3)
    expect(lines.flatMap((line) => line.points)).toHaveLength(9)
    expect(new Set(lines.map((line) => line.axis)).size).toBe(1)
  })

  it('점이 더 많은 축을 고른다', () => {
    // 온도 둘 × 속도 셋 — 속도를 따라 이으면 3점 선 둘, 온도를 따라서는 2점이라 선이 아니다.
    const rows = [298, 373].flatMap((t) =>
      [0.001, 0.1, 10].map((rate) => value({ conditions: { temperature_k: t, strain_rate_s: rate } }))
    )
    const lines = autoCurves(rows)
    expect(lines.map((line) => line.axis)).toEqual(['strain_rate_s', 'strain_rate_s'])
    const ids = lines.flatMap((line) => line.points)
    expect(ids).toHaveLength(6)
  })

  it('직접 넣은 한 벌 · 계수 항 · 원본에서 빠진 값은 안 잇는다', () => {
    const lines = autoCurves([
      value({ conditions: { temperature_k: 1 }, series_id: 'x' }),
      value({ conditions: { temperature_k: 2 }, formula_term: true }),
      value({ conditions: { temperature_k: 3 }, source_missing_at: '2026-10-04T00:00:00Z' }),
      value({ conditions: { temperature_k: 4 } }),
      value({ conditions: { temperature_k: 5 } }),
    ])
    expect(lines).toHaveLength(0)
  })
})

describe('직접 넣은 한 벌', () => {
  it('곡선의 열마다 선 하나, 계수 묶음은 선이 아니다', () => {
    const series = [
      {
        id: 'c1',
        kind: 'curve',
        label: 'DMA 1 Hz',
        x_key: 'temperature_k',
        columns: [
          { property_key: 'mechanical.storage_modulus', property_name: '저장 탄성률', unit: 'Pa' },
          { property_key: 'mechanical.loss_tangent', property_name: '손실계수', unit: '1' },
        ],
      },
      { id: 'p1', kind: 'parameter_set', label: 'Anand', x_key: null, columns: [] },
    ] as unknown as CatalogSeries[]
    const values = [250, 300].flatMap((t) => [
      value({
        property_key: 'mechanical.storage_modulus',
        series_id: 'c1',
        conditions: { temperature_k: t },
      }),
      value({ property_key: 'mechanical.loss_tangent', series_id: 'c1', conditions: { temperature_k: t } }),
    ])
    const lines = seriesCurves(series, values)
    expect(lines.map((line) => [line.propertyKey, line.points.length, line.seriesId])).toEqual([
      ['mechanical.storage_modulus', 2, 'c1'],
      ['mechanical.loss_tangent', 2, 'c1'],
    ])
  })
})

describe('물성 요약 · 출처', () => {
  it('물성 하나에 한 줄 — 대표값 · 갈리는 조건 범위 · 선 수 · 계수 묶음 표시', () => {
    const values = [
      value({ value_num: 2e11, representative: true, conditions: { temperature_k: 298 } }),
      value({ value_num: 1.8e11, quality_tier: 3, conditions: { temperature_k: 573 } }),
      value({
        property_key: 'mechanical.anand_constant',
        property_name: 'Anand 상수',
        formula_term: true,
        conditions: { term: 'A', model: 'anand' },
      }),
    ]
    const groups = propertyGroups(values, autoCurves(values))
    expect(groups.map((one) => one.propertyKey)).toEqual([
      'mechanical.youngs_modulus',
      'mechanical.anand_constant',
    ])
    expect(groups[0].head.value_num).toBe(2e11)
    expect(groups[0].tiers).toEqual([1, 3])
    expect(groups[0].ranges).toEqual([{ key: 'temperature_k', min: 298, max: 573 }])
    expect(groups[0].parameterized).toBe(false)
    expect(groups[1].parameterized).toBe(true)
  })

  it('출처마다 값 수 · 물성 수 · 등급, 값이 많은 출처부터', () => {
    const other = { ...SOURCE, id: 's2', title: '논문 B' }
    const rows = sourceRows([
      value({}),
      value({ source: other, quality_tier: 2 }),
      value({ source: other, property_key: 'thermal.conductivity', quality_tier: 4 }),
    ])
    expect(rows.map((row) => [row.source?.title, row.count, row.properties, row.tiers])).toEqual([
      ['논문 B', 2, 2, [2, 4]],
      ['논문 A', 1, 1, [1]],
    ])
    expect([...tierCounts([value({}), value({ quality_tier: 4 })])]).toEqual([
      [1, 1],
      [4, 1],
    ])
  })
})
