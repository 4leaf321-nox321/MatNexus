/**
 * 재료 물성 — **한눈에 답이 나오는가.**
 *
 * 계산이 맞는지는 백엔드가 본다. 여기서 보는 것은 배치다. 이 화면에 가장 자주
 * 하는 일은 **「그래서 이 재료 항복강도가 얼마인가」** 인데, 전에는 그 답이
 * 8열 표(항목·n·평균·중앙값·표준편차·CV·95%CI·이상치) 안에 있었고 묶음마다
 * 그 표가 세로로 쌓였다 — 방향이 셋이면 세 번 스크롤해야 셋을 견줬다.
 *
 * 무는 자리 넷:
 *
 *   1. **값이 맨 위에 있다.** 표를 읽지 않고도 얼마인지 안다.
 *   2. **방향이 열이다.** MD·TD 차이가 이 재료의 핵심인데 세로로 흩어져 있었다.
 *   3. **흔들리는 값이 그 자리에서 보인다.** 「이 평균을 믿어도 되나」 가 전에는
 *      8열 표의 맨 오른쪽, 가장 안 보이는 자리에 있었다.
 *   4. **할 말이 있는 묶음은 접지 않는다.** 접어 두면 아무도 안 보는데, 이 화면이
 *      그것을 알리려고 있다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PropertiesPanel } from '@/modules/statistics/PropertiesPanel'

const forMaterial = vi.fn()

vi.mock('@/modules/statistics/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/statistics/api')>(
      '@/modules/statistics/api'
    )
  return {
    ...actual,
    statisticsApi: {
      ...actual.statisticsApi,
      forMaterial: (...a: unknown[]) => forMaterial(...a),
    },
  }
})

vi.mock('@/modules/statistics/DistributionPanel', () => ({
  DistributionPanel: () => <div>분포</div>,
}))
vi.mock('@/modules/tests/CurveChart', () => ({ CurveChart: () => <div>곡선</div> }))

const scalar = (key: string, label: string, mean: number, sd: number | null, cv = 0.01) => ({
  key,
  label,
  count: 5,
  mean,
  median: mean,
  sample_sd: sd,
  coefficient_of_variation: cv,
  ci95_low: null,
  ci95_high: null,
  iqr: null,
  mad: null,
  minimum: mean,
  maximum: mean,
  outliers: [],
  si_unit: 'Pa',
  dimension: 'stress',
})

const group = (orientation: string, yieldMpa: number, over: Record<string, unknown> = {}) => ({
  test_type_key: 'tensile',
  test_type_label: '인장시험',
  orientation,
  sample_count: 5,
  skipped_unadopted: 0,
  notes: [],
  curve: null,
  test_run_ids: [],
  scalars: [
    scalar('yield_strength', '항복강도', yieldMpa * 1e6, 12e6),
    scalar('tensile_strength', '인장강도', 410e6, 8e6),
  ],
  ...over,
})

function show() {
  render(<PropertiesPanel materialId="m1" />)
}

/**
 * 요약 영역. **접힌 상세도 DOM 에 남아 있으므로** 범위를 좁히지 않으면 같은
 * 항목 이름이 여러 번 잡힌다.
 *
 * 요약은 **항목마다 카드**이고 여러 열에 흐른다 — 항목마다 값 개수가 달라
 * 격자로 두면 짧은 카드 밑에 빈칸이 크게 남기 때문이다.
 */
const summary = async () => within(await screen.findByLabelText('물성 요약'))

/**
 * 그 항목의 **첫 줄** 안에서만 찾는다.
 *
 * 같은 항목이 여러 곳에서 오면 행이 여럿이다(계산·묶음·선언). 첫 줄만 집으면
 * 「그 값이 있나」 는 못 보므로, 여러 줄을 함께 보는 시험은 `linesOf` 를 쓴다.
 */
const card = async (label: string) => within((await linesOf(label))[0])

