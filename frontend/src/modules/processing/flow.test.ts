/**
 * 순서도 — **돌려 보기 전에도 무엇을 고를 수 있는지 안다.**
 *
 * 여기서 지키는 것은 실제로 겪은 막힘이다: 처음 데이터에는 변위·하중·폭만
 * 있는데 인장강도 단계는 변형률·응력 열을 고르라고 한다. 그 열은 앞 단계가
 * 만드는 것이라, 돌려 보기 전에는 목록이 비어 있었다.
 */

import { describe, expect, it } from 'vitest'

import {
  blockersAt,
  columnsAt,
  insertionIndex,
  madeColumns,
  outOfOrder,
  resolveTemplate,
  valuesAt,
} from '@/modules/processing/flow'
import type { ProcessingStep, RecipeStep } from '@/modules/processing/api'

const SOURCE = ['displacement', 'force', 'width']

function plugin(over: Partial<ProcessingStep> & { id: string }): ProcessingStep {
  return {
    label: over.id,
    version: '1',
    applies_to: ['tensile'],
    params: [],
    makes_columns: [],
    makes_values: [],
    order: 100,
    ...over,
  } as ProcessingStep
}

const column = (name: string, label: string, dflt?: string) => ({
  name,
  label,
  type: 'str',
  default: dflt ?? null,
  choices: [],
  choice_labels: {},
  unit: null,
  dimension: null,
  help: null,
  role: 'column',
  when: {},
})

const CATALOG = new Map<string, ProcessingStep>(
  [
    plugin({
      id: 'tensile.engineering',
      order: 10,
      makes_columns: ['strain_engineering', 'stress_engineering'],
      params: [
        column('displacement', '변위 열', 'displacement'),
        column('force', '하중 열', 'force'),
      ] as ProcessingStep['params'],
    }),
    plugin({ id: 'curve.sort_unique', order: 20, params: [column('x', '기준 열')] as ProcessingStep['params'] }),
    plugin({
      id: 'curve.smooth',
      order: 45,
      makes_columns: ['{column}_smoothed'],
      params: [column('column', '평활할 열')] as ProcessingStep['params'],
    }),
    plugin({ id: 'tensile.elastic_modulus', order: 50, makes_values: ['youngs_modulus'] }),
    plugin({
      id: 'tensile.proof_stress',
      order: 60,
      makes_values: ['proof_stress'],
      params: [
        {
          ...column('youngs_modulus', '탄성계수'),
          type: 'float',
          role: null,
          default: '@youngs_modulus',
        },
      ] as ProcessingStep['params'],
    }),
    plugin({
      id: 'tensile.strength',
      order: 70,
      params: [
        column('strain', '변형률 열', 'strain_engineering'),
        column('stress', '응력 열', 'stress_engineering'),
      ] as ProcessingStep['params'],
    }),
  ].map((item) => [item.id, item])
)

const step = (id: string, options: Record<string, unknown> = {}): RecipeStep => ({
  plugin: id,
  options,
})

