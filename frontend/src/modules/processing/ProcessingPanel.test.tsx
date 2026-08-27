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

import { configure, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProcessingPanel } from '@/modules/processing/ProcessingPanel'

/**
 * **기다리는 시간을 늘린다.** 기본은 1초인데, 이 파일은 무거운 패널을 서른 번
 * 넘게 그리고 그때마다 목록·레시피·들어오는 값을 받는다. 전체 스위트를 돌릴
 * 때(다른 파일과 함께) 1초를 넘겨 **간헐적으로 실패했다** — 두 번 물렸고, 혼자
 * 돌리면 늘 통과했다.
 *
 * 논리 문제를 덮는 것이 아니다. 늦게 오는 것을 기다리는 시간이지, 안 오는 것을
 * 기다리는 시간이 아니다 — 안 오면 5초 뒤에도 실패한다.
 */
configure({ asyncUtilTimeout: 5000 })
import {
  RightPanelHost,
  RightPanelProvider,
  useRightPanel,
} from '@/shared/layout/SidePanel'
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
    inputs: () => inputs(),
  },
}))

vi.mock('@/modules/tests/api', () => ({
  testsApi: { instrumentDimensions: () => dimensions() },
}))

/** 서버가 이 시험에 넣어 주는 값. **규격이 칸을 정하므로 시험마다 다르다.** */
const inputs = vi.fn(() => Promise.resolve([] as unknown[]))

const made = (key: string, label: string, si_unit = '1', help: string | null = null) => ({
  key,
  label,
  si_unit,
  help,
})

/**
 * 숫자 칸. 시편 값을 이어 붙일 수 있는 자리는 이쪽이다.
 *
 * **필수로 두지 않는다.** 여기서 지키는 것은 "값을 어떻게 잇는가" 이고, 덜 채운
 * 단계를 붉게 하는 것은 아래 자기 목록을 쓰는 묶음이 따로 본다.
 */