/**
 * 그 항목의 모든 줄. **몇 줄을 기다릴지 말할 수 있다.**
 *
 * 표는 두 곳에서 채워진다 — 적어 둔 값(`declared` prop)은 첫 렌더에 이미 있고,
 * 잰 값(통계)은 조회가 끝난 뒤에 붙는다. 그래서 표가 뜨자마자 줄을 집으면
 * **적어 둔 줄만 있는 순간**을 잡을 수 있다. CI 에서 그렇게 깨졌다(2026-08-31):
 * 첫 줄에 「통계」 배지가 없다고 나왔는데, 그 순간 첫 줄은 선언 줄이었다.
 *
 * 두 곳에서 오는 것을 보는 시험은 `linesOf(label, 2)` 처럼 **몇 줄인지 적는다.**
 */
const linesOf = async (label: string, count = 1) => {
  const table = await summary()
  await waitFor(() =>
    expect(table.getAllByLabelText(label).length).toBeGreaterThanOrEqual(count)
  )
  return table.getAllByLabelText(label)
}

beforeEach(() => {
  vi.clearAllMocks()
  forMaterial.mockResolvedValue({ groups: [group('MD', 285), group('TD', 301)] })
})

describe('요약', () => {
  it('표를 읽지 않아도 값이 보인다', async () => {
    show()
    const one = await card('항복강도')
    expect(one.getAllByText(/285/).length).toBeGreaterThan(0)
  })

  it('같은 항목이 여러 곳에서 오면 나란히 둔다', async () => {
    // **겹쳐서 하나만 보이면 어느 방법의 값인지 사라진다** — 그리고 그 차이가
    // 볼 값의 전부일 때가 있다.
    show()
    // **줄이 둘로 선다.** 겹쳐서 하나만 보이면 어느 방법의 값인지 사라진다.
    const lines = await linesOf('항복강도')
    expect(lines).toHaveLength(2)
    expect(within(lines[0]).getByText(/인장시험 · MD/)).toBeInTheDocument()
    expect(within(lines[1]).getByText(/인장시험 · TD/)).toBeInTheDocument()
  })

  it('어디서 나온 값인지 적는다', async () => {
    // 시험종류와 방향이 없으면 「같은 항목의 두 값」 이 그냥 중복으로 보인다.
    show()
    const one = await card('항복강도')
    expect(one.getByText(/인장시험 · MD/)).toBeInTheDocument()
  })

  it('산포가 값 옆에 붙어 있다', async () => {
    // **285 만 보고 쓰는 사람이 생긴다.** 몇 번 재서 얼마나 흩어졌는지가 값의 절반이다.
    show()
    const one = await card('항복강도')
    expect(one.getAllByText(/±/).length).toBeGreaterThan(0)
    expect(one.getAllByText(/n=5/).length).toBeGreaterThan(0)
  })

  it('시험종류가 달라도 한 표에 모인다', async () => {
    // **시험종류마다 표를 만들면** 종류가 다섯일 때 표가 다섯 개 세로로 선다.
    forMaterial.mockResolvedValue({
      groups: [
        group('MD', 285),
        {
          ...group('NA', 0),
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA 스윕',
          scalars: [scalar('glass_transition', '유리전이온도', 358.15, 1.2)],
        },
      ],
    })
    show()
    const area = await summary()
    // **한 표에 둘 다 있다.** 시험종류마다 표를 만들면 종류 수만큼 세로로 선다.
    expect(area.getAllByLabelText('유리전이온도').length).toBeGreaterThan(0)
    expect(area.getAllByLabelText('항복강도').length).toBeGreaterThan(0)
  })

  it('적어 둔 값도 같은 표에 온다', async () => {
    // 카드는 「잰 값 > 적은 값」 으로 말없이 한쪽을 싣는다 — **그 둘이 어긋나는
    // 것을 볼 자리**가 어디에도 없었다.
    render(
      <PropertiesPanel
        materialId="m1"
        declared={
          [{ item: '탄성계수', input_unit: 'GPa', points: [{ value: 210 }] }] as never
        }
      />
    )
    const one = await card('탄성계수')
    // **배지가 출처를 말한다.** 「인장시험 · MD」 만으로는 그것이 잰 값인지 누가
    // 적은 값인지 자리로 안 드러났고, 그 둘은 카드에 실릴 때 우선순위가 다르다.
    expect(one.getByText('선언')).toBeInTheDocument()
    expect(one.getByText('210 GPa')).toBeInTheDocument()
  })

  it('두 값이 크게 어긋나면 짚는다', async () => {
    // 인장 206 GPa 와 DMA 198 GPa 는 정상이다. **두 배 차이는 둘 중 하나가
    // 틀린 것**이고, 그때 카드는 아무 말 없이 한쪽을 싣는다.
    forMaterial.mockResolvedValue({
      groups: [
        group('MD', 285, { scalars: [scalar('elastic_modulus', '탄성계수', 206e9, 3e9)] }),
      ],
    })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={
          [{ item: '탄성계수', input_unit: 'GPa', points: [{ value: 20 }] }] as never
        }
      />
    )
    expect(await screen.findByText(/값이 크게 다릅니다/)).toBeInTheDocument()
  })
})

