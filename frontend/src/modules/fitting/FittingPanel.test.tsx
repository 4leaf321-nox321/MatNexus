/**
 * 적합 화면 — **보여 준 것을 저장할 수 있어야 한다.**
 *
 * 이 파일이 지키는 것은 둘이다.
 *
 *   늘리기 칸은 늘릴 수 있는 식에서만 열린다
 *   축 이름은 식이 정한다 — 화면이 하드코딩하지 않는다
 *   확정한 값을 못 쓰게 만드는 일은 **한 번 묻고**, 되살릴 길을 둔다
 *
 * 왜 시험으로 두는가. 초탄성은 저장이 422 로 거절한다(소성 표를 만드는 식이
 * 아니다). 그런데 화면이 칸을 열어 두면 사람은 숫자를 넣고 곡선을 보고 정한 뒤
 * **저장 버튼에서 거절당한다.** 이 저장소가 반복해서 데인 자리다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FittingPanel } from '@/modules/fitting/FittingPanel'

const preview = vi.fn()
const cards = vi.fn()
const declaredPreview = vi.fn()
const forMaterial = vi.fn()
const deprecate = vi.fn()
const restore = vi.fn()
const create = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    preview: (...args: unknown[]) => preview(...args),
    cards: (...args: unknown[]) => cards(...args),
    // 카드 대화상자가 물려받을 밀도·푸아송비를 묻는다.
    inherited: () => Promise.resolve([]),
    deprecate: (...args: unknown[]) => deprecate(...args),
    restore: (...args: unknown[]) => restore(...args),
    // 카드 줄에는 내보내기 메뉴가 딸려 있다 — 그 안이 단위계를 읽는다.
    unitSystems: () => Promise.resolve([{ key: 'si', label: 'SI', is_default: true }]),
    create: (...args: unknown[]) => create(...args),
    // 방법 목록은 서버가 준다 — 차례가 곧 추천 순서다.
    resampleMethods: () =>
      Promise.resolve([
        { key: 'curvature', label: '꺾이는 곳에 촘촘히', help: '무릎에 점을 몰아 줍니다.' },
        { key: 'uniform', label: '등간격', help: '같은 폭으로 나눕니다.' },
      ]),
    // 카드 목록이 비어 있어도 화면은 형식·블록 선언을 먼저 읽는다.
    formats: () => Promise.resolve([]),
    blocks: () => Promise.resolve([]),
    // 선형탄성구간 대화상자가 「함께 실리는 것」 을 보여 주려고 읽는다.
    declaredPreview: (...args: unknown[]) => declaredPreview(...args),
  },
}))

// CAE 카드 탭이 글로벌 피팅 패널을 품는다 — 그 패널이 읽는 것들.
const groupKinds = vi.fn()
vi.mock('@/modules/materials/api.groups', () => ({
  groupsApi: {
    kinds: (...args: unknown[]) => groupKinds(...args),
    ofMaterial: () => Promise.resolve([]),
    create: () => Promise.resolve({}),
  },
}))
const PRONY_WAY = {
  id: 'viscoelastic.prony_group',
  label: 'Prony 글로벌 피팅',
  applies_to: ['dma_sweep'],
  params: [],
  makes_values: [],
  needs: 'master_curve',
}
vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { runs: () => Promise.resolve({ items: [], total: 0 }) },
}))

vi.mock('@/modules/statistics/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/statistics/api')>()),
  statisticsApi: { forMaterial: (...args: unknown[]) => forMaterial(...args) },
}))

function fit(overrides: Record<string, unknown> = {}) {
  return {
    family: 'voce',
    label: 'Voce',
    block: 'hardening',
    parameters: [
      { name: 'sigma_0', value: 250e6, si_unit: 'Pa', lower: 0, upper: 1e9, initial: 3e8 },
    ],
    rmse: 1e6,
    relative_rmse: 0.004,
    r_squared: 0.999,
    max_residual: 2e6,
    point_count: 40,
    strain_min: 0.001,
    strain_max: 0.2,
    notes: [],
    curve: [
      [0.001, 2.5e8],
      [0.2, 4.4e8],
    ] as [number, number][],
    extrapolated_to: null,
    x_label: '진소성변형률',
    y_label: '진응력',
    ...overrides,
  }
}

function body(fits: ReturnType<typeof fit>[]) {
  return {
    test_type_key: 'tensile',
    test_type_label: '인장',
    orientation: 'MD',
    sample_count: 3,
    source_points: [
      [0.001, 2.5e8],
      [0.2, 4.4e8],
    ] as [number, number][],
    si_unit: 'Pa',
    notes: [],
    elastic: [],
    fits,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  cards.mockResolvedValue([])
  groupKinds.mockResolvedValue([PRONY_WAY])
  declaredPreview.mockResolvedValue({ material_name: 'X', blocks: [], values: [] })
  forMaterial.mockResolvedValue({
    material_id: 'm1',
    material_name: 'DP600',
    groups: [
      {
        test_type_key: 'tensile',
        test_type_label: '인장',
        orientation: 'MD',
        sample_count: 3,
        // **실제 응답과 같은 칸을 둔다.** 빠뜨리면 화면이 그 칸을 읽다 죽는
        // 것을 시험이 못 잡는다 — 실제로 그렇게 놓쳤다.
        test_run_ids: ['r-1', 'r-2', 'r-3'],
        record_names: ['SECC__01__MD_01__TEN_01', 'SECC__02', 'SECC__03'],
        scalars: [],
        curve: null,
        notes: [],
        skipped_unadopted: 0,
      },
    ],
  })
})

function panel() {
  return render(
    <MemoryRouter>
      <FittingPanel materialId="m1" />
    </MemoryRouter>
  )
}

/** 「경화식 카드」 로 모달을 열고 「경화식 맞춰 보기」를 눌러 미리보기를 받는다. **자동으로 안 돈다.** */
async function compare() {
  await userEvent.click(await screen.findByRole('button', { name: /^탄소성 카드$/ }))
  await userEvent.click(await screen.findByRole('button', { name: /경화식 맞춰 보기/ }))
  await waitFor(() => expect(preview).toHaveBeenCalled())
}

