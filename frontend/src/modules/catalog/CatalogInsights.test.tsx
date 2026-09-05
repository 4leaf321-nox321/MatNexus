/**
 * 3단계 화면 — 비교 · Ashby · 커버리지.
 *
 *   비교 칸에는 대표값·tier·후보 수가 산다
 *   Ashby 는 로그축에서 뺀 점 수를 말한다 (조용히 사라진 점은 없는 재료처럼 보인다)
 *   커버리지의 빈 칸은 빈 칸으로 보인다
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogAshbyPage from '@/modules/catalog/CatalogAshbyPage'
import CatalogComparePage from '@/modules/catalog/CatalogComparePage'
import CatalogCoveragePage from '@/modules/catalog/CatalogCoveragePage'

const compare = vi.fn()
const axes = vi.fn()
const ashby = vi.fn()
const coverage = vi.fn()
const materials = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    compare: (...args: unknown[]) => compare(...args),
    axes: (...args: unknown[]) => axes(...args),
    ashby: (...args: unknown[]) => ashby(...args),
    coverage: (...args: unknown[]) => coverage(...args),
    materials: (...args: unknown[]) => materials(...args),
  },
}))

const A = '11111111-1111-1111-1111-111111111111'
const B = '22222222-2222-2222-2222-222222222222'

beforeEach(() => {
  vi.clearAllMocks()
  materials.mockResolvedValue({ total: 0, limit: 8, offset: 0, items: [] })
  // 단위 모드가 브라우저에 남는다 — 시험끼리 새지 않게 지운다.
  localStorage.clear()
})

describe('비교', () => {
  it('칸에 대표값·tier·후보 수가 선다', async () => {
    compare.mockResolvedValue({
      materials: [
        { id: A, name: 'SUS304', category: 'metal' },
        { id: B, name: 'FR-4', category: 'composite' },
      ],
      rows: [
        {
          property_key: 'mechanical.youngs_modulus',
          name: '영률',
          domain: 'mechanical',
          symbol: 'E',
          unit: 'Pa',
          cells: [
            {
              value_num: 1.93e11,
              value_text: null,
              quality_tier: 1,
              n_candidates: 2,
              conditions: null,
            },
            { value_num: null, value_text: null, quality_tier: null, n_candidates: 0 },
          ],
        },
      ],
    })
    render(
      <MemoryRouter initialEntries={[`/catalog/compare?ids=${A},${B}`]}>
        <CatalogComparePage />
      </MemoryRouter>
    )
    // 기본은 표시용 단위 — Pa 가 MPa 로 보인다.
    expect(await screen.findByText(/1\.930e\+5 MPa/)).toBeInTheDocument()
    expect(screen.getByText(/실측 · 후보 2/)).toBeInTheDocument()
    // FR-4 칸은 빈 칸으로 보인다.
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('두 종 미만이면 표 대신 안내가 선다', () => {
    render(
      <MemoryRouter initialEntries={['/catalog/compare']}>
        <CatalogComparePage />
      </MemoryRouter>
    )
    expect(screen.getByText(/두 종 이상 추가하면/)).toBeInTheDocument()
    expect(compare).not.toHaveBeenCalled()
  })
})

describe('Ashby', () => {
  it('로그축에서 뺀 점 수를 말한다', async () => {
    axes.mockResolvedValue([
      {
        key: 'mechanical.youngs_modulus',
        name: '영률',
        domain: 'mechanical',
        unit: 'Pa',
        material_count: 100,
      },
      {
        key: 'physical.density',
        name: '밀도',
        domain: 'physical',
        unit: 'kg/m^3',
        material_count: 90,
      },
    ])
    ashby.mockResolvedValue({
      x_unit: 'Pa',
      y_unit: 'kg/m^3',
      points: [
        { id: A, name: 'SUS304', group: 'metal', x: 1.93e11, y: 7930 },
        // 로그축에서 빠질 점 — 조용히 사라지면 안 된다.
        { id: B, name: '이상한 값', group: 'metal', x: 0, y: 100 },
      ],
    })
    render(
      <MemoryRouter
        initialEntries={['/catalog/ashby?x=mechanical.youngs_modulus&y=physical.density']}
      >
        <CatalogAshbyPage />
      </MemoryRouter>
    )
    expect(await screen.findByText(/1종 표시/)).toBeInTheDocument()
    expect(screen.getByText(/0·음수 1점 제외/)).toBeInTheDocument()
  })

  it('양 축에 물성 이름과 단위가 적힌다', async () => {
    axes.mockResolvedValue([
      {
        key: 'mechanical.youngs_modulus',
        name: '영률',
        domain: 'mechanical',
        unit: 'Pa',
        material_count: 100,
      },
      {
        key: 'physical.density',
        name: '밀도',
        domain: 'physical',
        unit: 'kg/m^3',
        material_count: 90,
      },
    ])
    ashby.mockResolvedValue({
      x_unit: 'Pa',
      y_unit: 'kg/m^3',
      points: [{ id: A, name: 'SUS304', group: 'metal', x: 1.93e11, y: 7930 }],
    })
    render(
      <MemoryRouter
        initialEntries={['/catalog/ashby?x=mechanical.youngs_modulus&y=physical.density']}
      >
        <CatalogAshbyPage />
      </MemoryRouter>
    )
    // 기본은 표시용 단위(공용 표) — Pa→MPa, kg/m3→tonne/mm³ (CAE 관행).
    expect(await screen.findByText('영률 (MPa)')).toBeInTheDocument()
    expect(screen.getByText('밀도 (tonne/mm³)')).toBeInTheDocument()

    // SI 로 바꾸면 정본 철자로.
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(screen.getByLabelText('단위 모드'), { target: { value: 'si' } })
    expect(await screen.findByText('영률 (Pa)')).toBeInTheDocument()
    expect(screen.getByText('밀도 (kg/m3)')).toBeInTheDocument()
  })
})

describe('커버리지', () => {
  it('격자가 서고 빈 칸은 빈 칸으로 보인다', async () => {
    coverage.mockResolvedValue({
      domains: ['mechanical', 'thermal'],
      subsystems: ['housing', ''],
      cells: { housing: { mechanical: 120 }, '': { thermal: 3 } },
    })
    render(
      <MemoryRouter>
        <CatalogCoveragePage />
      </MemoryRouter>
    )
    expect(await screen.findByText('120')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '미분류' })).toBeInTheDocument()
    // housing 줄의 열(thermal) 칸은 빈 칸.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})