describe('흔들리는 값', () => {
  it('요약에서 바로 보인다', async () => {
    // 전에는 8열 표의 맨 오른쪽에 있었다 — **가장 안 보이는 자리**였다.
    forMaterial.mockResolvedValue({
      groups: [
        group('MD', 285, {
          scalars: [scalar('yield_strength', '항복강도', 285e6, 40e6, 0.14)],
        }),
      ],
    })
    show()
    expect(await screen.findByLabelText(/CV 14\.0%/)).toBeInTheDocument()
  })
})

describe('접기', () => {
  it('조용한 묶음은 접혀서 시작한다', async () => {
    // 값은 위 요약이 답한다. 8열 표가 묶음마다 펼쳐져 있을 이유가 없다.
    show()
    await screen.findAllByText('항복강도')
    expect(
      screen.getByRole('button', { name: /인장시험 MD 펴기/ })
    ).toBeInTheDocument()
  })

  it('할 말이 있으면 펴 둔다', async () => {
    // **접어 두면 아무도 안 본다.** 조용히 빠진 시험을 알리려고 있는 화면이다.
    forMaterial.mockResolvedValue({
      groups: [group('MD', 285, { notes: ['시험 2건이 곡선을 못 냈습니다.'] })],
    })
    show()
    expect(await screen.findByText(/곡선을 못 냈습니다/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /인장시험 MD 접기/ })).toBeInTheDocument()
  })

  it('할 말이 있는 것을 접으면 그 사실이 머리에 남는다', async () => {
    // 할 말이 있으면 저절로 펴지므로, 접힌 채로 그 상태가 되는 것은 **사람이
    // 직접 접었을 때**다. 그때 아무 표시가 없으면 접은 순간 그 경고가 사라진다.
    const user = userEvent.setup()
    forMaterial.mockResolvedValue({
      groups: [group('MD', 285, { notes: ['시험 2건이 곡선을 못 냈습니다.'] })],
    })
    show()
    await screen.findByText(/곡선을 못 냈습니다/)
    await user.click(screen.getByRole('button', { name: /인장시험 MD 접기/ }))
    expect(screen.getByText('볼 것 있음')).toBeInTheDocument()
  })

  it('펴면 자세한 통계가 나온다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findAllByText('항복강도')
    await user.click(screen.getByRole('button', { name: /인장시험 MD 펴기/ }))
    await waitFor(() => expect(screen.getAllByText('중앙값').length).toBeGreaterThan(0))
  })
})

describe('시험종류 칩', () => {
  /**
   * **위 표가 값을 다 보이므로, 아래 상세는 지금 보려는 종류만 있으면 된다.**
   * 종류가 다섯이면 묶음 카드가 열 개 넘게 세로로 쌓이던 자리다.
   */
  const mixed = () =>
    forMaterial.mockResolvedValue({
      groups: [
        group('MD', 285),
        group('TD', 301),
        {
          ...group('NA', 0),
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA 스윕',
          scalars: [scalar('glass_transition', '유리전이온도', 358.15, 1.2)],
        },
      ],
    })

  it('종류가 하나면 칩을 안 만든다', async () => {
    // **없는 선택지를 보이면 그것도 소음이다.**
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    show()
    await summary()
    expect(screen.queryByRole('button', { name: '모든 시험종류 보기' })).not.toBeInTheDocument()
  })

  it('종류가 여럿이면 고를 수 있다', async () => {
    mixed()
    show()
    await summary()
    expect(screen.getByRole('button', { name: '모든 시험종류 보기' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'DMA 스윕 만 보기' })).toBeInTheDocument()
  })

  it('고르면 그 종류의 상세만 남는다', async () => {
    const user = userEvent.setup()
    mixed()
    show()
    await summary()
    // **붙기를 기다린 뒤 누른다.** 곧바로 집으면 전체 스위트에서만 깨진다.
    await user.click(await screen.findByRole('button', { name: 'DMA 스윕 만 보기' }))
    // 인장 묶음 카드가 사라진다 — **요약의 값은 그대로다.**
    expect(screen.queryByRole('button', { name: /인장시험 MD 펴기/ })).not.toBeInTheDocument()
    expect((await summary()).getAllByLabelText('항복강도').length).toBeGreaterThan(0)
  })

  it('전체로 돌아올 수 있다', async () => {
    const user = userEvent.setup()
    mixed()
    show()
    await summary()
    // **붙기를 기다린 뒤 누른다.** 곧바로 집으면 전체 스위트에서만 깨진다.
    await user.click(await screen.findByRole('button', { name: 'DMA 스윕 만 보기' }))
    await user.click(screen.getByRole('button', { name: '모든 시험종류 보기' }))
    expect(screen.getByRole('button', { name: /인장시험 MD 펴기/ })).toBeInTheDocument()
  })
})

