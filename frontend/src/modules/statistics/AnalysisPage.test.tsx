/**
 * 물성 분석 — **숫자가 왜 이 수인지 화면이 말하는가.**
 *
 * 무는 자리를 「탭이 열린다」 보다 **「빠진 건수를 말한다」**·「1건이면 흩어짐을 안
 * 적는다」·「빈 칸과 0을 구별한다」 에 둔다. 앞엣것은 눈에 보이지만, 뒤엣것은
 * 조용히 틀린 수를 읽게 만든다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalysisPage, { show } from '@/modules/statistics/AnalysisPage'

const compare = vi.fn()
const distribution = vi.fn()
const specGap = vi.fn()
const trend = vi.fn()
const coverage = vi.fn()
const findMaterials = vi.fn()

vi.mock('@/modules/statistics/analysisApi', async () => {
  const actual = await vi.importActual<typeof import('@/modules/statistics/analysisApi')>(
    '@/modules/statistics/analysisApi'
  )
  return {
    ...actual,
    analysisApi: {
      compare: (...a: unknown[]) => compare(...a),
      distribution: (...a: unknown[]) => distribution(...a),
      specGap: (...a: unknown[]) => specGap(...a),
      trend: (...a: unknown[]) => trend(...a),
      coverage: (...a: unknown[]) => coverage(...a),
      findMaterials: (...a: unknown[]) => findMaterials(...a),
    },
  }
})

function mount(tab = 'compare') {
  return render(
    <MemoryRouter initialEntries={[`/compare?tab=${tab}`]}>
      <Routes>
        <Route path="/compare" element={<AnalysisPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  compare.mockResolvedValue({ materials: [], scalars: [], skipped_unadopted: 0 })
  distribution.mockResolvedValue({
    scalar_key: '',
    scalar_label: '',
    si_unit: '1',
    group_by: 'division',
    groups: [],
    scalars: [],
    skipped_unadopted: 0,
  })
  specGap.mockResolvedValue({ rows: [], unmatched_items: [] })
  trend.mockResolvedValue({
    scalar_key: '',
    scalar_label: '',
    si_unit: '1',
    group_by: 'division',
    series: [],
    scalars: [],
    skipped_unadopted: 0,
  })
  coverage.mockResolvedValue({ test_types: [], materials: [] })
  findMaterials.mockResolvedValue([])
})

describe('탭', () => {
  it('다섯이 서고 비교가 기본이다', async () => {
    mount()
    for (const name of ['재료 비교', '분포', '사양 대비', '추이', '커버리지']) {
      expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    }
    expect(await screen.findByText(/견줄 재료를 골라 주세요/)).toBeInTheDocument()
  })
})

describe('재료 비교', () => {
  it('고른 것만 세고, 1건이면 흩어짐을 안 적는다', async () => {
    findMaterials.mockResolvedValue([{ id: 'm1', record_name: 'SECC_1.0' }])
    compare.mockResolvedValue({
      materials: [
        {
          material_id: 'm1',
          material_name: 'SECC_1.0',
          family: 'Metal',
          scalars: [
            {
              scalar_key: 'tensile_strength',
              scalar_label: '인장강도',
              si_unit: 'Pa',
              count: 1,
              mean: 300e6,
              sample_sd: null,
              minimum: 300e6,
              maximum: 300e6,
            },
          ],
        },
      ],
      scalars: [],
      skipped_unadopted: 2,
    })
    const user = userEvent.setup()
    mount()
    await user.type(screen.getByLabelText('재료 찾기'), 'SECC')
    await user.click(await screen.findByRole('button', { name: '+ SECC_1.0' }))
    await waitFor(() => expect(compare).toHaveBeenCalledWith(['m1']))

    // **1건이면 ± 가 없다** — 0 을 적으면 「완벽히 일정」 으로 읽힌다.
    const cell = await screen.findByText('n=1')
    expect(cell.textContent).not.toContain('±')
    // **빠진 건수를 말한다** — 조용히 빼면 n 이 왜 이 수인지 모른다.
    expect(screen.getByText(/채택되지 않아 2건이 빠졌습니다/)).toBeInTheDocument()
  })
})

describe('분포', () => {
  it('2건 미만이면 상자를 안 그리고 그렇게 말한다', async () => {
    distribution.mockResolvedValue({
      scalar_key: 'tensile_strength',
      scalar_label: '인장강도',
      si_unit: 'Pa',
      group_by: 'division',
      groups: [
        { group: 'MX', spread: null },
        {
          group: 'VD',
          spread: {
            count: 4,
            minimum: 1e8,
            q1: 2e8,
            median: 3e8,
            q3: 4e8,
            maximum: 5e8,
            mean: 3e8,
            outliers: [9e8],
          },
        },
      ],
      scalars: [{ key: 'tensile_strength', label: '인장강도', si_unit: 'Pa', count: 5 }],
      skipped_unadopted: 0,
    })
    mount('distribution')
    expect(await screen.findByText(/2건 미만 — 상자를 그릴 수 없습니다/)).toBeInTheDocument()
    // 이상치 수가 보인다 — 그것이 곧 재시험 후보다.
    expect(screen.getByText('1')).toBeInTheDocument()
  })
})

describe('사양 대비', () => {
  it('부호로 방향을 말하고, 못 견준 항목을 숨기지 않는다', async () => {
    specGap.mockResolvedValue({
      rows: [
        {
          material_id: 'm1',
          material_name: 'SECC_1.0',
          item: '인장강도',
          declared_si: 200e6,
          declared_source: 'datasheet',
          declared_reference: 'KS D 3512',
          measured_mean: 310e6,
          measured_count: 3,
          si_unit: 'Pa',
          gap_ratio: 0.55,
        },
      ],
      unmatched_items: ['열전도도'],
    })
    mount('spec')
    expect(await screen.findByText('+55.0%')).toBeInTheDocument()
    expect(screen.getByText(/못 견준 항목: 열전도도/)).toBeInTheDocument()
  })
})

describe('커버리지', () => {
  it('빈 칸과 0건을 구별한다', async () => {
    coverage.mockResolvedValue({
      test_types: [
        { key: 'tensile', label: '인장' },
        { key: 'dma', label: 'DMA' },
      ],
      materials: [
        {
          material_id: 'm1',
          material_name: 'SECC_1.0',
          family: 'Metal',
          // DMA 는 아예 없다 — **빈 칸이 요점이다.**
          cells: { tensile: { run_count: 3, adopted_count: 1 } },
        },
      ],
    })
    mount('coverage')
    expect(await screen.findByText('SECC_1.0')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('(1)')).toBeInTheDocument()
    // 빈 칸은 0 이 아니라 점이다 — 0 을 적으면 「쟀는데 0건」 으로 읽힌다.
    expect(screen.getByText('·')).toBeInTheDocument()
  })
})

describe('show', () => {
  it('SI 를 표시 단위로 바꾸고 자릿수를 크기에 맞춘다', () => {
    // Pa → MPa. **라벨에 단위를 손으로 안 적는다**(shared/units).
    expect(show(310e6, 'Pa')).toBe('310.0')
    expect(show(0, 'Pa')).toBe('0')
  })
})