/** 카드 한 장이 있는 화면. 상태를 바꿔 가며 단추를 본다. */
function withCard(status: string) {
  // **실제 응답과 같은 모양이어야 한다.** 칸이 빠지면 화면이 그것을 읽다 죽는데,
  // 그 죽음은 빈 화면으로만 보여서 원인을 못 찾는다 — 실제로 여기서 겪었다.
  cards.mockResolvedValue({
    total: 1,
    limit: 50,
    offset: 0,
    items: [
      {
        id: 'c1',
        material_id: 'm1',
        material_name: 'SECC_MDOI_1.0',
        test_type_key: 'tensile',
        orientation: 'MD',
        label: '인장 MD',
        status,
        source: { sample_count: 3 },
        blocks: {},
        available_formats: ['abaqus'],
        problem: null,
        point_count: 120,
        note: null,
        owner_workspace_name: '재료연구팀',
        is_global: false,
        published_at: status === 'published' ? '2026-09-01T00:00:00Z' : null,
        created_at: '2026-08-25T00:00:00Z',
      },
    ],
  })
}

describe('점 수 맞추기', () => {
  const openSave = async () => {
    // 비교 화면은 **후보가 있어야** 뜬다 — 그 안에 저장 단추가 있다.
    preview.mockResolvedValue(body([fit()]))
    panel()
    await compare()
    await userEvent.click(await screen.findByRole('button', { name: /이 값으로 카드 만들기/ }))
  }

  it('안 켜면 안 건다 — 측정 그대로 나간다', async () => {
    // **서버가 기본값을 두면 그 값이 곧 결정이 된다.** 아무도 그것을 결정이라고
    // 인식하지 않는다.
    create.mockResolvedValue({})
    await openSave()
    await userEvent.click(await screen.findByRole('button', { name: '초안으로 저장' }))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({
      resample_method: null,
      resample_points: null,
    })
  })

  it('켜면 방법과 점 수를 함께 보낸다', async () => {
    create.mockResolvedValue({})
    await openSave()
    await userEvent.click(await screen.findByLabelText('소성 표의 점 수 맞추기'))
    await userEvent.selectOptions(screen.getByLabelText('어떻게 고를까'), 'uniform')
    const points = screen.getByLabelText('점 수')
    await userEvent.clear(points)
    await userEvent.type(points, '25')
    await userEvent.click(screen.getByRole('button', { name: '초안으로 저장' }))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({
      resample_method: 'uniform',
      resample_points: 25,
    })
  })

  it('무엇을 하는 방법인지 서버가 적은 설명을 보여 준다', async () => {
    // 화면이 베껴 두면 새 방법이 붙을 때 설명만 옛것으로 남는다.
    await openSave()
    await userEvent.click(await screen.findByLabelText('소성 표의 점 수 맞추기'))
    expect(screen.getByText('무릎에 점을 몰아 줍니다.')).toBeInTheDocument()
  })
})

