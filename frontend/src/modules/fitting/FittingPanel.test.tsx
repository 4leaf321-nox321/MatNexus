/**
 * 적합 화면 — **보여 준 것을 저장할 수 있어야 한다.**
 *
 * 이 파일이 지키는 것은 둘이다.
 *
 *   늘리기 칸은 늘릴 수 있는 식에서만 열린다
 *   축 이름은 식이 정한다 — 화면이 하드코딩하지 않는다
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

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    preview: (...args: unknown[]) => preview(...args),
    cards: (...args: unknown[]) => cards(...args),
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