describe('값 개수가 제각각일 때', () => {
  /**
   * **항목마다 값이 몇 개인지 다르다.** 탄성계수는 인장·DMA·문헌으로 셋인데
   * 연신율은 하나뿐이다.
   *
   * 격자로 두면 행 높이가 가장 긴 카드에 맞춰져 **짧은 카드 밑에 큰 빈칸**이
   * 남는다. 흐르는 배치(`columns`)는 그 자리를 다음 항목이 채운다.
   */
  const uneven = () =>
    forMaterial.mockResolvedValue({
      groups: [
        group('MD', 285, {
          // **연신율이 먼저 온다.** 값이 하나뿐인 것이 앞에 있는 데이터라야
          // 「값이 많은 것을 앞으로」 가 실제로 하는 일이 보인다.
          scalars: [
            scalar('elongation', '연신율', 0.32e6, 0.01e6),
            scalar('elastic_modulus', '탄성계수', 206e9, 3e9),
          ],
        }),
        group('TD', 301, {
          scalars: [scalar('elastic_modulus', '탄성계수', 198e9, 4e9)],
        }),
      ],
    })

  it('값이 하나인 항목도 제 카드를 갖는다', async () => {
    uneven()
    show()
    expect(await linesOf('연신율')).toHaveLength(1)
  })

  it('값이 여럿인 항목은 그 카드가 길어질 뿐이다', async () => {
    // 항목이 둘로 갈리면 「같은 물성의 두 값」 이 그냥 다른 항목으로 보인다.
    uneven()
    show()
    // 항목 이름은 첫 줄에만 보이지만 줄은 둘이다.
    expect(await linesOf('탄성계수', 2)).toHaveLength(2)
  })

})

describe('전체 여닫기', () => {
  /**
   * **묶음이 여럿이면 하나씩 누르는 것이 그 수만큼 반복된다.** 그리고 무엇을
   * 이미 폈는지도 흐려진다.
   */
  it('묶음이 하나뿐이면 안 만든다', async () => {
    // 없는 선택지도 소음이다 — 그 카드의 단추 하나로 끝난다.
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    show()
    // **줄이 붙은 뒤에 본다.** 표는 조회가 끝나기 전에도 떠서, 곧바로 「없다」 를
    // 보면 아직 안 온 것을 없는 것으로 읽는다.
    await linesOf('항복강도')
    expect(screen.queryByRole('button', { name: /전체 펼치기|전체 접기/ })).not.toBeInTheDocument()
  })

  it('한 번에 전부 펴진다', async () => {
    const user = userEvent.setup()
    show()
    // 여닫기 단추는 묶음이 둘 이상일 때만 선다 — 조회가 끝나야 생긴다.
    await user.click(await screen.findByRole('button', { name: /전체 펼치기/ }))
    expect(screen.getByRole('button', { name: /인장시험 MD 접기/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /인장시험 TD 접기/ })).toBeInTheDocument()
  })

  it('한 번에 전부 접힌다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /전체 펼치기/ }))
    await user.click(screen.getByRole('button', { name: /전체 접기/ }))
    expect(screen.getByRole('button', { name: /인장시험 MD 펴기/ })).toBeInTheDocument()
  })

  it('문구가 지금 상태를 말한다', async () => {
    // **「전체 여닫기」 처럼 두면 누르기 전에 어느 쪽이 될지 모른다.** 하나라도
    // 펴져 있으면 접는 쪽이 다음 할 일이다.
    const user = userEvent.setup()
    show()
    expect(await screen.findByRole('button', { name: /전체 펼치기/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /인장시험 MD 펴기/ }))
    expect(screen.getByRole('button', { name: /전체 접기/ })).toBeInTheDocument()
  })

  it('할 말이 있어 펴진 것도 함께 접힌다', async () => {
    // 자동으로 펴진 것과 사람이 편 것을 다르게 다루면, 「전체 접기」 를 눌렀는데
    // 뭔가 남아 있다.
    const user = userEvent.setup()
    forMaterial.mockResolvedValue({
      groups: [group('MD', 285, { notes: ['시험 2건이 곡선을 못 냈습니다.'] }), group('TD', 301)],
    })
    show()
    await user.click(await screen.findByRole('button', { name: /전체 접기/ }))
    expect(screen.getByRole('button', { name: /인장시험 MD 펴기/ })).toBeInTheDocument()
  })
})