describe('확정한 값을 못 쓰게 만들 때', () => {
  it('한 번 묻고, 확인해야 중지한다', async () => {
    // **되돌려도 초안으로만 온다** — 확정을 다시 받아야 하므로 가벼운 누름이 아니다.
    withCard('published')
    deprecate.mockResolvedValue({})
    panel()
    await userEvent.click(await screen.findByRole('button', { name: '사용 중지' }))
    expect(deprecate).not.toHaveBeenCalled()

    await userEvent.click(await screen.findByRole('button', { name: '사용 중지', hidden: false }))
    await waitFor(() => expect(deprecate).toHaveBeenCalledWith('c1'))
  })

  it('사용 중지한 카드는 초안으로 되살린다', async () => {
    // 되살릴 길이 없으면 남는 방법은 같은 값으로 새 카드를 만드는 것뿐이고,
    // 그러면 만든 사람·만든 때가 실제와 달라진다.
    withCard('deprecated')
    restore.mockResolvedValue({})
    panel()
    await userEvent.click(await screen.findByRole('button', { name: '초안으로 되살리기' }))
    await waitFor(() => expect(restore).toHaveBeenCalledWith('c1'))
  })
})

describe('늘리기 칸', () => {
  it('금속 경화식에서는 열린다', async () => {
    preview.mockResolvedValue(body([fit()]))
    panel()
    await compare()
    const input = await screen.findByLabelText(/시험 구간 밖까지 늘리기/)
    expect(input).toBeEnabled()
    expect(screen.getByText(/시험 구간 밖까지 늘리기 \(진소성변형률\)/)).toBeInTheDocument()
  })

  it('초탄성에서는 잠기고 이유를 말한다', async () => {
    // **서버가 422 로 거절하는 것을 화면이 미리 막는다.**
    preview.mockResolvedValue(
      body([
        fit({
          family: 'ogden_1',
          label: 'Ogden (1항)',
          block: 'hyperelastic',
          x_label: '공칭 변형률',
          y_label: '공칭 응력',
        }),
      ])
    )
    panel()
    await compare()
    const input = await screen.findByLabelText(/시험 구간 밖까지 늘리기/)
    expect(input).toBeDisabled()
    expect(screen.getByText(/소성 표를 만드는 식이 아닙니다/)).toBeInTheDocument()
  })

  it('축 이름을 식에서 가져온다', async () => {
    // **고무는 공칭 변형률이다.** "진소성변형률" 이라고 붙으면 거짓말이다.
    preview.mockResolvedValue(
      body([
        fit({
          family: 'ogden_1',
          label: 'Ogden (1항)',
          block: 'hyperelastic',
          x_label: '공칭 변형률',
          y_label: '공칭 응력',
        }),
      ])
    )
    panel()
    await compare()
    expect(await screen.findByText(/시험 구간 밖까지 늘리기 \(공칭 변형률\)/)).toBeInTheDocument()
    expect(screen.queryByText(/시험 구간 밖까지 늘리기 \(진소성변형률\)/)).not.toBeInTheDocument()
  })

  it('식을 안 고르면 잠기고 그 이유를 말한다', async () => {
    // 표만 저장하면 측정한 점이 그대로 실리고, 그 밖을 채울 근거가 없다.
    preview.mockResolvedValue(body([fit()]))
    panel()
    await compare()
    await userEvent.click(await screen.findByRole('button', { name: /식 없이 표만/ }))
    expect(await screen.findByLabelText(/시험 구간 밖까지 늘리기/)).toBeDisabled()
    expect(screen.getByText(/식을 골라야 늘릴 수 있습니다/)).toBeInTheDocument()
  })
})

