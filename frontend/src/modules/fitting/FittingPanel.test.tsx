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

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FittingPanel } from '@/modules/fitting/FittingPanel'

const preview = vi.fn()
const cards = vi.fn()
const forMaterial = vi.fn()
const deprecate = vi.fn()
const restore = vi.fn()
const create = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    preview: (...args: unknown[]) => preview(...args),
    cards: (...args: unknown[]) => cards(...args),
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
  },
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

/** 묶음이 뜨면 「경화식 맞춰 보기」를 눌러 미리보기를 받는다. **자동으로 안 돈다.** */
async function compare() {
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