describe('선언과 계산', () => {
  /**
   * **한 표가 둘을 다 든다** (2026-08-30).
   *
   * 전에는 「적어 둔 값」 카드가 왼쪽, 「잰 값」 요약이 오른쪽이었는데 요약 안에
   * 이미 적어 둔 값 줄이 있어 **같은 값이 두 번** 보였다. 이제 요약 하나가 둘을
   * 다 들고, 어느 쪽인지는 배지가 말한다.
   */
  const both = () => {
    forMaterial.mockResolvedValue({
      groups: [group('MD', 285, { scalars: [scalar('elastic_modulus', '탄성계수', 206e9, 3e9)] })],
    })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={
          [
            {
              item: '탄성계수',
              input_unit: 'GPa',
              points: [{ value: 210 }],
              source: 'literature',
              reference: 'ASM Handbook Vol.2',
            },
          ] as never
        }
        onEditDeclared={onEdit}
      />
    )
  }
  const onEdit = vi.fn()

  it('시편마다 잰 값에는 통계 배지가 붙는다', async () => {
    both()
    // 잰 값 줄은 조회가 끝난 뒤에 붙는다 — 두 줄이 다 설 때까지 기다린다.
    const [measured] = await linesOf('탄성계수', 2)
    expect(within(measured).getByText('통계')).toBeInTheDocument()
  })

  it('적은 값에는 선언 배지와 근거가 붙는다', async () => {
    both()
    const lines = await linesOf('탄성계수', 2)
    const stated = within(lines[1])
    expect(stated.getByText('선언')).toBeInTheDocument()
    // **근거가 그 자리에 있어야 한다** — 「선언」 만으로는 어느 핸드북인지 모른다.
    expect(stated.getByText(/ASM Handbook Vol.2/)).toBeInTheDocument()
  })

  it('적은 값만 고칠 수 있다', async () => {
    // 잰 값은 시험에서 나온 것이라 여기서 고칠 것이 아니다.
    both()
    await linesOf('탄성계수', 2)
    // 잰 값 줄에는 없고 적은 값 줄에만 하나.
    expect(screen.getAllByRole('button', { name: /적어 둔 값 편집/ })).toHaveLength(1)
  })

  it('편집을 누르면 그 항목으로 창을 연다', async () => {
    const user = userEvent.setup()
    both()
    // **줄을 기다린 뒤에 단추를 「찾는다」.** 줄만 기다리고 곧바로 집으면 전체
    // 스위트의 부하에서 가끔 빈 목록을 집었다(2026-08-30·31 두 번) — 줄이 붙는
    // 렌더와 단추가 붙는 렌더가 같지 않다. `findBy…` 는 붙을 때까지 다시 본다.
    //
    // 이름으로 거르는 role 질의(`findAllByRole`)로는 못 바꾼다 — 트리 전체의
    // 접근성 이름을 매번 계산해 5초 안에 안 끝났다.
    await linesOf('탄성계수')
    const button = await screen.findByLabelText('탄성계수 적어 둔 값 편집')
    await user.click(button)
    await waitFor(() => expect(onEdit).toHaveBeenCalledWith('탄성계수'))
  })

  it('창을 열 수 없는 자리에서는 편집 단추를 안 만든다', async () => {
    // 시료 화면처럼 그 창을 들 수 없는 자리도 있다.
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={[{ item: '밀도', input_unit: 'g/cm^3', points: [{ value: 7.85 }] }] as never}
      />
    )
    await card('밀도')
    expect(screen.queryByRole('button', { name: /적어 둔 값 편집/ })).not.toBeInTheDocument()
  })

  it('잰 값이 하나도 없어도 적은 값은 보인다', async () => {
    // **시험을 안 한 재료가 대부분이다.** 요약이 안 뜨면 그 재료는 물성 탭이 빈다.
    forMaterial.mockResolvedValue({ groups: [] })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={[{ item: '밀도', input_unit: 'g/cm^3', points: [{ value: 7.85 }] }] as never}
      />
    )
    expect((await card('밀도')).getByText('선언')).toBeInTheDocument()
  })
})

