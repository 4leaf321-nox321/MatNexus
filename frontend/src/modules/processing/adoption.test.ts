/**
 * 채택 검토대의 셈 — **기본으로 무엇을 고르나, 어느 것이 튀나**(ADR 0058).
 *
 *   지금 채택을 기본으로      말없이 옮기지 않는다
 *   옛 원본의 결과는 피한다   원본을 바꾼 뒤의 결과가 있으면 그것
 *   반복 시편끼리만 견준다    같은 재료 · 시험 종류 · 방향 — 강판과 수지는 견줄 것이 없다
 *   하나뿐이면 모른다         자기 자신이 중앙값이라 늘 0 — 「안 튄다」 로 읽히면 안 된다
 *   부호를 지킨다             높게 튄 것과 낮게 튄 것은 다른 이야기다
 */

import { describe, expect, it } from 'vitest'

import {
  chosenOf,
  defaultChoice,
  groupOf,
  headlineOf,
  keysToCompare,
  spreadsOf,
} from '@/modules/processing/adoption'
import type { ResultBrief, RunOverview } from '@/modules/processing/api'

function result(id: string, values: Record<string, number>, over: Partial<ResultBrief> = {}) {
  return {
    id,
    created_at: '2026-10-01T00:00:00Z',
    recipe_key: null,
    recipe_label: null,
    step_count: 3,
    row_count: 100,
    has_true_stress: false,
    stale: false,
    is_adopted: false,
    scalars: Object.entries(values).map(([key, value]) => ({
      key,
      label: key,
      value,
      si_unit: 'Pa',
      dimension: null,
    })),
    ...over,
  } as ResultBrief
}

function run(id: string, results: ResultBrief[], over: Partial<RunOverview> = {}): RunOverview {
  return {
    test_run_id: id,
    found: true,
    code: id,
    record_name: id,
    status: 'parsed',
    test_type_key: 'tensile',
    test_type_label: '인장',
    adopted_result_id: null,
    results,
    ...over,
  } as RunOverview
}

describe('기본으로 고르는 결과', () => {
  it('지금 채택이 있으면 그것', () => {
    const one = run('t1', [result('new', {}), result('old', {})], { adopted_result_id: 'old' })
    expect(defaultChoice(one)).toBe('old')
  })

  it('없으면 옛 원본이 아닌 가장 최근', () => {
    // 결과는 최근 것이 앞에 온다(서버). 원본을 바꾸기 전의 결과는 옛 곡선의 것이다.
    const one = run('t1', [result('stale', {}, { stale: true }), result('fresh', {})])
    expect(defaultChoice(one)).toBe('fresh')
  })

  it('다 옛것이면 가장 최근, 결과가 없으면 없다', () => {
    expect(defaultChoice(run('t1', [result('a', {}, { stale: true })]))).toBe('a')
    expect(defaultChoice(run('t1', []))).toBeNull()
  })

  it('고른 것이 목록에서 사라졌으면 기본으로 돌아간다', () => {
    const one = run('t1', [result('a', {})])
    expect(chosenOf(one, { t1: '지워진것' })?.id).toBe('a')
    expect(chosenOf(one, undefined)?.id).toBe('a')
  })
})

describe('견줄 값', () => {
  it('인장이면 탄성계수 · 항복강도 · 인장강도 차례', () => {
    const keys = keysToCompare([
      result('a', { tensile_strength: 1, youngs_modulus: 2, elongation: 3 }),
    ])
    expect(keys).toEqual(['youngs_modulus', 'tensile_strength'])
  })

  it('그 셋이 없는 종류면 절반 이상이 가진 값 중 흔한 것', () => {
    const keys = keysToCompare([
      result('a', { tg: 1, e_glassy: 2, rare: 3 }),
      result('b', { tg: 1, e_glassy: 2 }),
      result('c', { tg: 1 }),
    ])
    expect(keys).toEqual(['tg', 'e_glassy'])
  })

  it('줄에 보일 값도 같은 차례', () => {
    const shown = headlineOf(result('a', { proof_stress: 2, youngs_modulus: 1 }), [
      'youngs_modulus',
      'proof_stress',
    ])
    expect(shown.map((one) => one.key)).toEqual(['youngs_modulus', 'proof_stress'])
  })
})