const number = (name: string, label: string, unit = 'm') => ({
  name,
  label,
  type: 'float',
  default: null,
  choices: [],
  choice_labels: {},
  unit,
  dimension: null,
  help: null,
  required: false,
  role: null,
  when: {},
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
  required: false,
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
    params: [
      number('gauge_length', '게이지 길이'),
      column('displacement', '변위 열', 'displacement'),
      column('force', '하중 열', 'force'),
    ],
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

/**
 * 순서도의 한 줄. 켠 줄은 **끄기 단추 + 이름 단추** 둘로 나뉘고, 안 켠 줄은
 * 하나다 — 어느 쪽이든 이름이 적힌 단추를 잡는다.
 */
const getStep = (label: string) =>
  screen.getAllByRole('button').find((node) => node.textContent?.includes(label))!
const findStep = async (label: string) => {
  await screen.findAllByRole('button')
  return getStep(label)
}
type User = ReturnType<typeof userEvent.setup>
/** 안 켠 줄을 누르면 켜진다. 켠 줄의 이름을 누르면 그 단계의 칸이 펴진다. */
const clickStep = async (user: User, label: string) => user.click(await findStep(label))
/** 켠 줄을 끄는 것은 이름이 아니라 왼쪽의 동그라미다. */
const turnOff = async (user: User, label: string) =>
  user.click(screen.getByRole('button', { name: new RegExp(`${label}.*끄기`) }))

/** 장비가 실제로 주는 것. 응력도 변형률도 없다. */
const SOURCE = ['displacement', 'force', 'width']

/** 상단 바 몫. 화면이 오른쪽 영역을 등록했을 때만 단추를 낸다. */
function FakeHeader() {
  const { label, open, toggle } = useRightPanel()
  if (!label) return null
  return (
    <button type="button" onClick={toggle} aria-pressed={open}>
      {label} {open ? '접기' : '펴기'}
    </button>
  )
}

function show() {
  return render(
    <RightPanelProvider>
      <FakeHeader />
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
    </RightPanelProvider>
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
    const rail = await findStep('공칭 응력-변형률')
    expect(rail).toBeInTheDocument()
    expect(getStep('인장강도')).toBeInTheDocument()
  })

  it('공칭 변환 전에는 인장강도를 켤 수 없고, 무엇이 먼저인지 말한다', async () => {
    show()
    const strength = await findStep('인장강도')
    // **회색이기만 하면 고장으로 읽힌다.** 이유가 같이 있어야 한다.
    expect(strength).toBeDisabled()
    expect(strength).toHaveTextContent('strain_engineering')
  })

  it('공칭 변환을 켜면 뒤 단계가 풀린다', async () => {
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')

    await waitFor(() =>
      expect(getStep('인장강도')).not.toBeDisabled()
    )
  })

  it('돌려 보기 전에도 변형률 열을 고를 수 있다', async () => {
    // **이 저장소에서 실제로 막혔던 자리.** 장비가 준 것은 변위·하중·폭뿐인데
    // 인장강도는 변형률 열을 고르라고 한다 — 그 열은 앞 단계가 만든다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')
    // 켠 줄의 이름을 누르면 그 단계의 칸이 펴진다.
    await clickStep(user, '인장강도')

    const picker = await screen.findByRole('combobox', { name: '변형률 열' })
    expect(picker).toHaveTextContent('strain_engineering')
    // **이름만이 아니라 뜻도 고르는 자리에 있다.**
    expect(picker).toHaveTextContent('공칭 변형률')
  })

  it('켠 순서와 상관없이 도는 순서는 권장 순서다', async () => {
    // 인장강도를 먼저 켤 수는 없으니, 공칭 → 인장강도 → 탄성계수 로 켠다.
    // 탄성계수(50)는 인장강도(70) 앞에 끼워져야 한다 — 끝에 붙이면 항복강도
    // 같은 뒤 단계가 `@youngs_modulus` 를 못 찾는다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')
    await clickStep(user, '탄성계수')

    await waitFor(() =>
      expect(getStep('탄성계수')).toHaveTextContent('2')
    )
    expect(getStep('인장강도')).toHaveTextContent('3')
  })

  it('돌려 보기는 늘 눌린다 — 회색 버튼은 이유를 말할 자리가 없다', async () => {
    show()
    await findStep('공칭 응력-변형률')
    expect(screen.getByRole('button', { name: '돌려 보기' })).not.toBeDisabled()
  })

  it('아무것도 안 켜고 누르면 무엇부터 켜야 하는지 말한다', async () => {
    const user = userEvent.setup()
    show()
    await findStep('공칭 응력-변형률')
    await user.click(screen.getByRole('button', { name: '돌려 보기' }))

    expect(await screen.findByText(/켠 단계가 없습니다/)).toBeInTheDocument()
    // 단계가 없으면 서버를 부르지 않는다 — 부를 것이 없다.
    expect(preview).not.toHaveBeenCalled()
  })

  it('끄면 다시 잠긴다', async () => {
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await waitFor(() => expect(getStep('인장강도')).not.toBeDisabled())

    await turnOff(user, '공칭 응력-변형률')
    await waitFor(() => expect(getStep('인장강도')).toBeDisabled())
  })
})