describe('글로벌 피팅 결과', () => {
  /**
   * **통합 적합 결과도 물성이다** (2026-08-30).
   *
   * 통계는 시편 n개를 **세어 본 것**이고, 통합 적합은 시편 여럿의 데이터로
   * **한 번에 하나를 구한 것**이다(마스터커브 다섯 → Prony 계수 한 벌). 그
   * 결과물이 곧 물성인데 옆 패널에만 두면 **「이 재료의 물성」 목록에서 빠진다** —
   * 카드에는 실리는데 목록에는 없다.
   */
  const KINDS = [
    {
      id: 'viscoelastic.prony_group',
      label: 'Prony 글로벌 피팅',
      applies_to: ['dma_temperature_sweep'],
      params: [],
      makes_values: [
        { key: 'equilibrium_pa', label: '평형 탄성률', si_unit: 'Pa', help: null },
        { key: 'term_count', label: '항 수', si_unit: '1', help: null },
      ],
    },
  ]
  const RESULT = {
    id: 'g1',
    plugin_id: 'viscoelastic.prony_group',
    used: ['r1', 'r2', 'r3'],
    values: { equilibrium_pa: 5.0e6, term_count: 3 },
    warnings: [],
  }

  const withGroups = () =>
    render(
      <PropertiesPanel
        materialId="m1"
        groupResults={[RESULT] as never}
        groupKinds={KINDS as never}
      />
    )

  it('물성 표에 함께 선다', async () => {
    withGroups()
    const one = await card('평형 탄성률')
    expect(one.getByText('피팅')).toBeInTheDocument()
  })

  it('값 이름을 방법이 준다', async () => {
    // **화면이 `equilibrium_pa` 를 몰라야 한다** — `makes_values` 가 이름과 단위를
    // 준다. 화면이 적어 두면 새 물성을 붙일 때 화면도 고쳐야 한다.
    withGroups()
    const area = await summary()
    expect(area.getAllByLabelText('평형 탄성률').length).toBeGreaterThan(0)
    expect(area.getAllByLabelText('항 수').length).toBeGreaterThan(0)
  })

  it('몇 건을 묶었는지 적는다', async () => {
    // **「셋을 묶었다」 가 근거의 절반이다.** 몇 건인지 없으면 그 계수가 한 시편의
    // 것인지 다섯의 것인지 모른다.
    withGroups()
    const one = await card('평형 탄성률')
    expect(one.getByText(/시험 3건/)).toBeInTheDocument()
  })

  it('묶음만 있어도 표가 뜬다', async () => {
    // 시험 통계가 없는 재료도 있다 — 요약이 안 뜨면 그 물성이 어디에도 안 보인다.
    forMaterial.mockResolvedValue({ groups: [] })
    withGroups()
    expect(await screen.findByLabelText('물성 요약')).toBeInTheDocument()
  })
})

