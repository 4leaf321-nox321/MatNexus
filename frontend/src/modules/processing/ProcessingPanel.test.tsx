/**
 * 처리 순서도 — **무엇을 어떤 순서로 놓을지 화면이 말하는가.**
 *
 * 관측된 말 셋이 이 파일의 이유다.
 *
 *   1. "단계 순서가 의미가 있어?" — 있다. 뒤 단계는 앞 단계가 만든 열로 돈다.
 *   2. "처음 데이터에 변위·힘·폭만 있는데 변형률 열을 고를 수가 없다" — 그 열은
 *      앞 단계가 만든다. 돌려 보기 전에도 목록에 있어야 한다.
 *   3. "무엇을 넣어야 하는지 파악하기 어렵다" — 순서도에서 켜고 끈다.
 *
 * 그래서 여기서는 **켜고 끄면서** 잠금과 목록이 따라오는지 본다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProcessingPanel } from '@/modules/processing/ProcessingPanel'
import type { ProcessingStep } from '@/modules/processing/api'

const steps = vi.fn()
const recipes = vi.fn()
const preview = vi.fn()
const dimensions = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: {
    steps: () => steps(),
    recipes: () => recipes(),
    preview: (...args: unknown[]) => preview(...args),
  },
}))

vi.mock('@/modules/tests/api', () => ({
  testsApi: { instrumentDimensions: () => dimensions() },
}))

const column = (name: string, label: string, dflt: string | null = null) => ({
  name,
  label,
  type: 'str',
  default: dflt,
  choices: [],
  choice_labels: {},
  unit: null,
  dimension: null,
  help: null,
  role: 'column',
  when: {},
})

/** 서버가 주는 그대로 — **권장 순서로 정렬돼 온다.** */
const CATALOG = [
  {
    id: 'tensile.engineering',
    label: '공칭 응력-변형률',
    version: '1',
    applies_to: ['tensile'],
    params: [column('displacement', '변위 열', 'displacement'), column('force', '하중 열', 'force')],
    makes_columns: ['strain_engineering', 'stress_engineering'],
    makes_values: [],
    order: 10,
  },
  {
    id: 'tensile.elastic_modulus',
    label: '탄성계수',
    version: '1',
    applies_to: ['tensile'],
    params: [
      column('strain', '변형률 열', 'strain_engineering'),
      column('stress', '응력 열', 'stress_engineering'),
    ],
    makes_columns: [],
    makes_values: ['youngs_modulus'],
    order: 50,
  },
  {
    id: 'tensile.strength',
    label: '인장강도·연신율',
    version: '1',
    applies_to: ['tensile'],
    params: [
      column('strain', '변형률 열', 'strain_engineering'),
      column('stress', '응력 열', 'stress_engineering'),
    ],
    makes_columns: [],
    makes_values: ['tensile_strength'],
    order: 70,
  },
] as unknown as ProcessingStep[]

/** 장비가 실제로 주는 것. 응력도 변형률도 없다. */
const SOURCE = ['displacement', 'force', 'width']

function show() {
  return render(
    <ProcessingPanel
      testRunId="run-1"
      // 인장이 아닌 종류로 연다 — 인장은 기본 순서가 미리 깔려서 "처음엔 아무것도
      // 안 켜져 있다" 를 볼 수 없다.
      testTypeKey="flexural"
      curveKey="curve-1"
      sourceColumns={SOURCE}
    />
  )
}

describe('처리 순서도', () => {
  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
    preview.mockReset()
  })

  it('순서도가 권장 순서대로 보인다', async () => {
    show()
    const rail = await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    expect(rail).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /인장강도/ })).toBeInTheDocument()
  })

  it('공칭 변환 전에는 인장강도를 켤 수 없고, 무엇이 먼저인지 말한다', async () => {
    show()
    const strength = await screen.findByRole('button', { name: /인장강도/ })
    // **회색이기만 하면 고장으로 읽힌다.** 이유가 같이 있어야 한다.
    expect(strength).toBeDisabled()
    expect(strength).toHaveTextContent('strain_engineering')
  })

  it('공칭 변환을 켜면 뒤 단계가 풀린다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /인장강도/ })).not.toBeDisabled()
    )
  })

  it('돌려 보기 전에도 변형률 열을 고를 수 있다', async () => {
    // **이 저장소에서 실제로 막혔던 자리.** 장비가 준 것은 변위·하중·폭뿐인데
    // 인장강도는 변형률 열을 고르라고 한다 — 그 열은 앞 단계가 만든다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))

    // 단계 카드의 '변형률 열' 선택기가 앞 단계가 만들 열을 갖고 있다.
    const picker = await screen.findByRole('combobox', { name: '변형률 열' })
    expect(picker).toHaveTextContent('strain_engineering')
  })

  it('켠 순서와 상관없이 도는 순서는 권장 순서다', async () => {
    // 인장강도를 먼저 켤 수는 없으니, 공칭 → 인장강도 → 탄성계수 로 켠다.
    // 탄성계수(50)는 인장강도(70) 앞에 끼워져야 한다 — 끝에 붙이면 항복강도
    // 같은 뒤 단계가 `@youngs_modulus` 를 못 찾는다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))
    await user.click(await screen.findByRole('button', { name: /탄성계수/ }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /탄성계수/ })).toHaveTextContent('2')
    )
    expect(screen.getByRole('button', { name: /인장강도/ })).toHaveTextContent('3')
  })

  it('아무것도 안 켜면 돌려 볼 수 없다', async () => {
    show()
    await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    expect(screen.getByRole('button', { name: '돌려 보기' })).toBeDisabled()
  })

  it('필요한 것이 갖춰지면 돌려 볼 수 있다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '돌려 보기' })).not.toBeDisabled()
    )
  })

  it('끄면 다시 잠긴다', async () => {
    const user = userEvent.setup()
    show()
    const engineering = await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    await user.click(engineering)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /인장강도/ })).not.toBeDisabled()
    )

    await user.click(engineering)
    await waitFor(() => expect(screen.getByRole('button', { name: /인장강도/ })).toBeDisabled())
  })
})