describe('중앙값과의 차이', () => {
  const runs = [
    run('t1', [result('a', { youngs_modulus: 200 })]),
    run('t2', [result('b', { youngs_modulus: 210 })]),
    run('t3', [result('c', { youngs_modulus: 100 })]),
  ]

  it('가장 먼 값으로 그 시험을 말하고, 부호를 지킨다', () => {
    const spreads = spreadsOf(runs, (one) => chosenOf(one, undefined))
    // 중앙값 200 — t3 은 절반, t2 는 5% 높다.
    expect(spreads.get('t3')?.ratio).toBeCloseTo(-0.5)
    expect(spreads.get('t2')?.ratio).toBeCloseTo(0.05)
    expect(spreads.get('t1')?.ratio).toBeCloseTo(0)
    expect(spreads.get('t3')?.key).toBe('youngs_modulus')
  })

  it('고른 결과로 센다 — 다른 결과를 고르면 차이도 바뀐다', () => {
    const many = [
      ...runs.slice(0, 2),
      run('t3', [result('c', { youngs_modulus: 100 }), result('d', { youngs_modulus: 205 })]),
    ]
    const spreads = spreadsOf(many, (one) => chosenOf(one, { t3: 'd' }))
    expect(Math.abs(spreads.get('t3')!.ratio)).toBeLessThan(0.05)
  })

  it('종류가 다르면 따로 센다', () => {
    const mixed = [
      ...runs,
      run('d1', [result('x', { tg: 300 })], { test_type_key: 'dma' }),
      run('d2', [result('y', { tg: 330 })], { test_type_key: 'dma' }),
    ]
    const spreads = spreadsOf(mixed, (one) => chosenOf(one, undefined))
    expect(spreads.get('d2')?.key).toBe('tg')
    expect(spreads.get('d2')?.ratio).toBeCloseTo(330 / 315 - 1)
    expect(spreads.get('t3')?.ratio).toBeCloseTo(-0.5)
  })

  it('재료나 방향이 다르면 따로 센다 — 반복 시편끼리만 견준다', () => {
    // 시험 종류로만 묶었더니 개발 DB 의 채택 전 47건(재료 여섯)에서 206 GPa 강판이 수지의
    // 중앙값에 대어 「+5405%」 로 섰다 — 47건 중 41건이 「먼 것」 이었다(2026-10-04).
    const mixed = [
      run('s1', [result('a', { youngs_modulus: 206 })], { material_id: 'steel' }),
      run('s2', [result('b', { youngs_modulus: 200 })], { material_id: 'steel' }),
      run('p1', [result('c', { youngs_modulus: 3.7 })], { material_id: 'resin' }),
      run('p2', [result('d', { youngs_modulus: 3.6 })], { material_id: 'resin' }),
      run('p3', [result('e', { youngs_modulus: 3.0 })], { material_id: 'resin', orientation: 'TD' }),
    ]
    const spreads = spreadsOf(mixed, (one) => chosenOf(one, undefined))
    expect(Math.abs(spreads.get('s1')!.ratio)).toBeLessThan(0.02)
    expect(Math.abs(spreads.get('p1')!.ratio)).toBeLessThan(0.02)
    // TD 는 하나뿐이라 견줄 것이 없다 — MD 와 섞어 「낮다」 고 하지 않는다.
    expect(spreads.get('p3')).toBeNull()
    expect(groupOf(mixed[0])).not.toBe(groupOf(mixed[2]))
  })

  it('견줄 것이 하나뿐이면 모른다', () => {
    // 하나뿐인 값은 자기 자신이 중앙값이라 늘 0 — 0 을 보이면 「안 튄다」 로 읽힌다.
    const spreads = spreadsOf([run('t1', [result('a', { youngs_modulus: 200 })])], (one) =>
      chosenOf(one, undefined)
    )
    expect(spreads.get('t1')).toBeNull()
  })

  it('결과가 없거나 볼 수 없는 시험은 모른다', () => {
    const spreads = spreadsOf(
      [...runs, run('none', []), run('gone', [], { found: false })],
      (one) => chosenOf(one, undefined)
    )
    expect(spreads.get('none')).toBeNull()
    expect(spreads.get('gone')).toBeNull()
  })
})