describe('섞기', () => {
  /**
   * 주식 Voce + 상대 Swift. **혼합은 후보가 아니라 상태다** — 서버가 `voce+swift`
   * 키로 돌려주는 곡선을 후보처럼 눌렀더니 그것이 주식이 되어 서버가 혼합을 빼고
   * 답했고, 그래프와 선택이 함께 사라졌다(2026-09-11 VOC).
   */
  const voce = fit()
  const swift = fit({ family: 'swift', label: 'Swift', relative_rmse: 0.006 })
  const mixed = fit({
    family: 'voce+swift',
    label: 'Voce 0.50 + Swift 0.50',
    relative_rmse: 0.005,
    curve: [
      [0.001, 2.6e8],
      [0.2, 4.5e8],
    ] as [number, number][],
  })

  beforeEach(() => {
    // 주식·상대·비중이 함께 오면 혼합이 하나 더 붙는다 — 서버와 같은 규칙.
    preview.mockImplementation((body: { blend_primary?: string; blend_with?: string }) =>
      Promise.resolve(
        body.blend_primary && body.blend_with
          ? { ...bodyOf([voce, swift]), fits: [voce, swift, mixed] }
          : bodyOf([voce, swift])
      )
    )
  })

  function bodyOf(fits: ReturnType<typeof fit>[]) {
    return body(fits)
  }

  it('후보의 「섞기」 로 상대를 고르면 혼합 줄이 서고, 그래프에는 혼합 곡선이 오른다', async () => {
    panel()
    await compare()
    await userEvent.click(await screen.findByRole('button', { name: 'Swift 섞기' }))

    await waitFor(() =>
      expect(preview).toHaveBeenLastCalledWith(
        expect.objectContaining({ blend_primary: 'voce', blend_with: 'swift', blend_weight: 0.5 })
      )
    )
    const row = await screen.findByRole('group', { name: '혼합' })
    expect(within(row).getByText(/Voce/)).toBeInTheDocument()
    expect(within(row).getByLabelText('섞는 비중')).toBeInTheDocument()
    // 혼합은 후보 격자에 박스로 서지 않는다.
    expect(screen.queryByRole('button', { name: /Voce 0\.50 \+ Swift/ })).toBeNull()
    expect(await screen.findByText('Voce 0.50 + Swift 0.50 적합')).toBeInTheDocument()
  })

  it('혼합 줄을 눌러도 아무것도 사라지지 않는다', async () => {
    panel()
    await compare()
    await userEvent.click(await screen.findByRole('button', { name: 'Swift 섞기' }))
    const row = await screen.findByRole('group', { name: '혼합' })
    // 서버 답이 와서 혼합 곡선까지 오른 뒤에 센다 — 그 전에 세면 늦게 온 답을 「다시 물었다」 로 읽는다.
    await screen.findByText('Voce 0.50 + Swift 0.50 적합')
    const calls = preview.mock.calls.length

    await userEvent.click(row)
    await userEvent.click(within(row).getByText(/Voce/))

    expect(screen.getByRole('group', { name: '혼합' })).toBeInTheDocument()
    expect(screen.getByText('Voce 0.50 + Swift 0.50 적합')).toBeInTheDocument()
    // 다시 묻지도 않는다 — 누른 것이 선택이 아니기 때문이다.
    expect(preview.mock.calls.length).toBe(calls)
  })

  it('상대를 주식으로 고르면 섞기가 풀린다', async () => {
    // 같은 식을 주식이자 상대로 두면 서버는 혼합을 못 만든다.
    panel()
    await compare()
    await userEvent.click(await screen.findByRole('button', { name: 'Swift 섞기' }))
    await screen.findByRole('group', { name: '혼합' })

    // 후보 박스 본체(이름 뒤에 지표가 이어진다) — 「Swift 섞기 해제」 단추와 가른다.
    const swiftBox = screen
      .getAllByRole('button', { name: /^Swift/ })
      .find((one) => !one.getAttribute('aria-label'))
    expect(swiftBox).toBeDefined()
    await userEvent.click(swiftBox!)

    await waitFor(() => expect(screen.queryByRole('group', { name: '혼합' })).toBeNull())
    await waitFor(() =>
      expect(preview).toHaveBeenLastCalledWith(
        expect.objectContaining({ blend_primary: null, blend_with: null })
      )
    )
  })
})