describe('무엇이 있는가', () => {
  it('아무것도 안 했으면 장비가 준 열뿐이다', () => {
    expect(columnsAt([], 0, SOURCE, CATALOG).sort()).toEqual([...SOURCE].sort())
  })

  it('공칭 변환 뒤에는 변형률·응력이 있다', () => {
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    // **핵심.** 두 번째 단계를 시작하는 시점에는 이미 열이 있다 —
    // 돌려 보지 않아도 안다.
    expect(columnsAt(steps, 1, SOURCE, CATALOG)).toContain('strain_engineering')
    expect(columnsAt(steps, 1, SOURCE, CATALOG)).toContain('stress_engineering')
  })

  it('자기 앞의 것만 센다', () => {
    const steps = [step('tensile.strength'), step('tensile.engineering')]
    // 순서를 거꾸로 놓으면 첫 단계에는 아직 변형률 열이 없다.
    expect(columnsAt(steps, 0, SOURCE, CATALOG)).not.toContain('strain_engineering')
  })

  it('평활은 고른 열에 따라 이름이 달라진다', () => {
    const smooth = step('curve.smooth', { column: 'force' })
    expect(madeColumns(smooth, CATALOG)).toEqual(['force_smoothed'])
    expect(madeColumns(step('curve.smooth', { column: 'stress_engineering' }), CATALOG)).toEqual([
      'stress_engineering_smoothed',
    ])
  })

  it('안 고른 틀은 그대로 남는다 — 없는 열을 지어내지 않는다', () => {
    expect(resolveTemplate('{column}_smoothed', {})).toBe('{column}_smoothed')
  })

  it('값도 앞 단계에서 온다', () => {
    const steps = [step('tensile.elastic_modulus'), step('tensile.proof_stress')]
    expect(valuesAt(steps, 1, CATALOG).has('youngs_modulus')).toBe(true)
    expect(valuesAt(steps, 0, CATALOG).has('youngs_modulus')).toBe(false)
  })
})

describe('지금 이 단계를 쓸 수 있는가', () => {
  it('필요한 열이 있으면 막지 않는다', () => {
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    expect(blockersAt(steps[1], 1, steps, SOURCE, CATALOG)).toEqual([])
  })

  it('공칭 변환 없이 인장강도를 놓으면 이유를 말한다', () => {
    const steps = [step('tensile.strength')]
    const blocked = blockersAt(steps[0], 0, steps, SOURCE, CATALOG)
    expect(blocked).toHaveLength(2)
    expect(blocked[0].reason).toContain('strain_engineering')
    // **누가 그 열을 만드는지까지 말한다.** "없다" 만으로는 다음에 뭘 해야
    // 하는지 알 수 없다.
    expect(blocked[0].fixedBy).toBe('tensile.engineering')
  })

  it('안 고른 기준 열은 고르라고 한다', () => {
    const steps = [step('curve.sort_unique')]
    const blocked = blockersAt(steps[0], 0, steps, SOURCE, CATALOG)
    expect(blocked[0].reason).toContain('기준 열')
  })

  it('탄성계수를 안 넣고 항복강도를 넣으면 막힌다', () => {
    const steps = [step('tensile.proof_stress')]
    const blocked = blockersAt(steps[0], 0, steps, SOURCE, CATALOG)
    expect(blocked[0].fixedBy).toBe('tensile.elastic_modulus')
  })

  it('시편에서 오는 값은 앞 단계를 요구하지 않는다', () => {
    // 게이지 길이는 곡선에 없고 시편 기록에 있다. 이걸 "앞 단계가 만들어야
    // 하는 값" 으로 세면 첫 단계부터 막힌다.
    const steps = [step('tensile.engineering', { gauge_length: '@specimen_gauge_length' })]
    expect(blockersAt(steps[0], 0, steps, SOURCE, CATALOG)).toEqual([])
  })
})

describe('어디에 끼우는가', () => {
  it('권장 순서를 지키는 자리에 넣는다', () => {
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    // 탄성계수(50)는 공칭(10)과 인장강도(70) 사이다. 끝에 붙이면
    // 항복강도가 그 앞에 남아 `@youngs_modulus` 가 안 풀린다.
    expect(insertionIndex(steps, 'tensile.elastic_modulus', CATALOG)).toBe(1)
    expect(insertionIndex(steps, 'curve.sort_unique', CATALOG)).toBe(1)
    expect(insertionIndex([], 'tensile.strength', CATALOG)).toBe(0)
  })

  it('손으로 옮겨 순서가 뒤집혔는지 안다', () => {
    expect(outOfOrder([step('tensile.engineering'), step('tensile.strength')], CATALOG)).toBe(
      false
    )
    expect(outOfOrder([step('tensile.strength'), step('tensile.engineering')], CATALOG)).toBe(
      true
    )
  })
})