describe('글로벌 피팅 자리', () => {
  /**
   * **아코디언 안이 아니라 물성 머리다** (2026-08-30).
   *
   * 묶음의 단위는 시험종류이고 방향은 안 본다 — 「인장시험 MD」 카드 안에 두면
   * MD 만 묶는 것처럼 보이고, **접혀 있으면 아예 안 보인다.** 결과도 물성 표에
   * 서므로 더하는 자리가 그 머리에 있는 것이 맞다(선언 물성 추가와 같은 성격이다).
   */
  it('물성 상자 머리에 온다', async () => {
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    render(<PropertiesPanel materialId="m1" groupSlot={<button>글로벌 피팅</button>} />)
    const box = await screen.findByLabelText('물성')
    const button = within(box).getByRole('button', { name: '글로벌 피팅' })
    // 표 안이 아니라 그 상자 머리에 — 카드를 펴지 않아도 보인다.
    expect(button.closest('[aria-label="물성 요약"]')).toBeNull()
  })

  it('선언 물성 추가 오른쪽에 온다', async () => {
    // **차례가 일의 차례다.** 적어 두는 것이 먼저이고(시험 없이도 할 수 있다),
    // 통합 적합은 시험이 여럿 쌓인 뒤의 일이다.
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    render(
      <PropertiesPanel
        materialId="m1"
        header={<button>선언 물성 추가</button>}
        groupSlot={<button>글로벌 피팅</button>}
      />
    )
    const box = await screen.findByLabelText('물성')
    const text = box.textContent ?? ''
    expect(text.indexOf('선언 물성 추가')).toBeLessThan(text.indexOf('글로벌 피팅'))
  })

  it('한 줄에 나란히 선다', async () => {
    // **`ml-auto` 만 주면 그 안이 block 이라 단추가 위아래로 쌓인다**
    // (2026-08-30). 머리 줄이 두 줄이 되면 그만큼 표가 아래로 밀린다.
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    render(
      <PropertiesPanel
        materialId="m1"
        header={<button>선언 물성 추가</button>}
        groupSlot={<button>글로벌 피팅</button>}
      />
    )
    await screen.findByLabelText('물성')
    const one = screen.getByRole('button', { name: '선언 물성 추가' })
    const two = screen.getByRole('button', { name: '글로벌 피팅' })
    // 같은 부모 안에서 가로로 늘어서야 한다.
    expect(one.parentElement).toBe(two.parentElement)
    expect(one.parentElement?.className).toContain('flex')
  })

  it('접힌 상세와 무관하게 보인다', async () => {
    forMaterial.mockResolvedValue({ groups: [group('MD', 285)] })
    render(<PropertiesPanel materialId="m1" groupSlot={<button>글로벌 피팅</button>} />)
    await screen.findByLabelText('물성 요약')
    // 카드는 접혀 있다. **붙기를 기다린다** — 부하에서 요약보다 늦게 온다.
    expect(await screen.findByRole('button', { name: /인장시험 MD 펴기/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '글로벌 피팅' })).toBeInTheDocument()
  })

  it('안 주면 아무것도 안 그린다', async () => {
    // 쓸 방법이 없는 재료에서 「묶기」 가 뜨면 그것이 무엇인지 매번 묻게 된다.
    show()
    await summary()
    expect(screen.queryByRole('button', { name: '글로벌 피팅' })).not.toBeInTheDocument()
  })
})

describe('시험이 없을 때', () => {
  /**
   * **없는 것은 시험이지 물성이 아니다.**
   *
   * 「아직 시험이 없습니다」 가 왼쪽(물성)에 있으면 「물성이 없다」 로 읽힌다 —
   * 그런데 적어 둔 값만 있는 재료도 물성은 있고, 그 재료가 대부분이다.
   */
  it('안내가 근거 쪽에 뜬다', async () => {
    forMaterial.mockResolvedValue({ groups: [] })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={[{ item: '밀도', input_unit: 'g/cm^3', points: [{ value: 7.85 }] }] as never}
      />
    )
    const notice = await screen.findByText(/아직 시험이 없습니다/)
    const table = await screen.findByLabelText('물성 요약')
    // 같은 열에 있으면 물성 위에 뜬다 — 나눈 뜻이 없다.
    expect(notice.closest('.min-h-0')).not.toBe(table.closest('.min-h-0'))
  })

  it('적어 둔 값은 그대로 보인다', async () => {
    forMaterial.mockResolvedValue({ groups: [] })
    render(
      <PropertiesPanel
        materialId="m1"
        declared={[{ item: '밀도', input_unit: 'g/cm^3', points: [{ value: 7.85 }] }] as never}
      />
    )
    expect((await card('밀도')).getByText('선언')).toBeInTheDocument()
  })
})