describe('시험 종류에 맞는 길만 연다', () => {
  /**
   * DMA 묶음에 「경화식 맞춰 보기」 가 떠서 누르면 422 였다(2026-09-05 실사용). 어느
   * 길이 열리는지는 서버가 말한다 — `fittable`(진소성변형률·진응력 열이 있는가)과
   * 선형 한계 변형률 스칼라(LVE 길)로.
   */
  const dma = (scalars: unknown[] = []) => ({
    test_type_key: 'dma_sweep',
    test_type_label: 'DMA 스윕',
    orientation: 'NA',
    sample_count: 2,
    fittable: false,
    test_run_ids: ['r-1', 'r-2'],
    record_names: ['A', 'B'],
    scalars,
    curve: null,
    notes: [],
    skipped_unadopted: 0,
  })
  const lveScalar = (key: string, label: string, mean: number, unit: string) => ({
    key,
    label,
    count: 2,
    mean,
    median: mean,
    sample_sd: 0,
    coefficient_of_variation: 0,
    ci95_low: null,
    ci95_high: null,
    iqr: null,
    mad: null,
    minimum: mean,
    maximum: mean,
    outliers: [],
    si_unit: unit,
    dimension: unit === 'Pa' ? 'stress' : 'strain',
  })

  it('DMA 만 있으면 경화식 단계가 아예 없다', async () => {
    forMaterial.mockResolvedValue({ material_id: 'm1', material_name: 'X', groups: [dma()] })
    panel()
    await screen.findByText(/새 카드 만들기/)
    expect(screen.queryByRole('button', { name: /^탄소성 카드$/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /경화식 맞춰 보기/ })).not.toBeInTheDocument()
    expect(screen.queryByText('무엇으로')).not.toBeInTheDocument()
    // 대신 점탄성 카드(글로벌 피팅) 단추가 선다 — DMA 에 붙는 방법이라서.
    expect(await screen.findByRole('button', { name: /^점탄성 카드$/ })).toBeInTheDocument()
  })

  it('선형 한계 변형률을 낸 DMA 묶음에는 LVE 길이 열린다', async () => {
    forMaterial.mockResolvedValue({
      material_id: 'm1',
      material_name: 'X',
      groups: [
        dma([
          lveScalar('youngs_modulus', '저장 탄성률 (선형 구간)', 1.19e9, 'Pa'),
          lveScalar('lve_strain_limit', '선형 한계 변형률', 1.65e-4, '1'),
        ]),
      ],
    })
    panel()
    const lve = await screen.findByRole('button', { name: /선형탄성구간\(LVE\) 카드/ })
    // **재료 기본 정보 카드가 맨 앞이다.** 시험이 없어도 열리는 길이라 먼저 선다.
    const buttons = screen.getAllByRole('button').map((one) => one.textContent ?? '')
    expect(buttons.findIndex((text) => text.includes('재료 기본 정보 카드'))).toBeLessThan(
      buttons.findIndex((text) => text.includes('선형탄성구간(LVE) 카드'))
    )
    await userEvent.click(lve)
    expect(await screen.findByRole('dialog')).toHaveTextContent('선형탄성구간(LVE) 카드 만들기')
    // 재료에 적어 둔 열물성을 함께 실을지 고른다 — 기본은 켜짐. 없으면 없다고 말한다.
    expect(screen.getByRole('checkbox', { name: '재료 기본 정보 함께 싣기' })).toBeChecked()
    expect(await screen.findByText(/함께 실릴 것이 없습니다/)).toBeInTheDocument()
  })

  it('재료에 적어 둔 열물성이 있으면 함께 실리는 값을 이름과 함께 적는다', async () => {
    forMaterial.mockResolvedValue({
      material_id: 'm1',
      material_name: 'X',
      groups: [
        dma([
          lveScalar('youngs_modulus', '저장 탄성률 (선형 구간)', 1.19e9, 'Pa'),
          lveScalar('lve_strain_limit', '선형 한계 변형률', 1.65e-4, '1'),
        ]),
      ],
    })
    declaredPreview.mockResolvedValue({
      material_name: 'X',
      blocks: ['thermal'],
      values: [
        { key: 'thermal_conductivity', label: '열전도율', value: 50, source: 'declared:literature', detail: '' },
        { key: 'specific_heat', label: '비열', value: 470, source: 'declared:literature', detail: '' },
        { key: 'youngs_modulus', label: '탄성계수', value: 2e11, source: 'declared:literature', detail: '' },
      ],
    })
    const { fittingApi } = await import('@/modules/fitting/api')
    ;(fittingApi as unknown as { blocks: () => Promise<unknown[]> }).blocks = () =>
      Promise.resolve([
        {
          key: 'thermal',
          label: '열물성',
          help: '',
          order: 15,
          produces: [
            { key: 'thermal_conductivity', label: '열전도율', si_unit: 'W/(m.K)', help: null },
            { key: 'specific_heat', label: '비열', si_unit: 'J/(kg.K)', help: null },
          ],
          rows: [],
        },
      ])
    panel()
    await userEvent.click(await screen.findByRole('button', { name: /선형탄성구간\(LVE\) 카드/ }))
    const said = (await screen.findByText('함께 실리는 것')).parentElement as HTMLElement
    // 값마다 표 하나 — 한 줄 글이 아니다.
    expect(said).toHaveTextContent('열전도율50 W/(m.K)')
    expect(said).toHaveTextContent('비열470 J/(kg.K)')
    // 탄성계수는 열물성 블록이 아니다 — 잰 E′ 를 덮지 않는다.
    expect(said).not.toHaveTextContent('탄성계수')
  })

  it('점탄성 카드 단추가 글로벌 피팅 모달을 연다 — 탭 본문은 단추 줄과 카드 목록뿐이다', async () => {
    forMaterial.mockResolvedValue({ material_id: 'm1', material_name: 'X', groups: [dma()] })
    panel()
    // 본문에는 절이 없다.
    expect(screen.queryByRole('heading', { name: '글로벌 피팅' })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: /^점탄성 카드$/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('점탄성 카드')
    expect(within(dialog).getByRole('heading', { name: '글로벌 피팅' })).toBeInTheDocument()
  })

  it('그 방법이 붙는 시험종류가 없으면 단추가 없다', async () => {
    // 인장만 있는 재료에 Prony(DMA) 단추가 서면 눌러 봐야 「쓸 시험이 없다」 다.
    panel()
    await screen.findByRole('button', { name: /^탄소성 카드$/ })
    expect(screen.queryByRole('button', { name: /^점탄성 카드$/ })).not.toBeInTheDocument()
  })

  it('「정보」 가 다섯 카드의 입력과 결과를 표로 보인다', async () => {
    panel()
    await userEvent.click(await screen.findByRole('button', { name: '카드 종류 설명' }))
    const dialog = await screen.findByRole('dialog')
    for (const name of ['재료 기본 정보 카드', '탄소성 카드', '선형탄성구간(LVE) 카드', '점탄성 카드', '속도 의존 카드']) {
      expect(within(dialog).getByText(name)).toBeInTheDocument()
    }
    expect(dialog).toHaveTextContent('*ELASTIC + *PLASTIC')
  })

  it('인장이면 경화식 길이 열린다 — 옛 응답(fittable 없음)도 된다', async () => {
    panel()
    // **탭 본문에는 단추만 있다.** 1~3단계는 모달 안이다(2026-09-05).
    expect(await screen.findByRole('button', { name: /^탄소성 카드$/ })).toBeInTheDocument()
    expect(screen.queryByText('무엇으로')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^탄소성 카드$/ }))
    expect(await screen.findByText('무엇으로')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /경화식 맞춰 보기/ })).toBeInTheDocument()
  })
})

