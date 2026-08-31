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
  flowRows,
  insertionIndex,
  madeColumns,
  outOfOrder,
  resolveTemplate,
  stepIO,
  stepSummary,
  valuesAt,
} from '@/modules/processing/flow'
import type { ProcessingStep, RecipeStep } from '@/modules/processing/api'

const SOURCE = ['displacement', 'force', 'width']

const made = (key: string, label: string, si_unit = '1') => ({ key, label, si_unit, help: null })

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
  required: false,
  role: 'column',
  when: {},
})

const CATALOG = new Map<string, ProcessingStep>(
  [
    plugin({
      id: 'tensile.engineering',
      order: 10,
      makes_columns: [
        made('strain_engineering', '공칭 변형률'),
        made('stress_engineering', '공칭 응력', 'Pa'),
      ],
      params: [
        column('displacement', '변위 열', 'displacement'),
        column('force', '하중 열', 'force'),
      ] as ProcessingStep['params'],
    }),
    plugin({ id: 'curve.sort_unique', order: 20, params: [column('x', '기준 열')] as ProcessingStep['params'] }),
    plugin({
      id: 'curve.smooth',
      order: 45,
      makes_columns: [made('{column}_smoothed', '평활한 열')],
      params: [column('column', '평활할 열')] as ProcessingStep['params'],
    }),
    plugin({
      id: 'tensile.elastic_modulus',
      order: 50,
      makes_values: [made('youngs_modulus', '탄성계수', 'Pa')],
    }),
    plugin({
      id: 'tensile.proof_stress',
      order: 60,
      makes_values: [made('proof_stress', '항복강도', 'Pa')],
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
    expect(madeColumns(smooth, CATALOG).map((item) => item.key)).toEqual(['force_smoothed'])
    expect(
      madeColumns(step('curve.smooth', { column: 'stress_engineering' }), CATALOG).map(
        (item) => item.key
      )
    ).toEqual(['stress_engineering_smoothed'])
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

describe('순서도 줄', () => {
  it('켠 것은 도는 순서대로, 안 켠 것은 갈 자리에', () => {
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    const rows = flowRows(steps, CATALOG, [...CATALOG.values()])
    const names = rows.map((row) =>
      row.kind === 'step' ? `${row.index + 1}:${row.step.plugin}` : `-:${row.plugin.id}`
    )
    // 탄성계수(50)는 공칭(10)과 인장강도(70) 사이에 끼어 보인다 —
    // **켜면 어디로 들어가는지가 그 자리에서 보인다.**
    expect(names).toEqual([
      '1:tensile.engineering',
      '-:curve.sort_unique',
      '-:curve.smooth',
      '-:tensile.elastic_modulus',
      '-:tensile.proof_stress',
      '2:tensile.strength',
    ])
  })

  it('손으로 순서를 바꾸면 바꾼 순서대로 보인다', () => {
    // 순서도가 권장 순서로 우기면 **실제로 도는 순서와 다른 그림**이 된다.
    const steps = [step('tensile.strength'), step('tensile.engineering')]
    const rows = flowRows(steps, CATALOG, [...CATALOG.values()])
    const chosen = rows.filter((row) => row.kind === 'step')
    expect(chosen.map((row) => (row.kind === 'step' ? row.step.plugin : ''))).toEqual([
      'tensile.strength',
      'tensile.engineering',
    ])
  })

  it('아무것도 안 켜면 권장 순서 그대로다', () => {
    const rows = flowRows([], CATALOG, [...CATALOG.values()])
    expect(rows.every((row) => row.kind === 'available')).toBe(true)
    expect(rows).toHaveLength(CATALOG.size)
  })
})

describe('접힌 줄의 요약', () => {
  const withParams = (over: Partial<ProcessingStep> & { id: string }) =>
    plugin({
      ...over,
      params: [
        {
          name: 'gauge_length',
          label: '게이지 길이',
          type: 'float',
          default: null,
          choices: [],
          choice_labels: {},
          unit: 'm',
          dimension: null,
          help: null,
          required: false,
          role: null,
          when: {},
        },
        {
          name: 'method',
          label: '방법',
          type: 'choice',
          default: 'linear_regression',
          choices: ['linear_regression', 'manual'],
          choice_labels: { linear_regression: '최소제곱 회귀', manual: '직접 입력' },
          unit: null,
          dimension: null,
          help: null,
          required: false,
          role: null,
          when: {},
        },
        {
          name: 'manual_modulus',
          label: '직접 입력',
          type: 'float',
          default: null,
          choices: [],
          choice_labels: {},
          unit: 'Pa',
          dimension: null,
          help: null,
          role: null,
          when: { method: ['manual'] },
        },
      ] as ProcessingStep['params'],
    })

  const CAT = new Map<string, ProcessingStep>([
    ['x', withParams({ id: 'x' })],
    ...CATALOG,
  ])

  it('저장은 SI 지만 사람이 읽는 단위로 적는다', () => {
    // 0.05 m 를 그대로 적으면 아무도 못 읽는다. mm 로 적는다.
    const text = stepSummary(step('x', { gauge_length: 0.05 }), CAT)
    expect(text).toContain('게이지 길이 50 mm')
  })

  it('고른 값은 사람이 읽는 이름으로', () => {
    expect(stepSummary(step('x', {}), CAT)).toContain('최소제곱 회귀')
  })

  it('지금 안 쓰이는 칸은 빼고 적는다', () => {
    // 방법이 회귀면 '직접 입력' 은 아무 데도 안 쓰인다. 그걸 적으면 요약이
    // 거짓말이 된다.
    const text = stepSummary(step('x', { manual_modulus: 210e9 }), CAT)
    expect(text).not.toContain('직접 입력')

    const manual = stepSummary(step('x', { method: 'manual', manual_modulus: 210e9 }), CAT)
    expect(manual).toContain('직접 입력')
  })

  it('시편에서 오는 값은 사람이 읽는 이름으로 적는다', () => {
    // 이름은 **서버가 준다** — 규격이 칸을 정하므로 화면이 목록을 들 수 없다.
    const given = new Map([
      [
        'specimen_gauge_length',
        { key: 'specimen_gauge_length', label: '시편 게이지 길이' },
      ],
    ] as const) as never
    const text = stepSummary(
      step('x', { gauge_length: '@specimen_gauge_length' }),
      CAT,
      given
    )
    expect(text).toContain('시편 게이지 길이')
  })

  it('이름을 모르면 원문을 그대로 적는다', () => {
    // 감추면 "빈 칸" 으로 읽힌다. 모르는 것은 모르는 대로 보여 주는 편이 낫다.
    const text = stepSummary(step('x', { gauge_length: '@specimen_gauge_length' }), CAT)
    expect(text).toContain('specimen_gauge_length')
  })

  it('열 이름은 그대로 적는다', () => {
    expect(stepSummary(step('tensile.strength', {}), CATALOG)).toContain('strain_engineering')
  })
})

describe('필수 칸이 비면 막힌다', () => {
  const CAT = new Map<string, ProcessingStep>([
    [
      'needs',
      plugin({
        id: 'needs',
        order: 5,
        params: [
          {
            name: 'gauge_length',
            label: '게이지 길이',
            type: 'float',
            default: null,
            choices: [],
            choice_labels: {},
            unit: 'm',
            dimension: null,
            help: null,
            required: true,
            role: null,
            when: {},
          },
          {
            name: 'method',
            label: '방법',
            type: 'choice',
            default: 'auto',
            choices: ['auto', 'manual'],
            choice_labels: {},
            unit: null,
            dimension: null,
            help: null,
            required: false,
            role: null,
            when: {},
          },
          {
            name: 'manual_modulus',
            label: '직접 입력',
            type: 'float',
            default: null,
            choices: [],
            choice_labels: {},
            unit: 'Pa',
            dimension: null,
            help: null,
            required: true,
            role: null,
            when: { method: ['manual'] },
          },
        ] as ProcessingStep['params'],
      }),
    ],
  ])

  it('비면 무엇을 채워야 하는지 말한다', () => {
    const steps = [step('needs', {})]
    const blocked = blockersAt(steps[0], 0, steps, SOURCE, CAT)
    expect(blocked.map((item) => item.reason)).toEqual(['게이지 길이을(를) 채워야 합니다.'])
  })

  it('채우면 풀린다', () => {
    const steps = [step('needs', { gauge_length: 0.05 })]
    expect(blockersAt(steps[0], 0, steps, SOURCE, CAT)).toEqual([])
  })

  it('지금 안 쓰이는 칸은 비어도 막지 않는다', () => {
    // 방법이 'auto' 면 '직접 입력' 은 아무 데도 안 쓰인다. 그걸 붉게 칠하면
    // 멀쩡한 구성을 고장으로 읽게 된다.
    const steps = [step('needs', { gauge_length: 0.05, method: 'auto' })]
    expect(blockersAt(steps[0], 0, steps, SOURCE, CAT)).toEqual([])

    const manual = [step('needs', { gauge_length: 0.05, method: 'manual' })]
    expect(blockersAt(manual[0], 0, manual, SOURCE, CAT)).toHaveLength(1)
  })
})

describe('stepIO — 단계 사이로 무엇이 흘러가나', () => {
  /** 바깥에서 오는 값과 조건부 칸을 가진 단계를 얹은 목록. */
  const CATALOG2 = new Map(CATALOG)
  CATALOG2.set(
    'tensile.engineering2',
    plugin({
      id: 'tensile.engineering2',
      order: 10,
      makes_columns: [made('strain_engineering', '공칭 변형률')],
      params: [
        column('displacement', '변위 열', 'displacement'),
        { ...column('gauge_length', '게이지 길이'), role: null, default: '@specimen_gauge_length' },
        { ...column('manual', '직접 입력'), role: null, when: { method: ['manual'] } },
      ] as ProcessingStep['params'],
    })
  )

  it('열·값·시편에서 오는 것을 갈래로 가른다', () => {
    const steps = [step('tensile.engineering2', { manual: '@youngs_modulus' })]
    const io = stepIO(steps[0], 0, steps, SOURCE, CATALOG2)

    expect(io.takes.find((one) => one.key === 'displacement')?.kind).toBe('channel')
    // **시편에서 오는 것은 따로 센다.** 「앞 단계가 만들어야 할 값」 으로 세면
    // 첫 단계부터 빨갛게 된다 — 그건 곡선이 아니라 시편 기록에 있다.
    const 게이지 = io.takes.find((one) => one.key === 'specimen_gauge_length')
    expect(게이지?.kind).toBe('specimen')
    expect(게이지?.present).toBe(true)
    expect(io.makes.map((one) => one.key)).toEqual(['strain_engineering'])
    // **내는 것의 이름은 계산이 선언한 한글이다.** `strain_engineering` 이
    // 무엇인지는 코드를 읽어야 알고, 그러면 아무도 안 읽는다.
    expect(io.makes[0].label).toBe('공칭 변형률')
  })

  it('받는 열도 한글 이름으로 적는다', () => {
    // 같은 열이 「내는 것」 에서는 공칭 변형률인데 「받는 것」 에서는
    // `strain_engineering` 이면, 같은 것인 줄 알아볼 수 없다.
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    const names = new Map([['strain_engineering', { label: '공칭 변형률' }]])
    const io = stepIO(steps[1], 1, steps, SOURCE, CATALOG, undefined, names)
    expect(io.takes.find((one) => one.key === 'strain_engineering')?.label).toBe('공칭 변형률')
    // 모르는 열은 키 그대로 — **지어내지 않는다.**
    expect(io.takes.find((one) => one.key === 'stress_engineering')?.label).toBe(
      'stress_engineering'
    )
  })

  it('지금 안 쓰이는 칸은 받는 것이 아니다', () => {
    // 방법이 '자동' 이면 '직접 입력' 칸의 값은 아무 데도 안 간다. 그것까지
    // 적으면 이 목록이 거짓말이 된다.
    const steps = [step('tensile.engineering2', { manual: '@youngs_modulus' })]
    const io = stepIO(steps[0], 0, steps, SOURCE, CATALOG2)
    expect(io.takes.map((one) => one.key)).not.toContain('youngs_modulus')
  })

  it('아직 없는 열은 지우지 않고 없다고 표시한다', () => {
    // **안 보이면 「이 단계는 그걸 안 쓰는구나」 로 읽힌다** — 못 받고 있다는
    // 사실이 사라진다.
    const steps = [step('tensile.strength')]
    const io = stepIO(steps[0], 0, steps, SOURCE, CATALOG)
    expect(io.takes.find((one) => one.key === 'strain_engineering')?.present).toBe(false)
  })

  it('앞 단계가 만들면 있는 것이 된다', () => {
    const steps = [step('tensile.engineering'), step('tensile.strength')]
    const io = stepIO(steps[1], 1, steps, SOURCE, CATALOG)
    expect(io.takes.find((one) => one.key === 'strain_engineering')?.present).toBe(true)
  })

  it('앞 단계의 스칼라는 값으로 센다', () => {
    const steps = [step('tensile.elastic_modulus'), step('tensile.proof_stress')]
    const io = stepIO(steps[1], 1, steps, SOURCE, CATALOG)
    const E = io.takes.find((one) => one.key === 'youngs_modulus')
    expect(E?.kind).toBe('scalar')
    expect(E?.present).toBe(true)
    expect(stepIO(steps[1], 0, steps, SOURCE, CATALOG).takes[0].present).toBe(false)
  })
})