describe('변수 목록', () => {
  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
  })

  /** 껍데기의 오른쪽 영역. 여는 단추는 **상단 바**에 있다. */
  const sidebar = () => screen.getByRole('complementary')
  const openSidebar = async (user: ReturnType<typeof userEvent.setup>) =>
    user.click(await screen.findByRole('button', { name: '변수 목록 펴기' }))

  it('처리 화면을 열면 상단 바에 여는 단추가 생긴다 — 기본은 닫힘', async () => {
    // 처음에는 화면 오른쪽 끝의 흐린 세로 띠로 뒀는데 아무도 못 봤다.
    // 껍데기를 여닫는 단추는 왼쪽 사이드바 토글과 같은 자리에 있어야 한다.
    show()
    expect(await screen.findByRole('button', { name: '변수 목록 펴기' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('상단 바에서 열고 닫는다', async () => {
    const user = userEvent.setup()
    show()
    await openSidebar(user)
    expect(sidebar()).toHaveTextContent('곡선의 세로줄')

    await user.click(screen.getByRole('button', { name: '변수 목록 접기' }))
    await waitFor(() => expect(screen.queryByRole('complementary')).not.toBeInTheDocument())
  })

  it('이름만이 아니라 뜻과 단위를 함께 보여 준다', async () => {
    // **`strain_engineering` 만 보여 주면 그게 무엇인지 코드를 읽어야 안다.**
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
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
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '탄성계수')
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

    await user.click(getStep('공칭 응력-변형률'))
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
    await clickStep(user, '공칭 응력-변형률')

    expect(screen.queryByText(/못 도는 단계가/)).not.toBeInTheDocument()
  })

  it('누르면 어느 단계가 왜 막혔는지 짚는다', async () => {
    const user = userEvent.setup()
    show()
    // 공칭 변환을 켜서 인장강도를 풀고, 그 다음 공칭 변환만 끈다 —
    // 인장강도는 남고 변형률 열은 사라진 상태가 된다.
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')
    await turnOff(user, '공칭 응력-변형률')

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
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')
    await turnOff(user, '공칭 응력-변형률')

    await user.click(screen.getByRole('button', { name: '돌려 보기' }))
    await waitFor(() => expect(preview).toHaveBeenCalled())
  })

  it('고치기 시작하면 짚어 둔 것을 거둔다', async () => {
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')
    await turnOff(user, '공칭 응력-변형률')
    await user.click(screen.getByRole('button', { name: '돌려 보기' }))
    await screen.findByText(/못 도는 단계가/)

    // 다시 켜면 문제가 사라진다.
    await clickStep(user, '공칭 응력-변형률')
    await waitFor(() => expect(screen.queryByText(/못 도는 단계가/)).not.toBeInTheDocument())
  })
})

describe('접힌 줄이 설정을 말한다', () => {
  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
  })

  it('열지 않아도 무엇으로 설정됐는지 보인다', async () => {
    // **하나하나 열어서 확인해야 하면 접어 둔 뜻이 없다.**
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')

    const row = getStep('인장강도')
    expect(row).toHaveTextContent('strain_engineering')
    expect(row).toHaveTextContent('stress_engineering')
  })

  it('여러 단계를 나란히 펴 둘 수 있다', async () => {
    // 아코디언(한 번에 하나)이면 견주려고 왔다 갔다 해야 한다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')

    await clickStep(user, '공칭 응력-변형률') // 펴기
    await clickStep(user, '인장강도') // 펴기

    expect(await screen.findByRole('combobox', { name: '변위 열' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '변형률 열' })).toBeInTheDocument()
  })

  it('모두 펴기 한 번으로 전부 본다', async () => {
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '인장강도')

    await user.click(screen.getByRole('button', { name: '모두 펴기' }))
    expect(await screen.findByRole('combobox', { name: '변위 열' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '변형률 열' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '모두 접기' }))
    await waitFor(() =>
      expect(screen.queryByRole('combobox', { name: '변위 열' })).not.toBeInTheDocument()
    )
  })
})

describe('덜 채운 단계는 붉다', () => {
  beforeEach(() => {
    steps.mockResolvedValue([
      {
        ...CATALOG[0],
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
        ],
      },
      ...CATALOG.slice(1),
    ] as unknown as ProcessingStep[])
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
  })

  it('돌려 보기를 누르기 전에도 표시된다', async () => {
    // **누를 때까지 기다리면 스무 줄을 다 훑고 나서야 어디가 빈지 안다.**
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')

    const row = getStep('공칭 응력-변형률')
    expect(row).toHaveTextContent('덜 채움')
    // **붉기만 하면 열어 봐야 안다.** 무엇이 없는지 그 줄에 적는다.
    expect(row).toHaveTextContent('게이지 길이을(를) 채워야 합니다.')
  })

  it('채우면 표시가 사라지고 설정 요약으로 돌아간다', async () => {
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률') // 펴기

    await user.type(await screen.findByLabelText('게이지 길이'), '50')
    await user.click(screen.getByRole('button', { name: '모두 접기' }))

    await waitFor(() => expect(getStep('공칭 응력-변형률')).not.toHaveTextContent('덜 채움'))
    expect(getStep('공칭 응력-변형률')).toHaveTextContent('게이지 길이 50 mm')
  })
})