describe('카드 목록은 접혀 있다', () => {
  it('요약 칩만 보이고, 펴면 블록 전부가 보인다', async () => {
    withCard('draft')
    cards.mockResolvedValue({
      total: 1,
      limit: 50,
      offset: 0,
      items: [
        {
          id: 'c1',
          material_id: 'm1',
          material_name: 'X',
          test_type_key: 'dma_sweep',
          orientation: 'NA',
          label: 'LVE 하나',
          status: 'draft',
          source: { sample_count: 2 },
          blocks: {
            elastic: { values: { youngs_modulus: 1.19e9, poisson_ratio: 0.49 } },
            lve: { values: { youngs_modulus: 1.19e9, lve_strain_limit: 1.65e-4, sample_count: 2 } },
          },
          available_formats: ['abaqus_lve'],
          problem: null,
          point_count: 0,
          note: null,
          owner_workspace_name: null,
          is_global: false,
          published_at: null,
          created_at: '2026-09-05T00:00:00Z',
        },
      ],
    })
    const { fittingApi } = await import('@/modules/fitting/api')
    ;(fittingApi as unknown as { blocks: () => Promise<unknown[]> }).blocks = () =>
      Promise.resolve([
        {
          key: 'elastic',
          label: '탄성',
          help: '',
          order: 10,
          produces: [
            { key: 'youngs_modulus', label: '탄성계수', si_unit: 'Pa', help: null },
            { key: 'poisson_ratio', label: '푸아송비', si_unit: '1', help: null },
          ],
          rows: [],
        },
        {
          key: 'lve',
          label: '선형탄성구간(LVE) 탄성률',
          help: '',
          order: 45,
          produces: [
            { key: 'youngs_modulus', label: '저장 탄성률 (선형 구간)', si_unit: 'Pa', help: null },
            { key: 'lve_strain_limit', label: '선형 한계 변형률', si_unit: '1', help: null },
          ],
          rows: [],
        },
      ])
    panel()
    // 접힌 상태: 블록 이름과 첫 값만.
    expect(await screen.findByText('탄성')).toBeInTheDocument()
    expect(screen.queryByText('푸아송비')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'LVE 하나 펴기' }))
    expect(await screen.findByText('푸아송비')).toBeInTheDocument()
    expect(screen.getByText('선형 한계 변형률')).toBeInTheDocument()
  })

  it('종류 칩으로 가른다 — 칩은 실제로 든 종류만 선다', async () => {
    // 탄소성·선형탄성구간·재료 기본 정보가 한 목록에 섞이면 이름만으로는 안 보인다.
    const base = {
      material_id: 'm1',
      material_name: 'X',
      status: 'draft',
      source: { sample_count: 2 },
      available_formats: [],
      problem: null,
      point_count: 0,
      note: null,
      owner_workspace_name: null,
      is_global: false,
      published_at: null,
      created_at: '2026-09-05T00:00:00Z',
    }
    cards.mockResolvedValue({
      total: 3,
      limit: 50,
      offset: 0,
      items: [
        { ...base, id: 'c1', test_type_key: 'dma_sweep', orientation: 'NA', label: 'LVE 하나',
          blocks: { elastic: { values: {} }, lve: { values: {} } } },
        { ...base, id: 'c2', test_type_key: 'tensile', orientation: 'MD', label: 'Voce 카드',
          blocks: { elastic: { values: {} }, hardening: { values: {} }, table: { values: {} } } },
        { ...base, id: 'c3', test_type_key: null, orientation: null, label: '문헌 카드',
          blocks: { elastic: { values: {} } } },
      ],
    })
    const { fittingApi } = await import('@/modules/fitting/api')
    ;(fittingApi as unknown as { blocks: () => Promise<unknown[]> }).blocks = () =>
      Promise.resolve([
        // 종류는 선언의 kind_priority 로 정한다 — 탄성·소성 표는 종류가 아니다(null).
        { key: 'elastic', label: '탄성', help: '', order: 10, produces: [], rows: [], kind_priority: null },
        { key: 'hardening', label: '경화식', help: '', order: 20, produces: [], rows: [], kind_priority: 3 },
        { key: 'table', label: '소성 표', help: '', order: 30, produces: [], rows: [], kind_priority: null },
        { key: 'lve', label: '선형탄성구간(LVE) 탄성률', help: '', order: 45, produces: [], rows: [], kind_priority: 5 },
      ])
    panel()
    await screen.findByText('Voce 카드')
    const chips = within(screen.getByRole('group', { name: '카드 종류' }))
    expect(chips.getByRole('button', { name: '전체 3' })).toHaveAttribute('aria-pressed', 'true')
    expect(chips.getByRole('button', { name: '탄소성 1' })).toBeInTheDocument()
    expect(chips.getByRole('button', { name: '재료 기본 정보 1' })).toBeInTheDocument()
    // 소성 표는 탄소성 카드의 일부지 종류가 아니다. 블록 이름(경화식)이 아니라 카드 종류(탄소성)로 센다.
    expect(chips.queryByRole('button', { name: /소성 표/ })).toBeNull()

    await userEvent.click(chips.getByRole('button', { name: '선형탄성구간(LVE) 탄성률 1' }))
    expect(screen.getByText('LVE 하나')).toBeInTheDocument()
    expect(screen.queryByText('Voce 카드')).not.toBeInTheDocument()
    expect(screen.queryByText('문헌 카드')).not.toBeInTheDocument()
  })
})
