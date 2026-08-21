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
import { RightPanelHost } from '@/shared/layout/RightPanel'
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

const made = (key: string, label: string, si_unit = '1', help: string | null = null) => ({
  key,
  label,
  si_unit,
  help,
})

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
    makes_columns: [
      made('strain_engineering', '공칭 변형률', '1', '변위 ÷ 게이지 길이.'),
      made('stress_engineering', '공칭 응력', 'Pa'),
    ],
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
    makes_values: [made('youngs_modulus', '탄성계수', 'Pa', '탄성 구간의 기울기.')],
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
    makes_values: [made('tensile_strength', '인장강도', 'Pa')],
    order: 70,
  },
] as unknown as ProcessingStep[]

/** 장비가 실제로 주는 것. 응력도 변형률도 없다. */
const SOURCE = ['displacement', 'force', 'width']

function show() {
  return render(
    <>
      {/* 변수 목록은 **껍데기의 오른쪽 영역**에 산다. 그 자리가 없으면 아무
          데도 안 뜬다 — 시험에서도 껍데기 몫을 같이 그린다. */}
      <RightPanelHost />
      <ProcessingPanel
        testRunId="run-1"
        // 인장이 아닌 종류로 연다 — 인장은 기본 순서가 미리 깔려서 "처음엔
        // 아무것도 안 켜져 있다" 를 볼 수 없다.
        testTypeKey="flexural"
        curveKey="curve-1"
        sourceColumns={SOURCE}
        sourceChannels={[
          { key: 'displacement', label: '변위', si_unit: 'm' },
          { key: 'force', label: '하중', si_unit: 'N' },
        ]}
      />
    </>
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

  it('돌려 보기는 늘 눌린다 — 회색 버튼은 이유를 말할 자리가 없다', async () => {
    show()
    await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    expect(screen.getByRole('button', { name: '돌려 보기' })).not.toBeDisabled()
  })

  it('아무것도 안 켜고 누르면 무엇부터 켜야 하는지 말한다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    await user.click(screen.getByRole('button', { name: '돌려 보기' }))

    expect(await screen.findByText(/켠 단계가 없습니다/)).toBeInTheDocument()
    // 단계가 없으면 서버를 부르지 않는다 — 부를 것이 없다.
    expect(preview).not.toHaveBeenCalled()
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

describe('변수 목록', () => {
  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
  })

  /** 오른쪽 사이드바. 창이 아니라 화면 가장자리에 붙는다. */
  const sidebar = () => screen.getByRole('complementary')
  const openSidebar = async (user: ReturnType<typeof userEvent.setup>) =>
    user.click(await screen.findByRole('button', { name: '변수 목록 펴기' }))

  it('기본은 접혀 있고, 여는 손잡이가 그 자리에 있다', async () => {
    // **머리에 버튼을 두지 않는다.** "저 버튼이 여는 것이 어느 쪽인가" 를 한 번
    // 더 생각해야 하고, 접혔을 때 오른쪽 가장자리에 남는 띠가 곧 그 자리다.
    show()
    const handle = await screen.findByRole('button', { name: '변수 목록 펴기' })
    expect(handle).toHaveAttribute('aria-expanded', 'false')
    expect(sidebar()).not.toHaveTextContent('곡선의 세로줄')
  })

  it('가장자리에서 열고 닫는다', async () => {
    const user = userEvent.setup()
    show()
    await openSidebar(user)
    expect(sidebar()).toHaveTextContent('곡선의 세로줄')

    await user.click(screen.getByRole('button', { name: '변수 목록 접기' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '변수 목록 펴기' })).toBeInTheDocument()
    )
  })

  it('이름만이 아니라 뜻과 단위를 함께 보여 준다', async () => {
    // **`strain_engineering` 만 보여 주면 그게 무엇인지 코드를 읽어야 안다.**
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))
    await openSidebar(user)

    expect(sidebar()).toHaveTextContent('strain_engineering')
    expect(sidebar()).toHaveTextContent('공칭 변형률')
    expect(sidebar()).toHaveTextContent('변위 ÷ 게이지 길이.')
    expect(sidebar()).toHaveTextContent('Pa')
  })

  it('원본 채널도 이름으로 읽힌다', async () => {
    const user = userEvent.setup()
    show()
    await openSidebar(user)

    expect(sidebar()).toHaveTextContent('displacement')
    expect(sidebar()).toHaveTextContent('변위')
    // 어디서 왔는지도 말한다 — 계산이 만든 것과 장비가 준 것은 다르다.
    expect(sidebar()).toHaveTextContent('장비 파일')
  })

  it('값은 어느 단계가 내는지 말한다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))
    await user.click(await screen.findByRole('button', { name: /탄성계수/ }))
    await openSidebar(user)

    expect(sidebar()).toHaveTextContent('youngs_modulus')
    expect(sidebar()).toHaveTextContent('탄성 구간의 기울기.')
  })

  it('안 켠 단계가 만드는 것은 안 보인다', async () => {
    // 다 보이면 "있는데 왜 못 고르지" 가 된다 — 그건 순서도가 답할 질문이다.
    const user = userEvent.setup()
    show()
    await openSidebar(user)

    expect(sidebar()).not.toHaveTextContent('strain_engineering')
  })

  it('열어 둔 채로 단계를 켜면 따라 는다', async () => {
    // 옆에 두는 이유가 이것이다 — 창이면 열었다 닫았다를 반복하게 된다.
    const user = userEvent.setup()
    show()
    await openSidebar(user)
    expect(sidebar()).not.toHaveTextContent('strain_engineering')

    await user.click(screen.getByRole('button', { name: /공칭 응력-변형률/ }))
    await waitFor(() => expect(sidebar()).toHaveTextContent('strain_engineering'))
  })
})