describe('시편 값 이어 붙이기', () => {
  const GIVEN = [
    {
      key: 'specimen_gauge_length',
      label: '시편 게이지 길이',
      value: 0.05,
      si_unit: 'm',
      dimension: null,
      source: 'run',
    },
  ]

  beforeEach(() => {
    steps.mockResolvedValue(CATALOG)
    recipes.mockResolvedValue([])
    dimensions.mockResolvedValue({ items: [] })
    preview.mockReset()
    inputs.mockResolvedValue(GIVEN)
  })

  it('올 값이 있는 칸에만 버튼이 붙는다', async () => {
    // **화면에 이름을 박아 두지 않는다.** 규격에 칸을 더하면 저절로 따라오고,
    // 올 값이 없으면 안 붙는다 — 눌러 봐야 돌릴 때 "그 값이 없습니다" 다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률') // 켠 줄을 한 번 더 누르면 칸이 펴진다

    expect(await screen.findByRole('button', { name: /자동 연결 · 시편 게이지 길이/ })).toBeInTheDocument()
    // 이 시험에는 단면적이 안 왔다.
    expect(screen.queryByRole('button', { name: /자동 연결 · .*단면적/ })).not.toBeInTheDocument()
  })

  it('이어 붙이면 그 값이 몇인지 보여 준다', async () => {
    // **규격의 공칭과 그 시편의 실측은 뜻이 조금 다르다.** 얼마인지 모르면
    // 고칠지 말지를 판단할 수 없다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률')
    await user.click(await screen.findByRole('button', { name: /자동 연결 · 시편 게이지 길이/ }))

    expect(await screen.findByText(/지금 50 mm/)).toBeInTheDocument()
  })

  it('이어 붙이지 않아도 갖고 도는 값이 보인다', async () => {
    // **실사용에서 나왔다** — *"시험에서 나온 두께 같은 값은 처리에서 어디서 보고
    // 써? 안 보이는데?"*. 값은 서버가 이미 보내고 있었는데 **이어 붙인 칸
    // 안에서만** 보였다. 인장 표준 레시피가 잇는 것은 단면적과 게이지라,
    // 두께·폭은 어디에도 안 떴다.
    inputs.mockResolvedValue([
      { ...GIVEN[0], key: 'specimen_thickness', label: '시편 두께', value: 0.000986 },
    ])
    show()
    // 단계를 하나도 안 켰는데도 보인다.
    expect(await screen.findByText(/시편 규격이 정한 칸/)).toBeInTheDocument()
    expect(screen.getByText(/0.986 mm/)).toBeInTheDocument()
    expect(screen.getByText(/이 시험이 잰 값/)).toBeInTheDocument()
  })

  it('치수와 조건을 나눠 보인다', async () => {
    // **선언한 곳이 다르다** — 치수는 시편 규격이, 조건은 시험 종류가 정한다.
    // 한 줄에 섞으면 사람은 둘을 같은 자리에서 정하는 줄 안다(실사용에서 나왔다).
    inputs.mockResolvedValue([
      { ...GIVEN[0], key: 'specimen_thickness', label: '시편 두께', value: 0.000986 },
      {
        key: 'condition_preload',
        label: '예하중',
        value: 20,
        si_unit: 'N',
        dimension: null,
        source: 'condition',
      },
    ])
    show()
    expect(await screen.findByText(/시편 규격이 정한 칸/)).toBeInTheDocument()
    expect(screen.getByText(/시험 종류가 정한 칸/)).toBeInTheDocument()
  })

  it('그 값이 어디서 왔는지 말한다', async () => {
    // **치수는 세 곳에 살 수 있다** — 이 시험이 잰 값 · 시편에 적힌 값 · 규격
    // 공칭(v1.118.0). 안 보이면 사람이 "어느 게 맞느냐" 에 답할 수 없고, 그러면
    // 그 자리가 조용히 틀리는 자리가 된다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률')
    await user.click(await screen.findByRole('button', { name: /자동 연결 · 시편 게이지 길이/ }))

    // **이어 붙인 자리 안에서 본다.** 같은 글자가 위쪽 「갖고 도는 값」 에도
    // 있어서, 화면 전체에서 찾으면 둘이 잡힌다.
    const shown = await screen.findByText(/지금 50 mm/)
    expect(shown.parentElement).toHaveTextContent('이 시험이 잰 값')
  })

  it('시편에서 온 값이면 그렇게 말한다', async () => {
    inputs.mockResolvedValue([{ ...GIVEN[0], source: 'measured' }])
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률')
    await user.click(await screen.findByRole('button', { name: /자동 연결 · 시편 게이지 길이/ }))

    const shown = await screen.findByText(/지금 50 mm/)
    expect(shown.parentElement).toHaveTextContent('시편에 적힌 값')
  })

  it('이어 붙인 값을 그 자리에서 고칠 수 있다', async () => {
    // **객체처럼 묶여서 못 고치면 안 된다.** 규격상 치수와 이 시편의 치수는
    // 다를 수 있다 — 지금 값을 그대로 옮겨 담고 거기서부터 고친다.
    const user = userEvent.setup()
    show()
    await clickStep(user, '공칭 응력-변형률')
    await clickStep(user, '공칭 응력-변형률')
    await user.click(await screen.findByRole('button', { name: /자동 연결 · 시편 게이지 길이/ }))
    await user.click(await screen.findByRole('button', { name: '숫자로 고정' }))

    // 잇기 전 기본값(빈 칸)이 아니라 **이어 붙었던 값**이 남는다.
    expect(await screen.findByLabelText<HTMLInputElement>('게이지 길이')).toHaveValue('50')
  })
})