describe('돌려 보기가 막힐 때', () => {
  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
    preview.mockReset()
    preview.mockResolvedValue({
      source_curve_key: 'curve-1',
      source_row_count: 100,
      row_count: 100,
      columns: [],
      units: {},
      stages: [],
      scalars: [],
      notes: [],
      points: [],
    })
  })

  it('누르기 전에는 조용하다', async () => {
    // 단계를 쌓는 동안 미리 붉게 물들어 있으면 그건 경고가 아니라 배경이 된다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /공칭 응력-변형률/ }))

    expect(screen.queryByText(/못 도는 단계가/)).not.toBeInTheDocument()
  })

  it('누르면 어느 단계가 왜 막혔는지 짚는다', async () => {
    const user = userEvent.setup()
    show()
    // 공칭 변환을 켜서 인장강도를 풀고, 그 다음 공칭 변환만 끈다 —
    // 인장강도는 남고 변형률 열은 사라진 상태가 된다.
    const engineering = await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    await user.click(engineering)
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))
    await user.click(engineering)

    await user.click(screen.getByRole('button', { name: '돌려 보기' }))

    const notice = await screen.findByText(/못 도는 단계가 1개 있습니다/)
    expect(notice).toBeInTheDocument()
    // **어디로 가야 하는지까지 말한다.** 이름만으로는 긴 목록에서 못 찾는다.
    expect(screen.getByRole('button', { name: /1단계 인장강도/ })).toBeInTheDocument()
  })

  it('막혀 보여도 서버에는 보낸다', async () => {
    // 이 판정은 선언에 기댄 추론이다. 틀렸으면 그냥 돌아가는 것이 맞다 —
    // 우리가 사람을 가두면 안 된다.
    const user = userEvent.setup()
    show()
    const engineering = await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    await user.click(engineering)
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))
    await user.click(engineering)

    await user.click(screen.getByRole('button', { name: '돌려 보기' }))
    await waitFor(() => expect(preview).toHaveBeenCalled())
  })

  it('고치기 시작하면 짚어 둔 것을 거둔다', async () => {
    const user = userEvent.setup()
    show()
    const engineering = await screen.findByRole('button', { name: /공칭 응력-변형률/ })
    await user.click(engineering)
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))
    await user.click(engineering)
    await user.click(screen.getByRole('button', { name: '돌려 보기' }))
    await screen.findByText(/못 도는 단계가/)

    // 다시 켜면 문제가 사라진다.
    await user.click(engineering)
    await waitFor(() => expect(screen.queryByText(/못 도는 단계가/)).not.toBeInTheDocument())
  })
})
