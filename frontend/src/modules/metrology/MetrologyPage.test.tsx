/**
 * 측정법 화면.
 *
 *   요약 타일이 카탈로그 장비 수와 보유 수를 가른다
 *   피커가 잴 수 있는 물성과 장비 없는 물성을 가른다
 *   ?key= 딥링크로 오면 기법별 표가 바로 선다 — 확신도 ≠ high 는 표시가 붙는다
 *   빈 칸은 — 로 보인다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MetrologyPage from '@/modules/metrology/MetrologyPage'

const summary = vi.fn()
const coverage = vi.fn()
const byProperty = vi.fn()

vi.mock('@/modules/metrology/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/metrology/api')>()),
  metrologyApi: {
    summary: (...args: unknown[]) => summary(...args),
    coverage: (...args: unknown[]) => coverage(...args),
    byProperty: (...args: unknown[]) => byProperty(...args),
  },
}))

const YOUNG = {
  property_key: 'mechanical.youngs_modulus',
  name: '탄성계수',
  domain: 'mechanical',
  symbol: 'E',
  si_unit: 'Pa',
  technique_count: 1,
  instrument_count: 1,
  owned_instrument_count: 1,
  value_count: 12,
}
const DENSITY = {
  property_key: 'physical.density',
  name: '밀도',
  domain: 'physical',
  symbol: 'rho',
  si_unit: 'kg/m3',
  technique_count: 0,
  instrument_count: 0,
  owned_instrument_count: 0,
  value_count: 7,
}

beforeEach(() => {
  vi.clearAllMocks()
  summary.mockResolvedValue({
    instruments: 218,
    instruments_owned: 12,
    capabilities: 532,
    properties_covered: 96,
    properties_total: 271,
    categories: { mechanical: 40 },
  })
  coverage.mockResolvedValue({ covered: [YOUNG], gaps: [DENSITY] })
})

describe('측정법', () => {
  it('요약이 카탈로그 장비와 보유를 가르고, 피커가 빈 칸을 숨기지 않는다', async () => {
    render(
      <MemoryRouter initialEntries={['/metrology']}>
        <MetrologyPage />
      </MemoryRouter>
    )
    expect(await screen.findByText('218')).toBeInTheDocument()
    expect(screen.getByText('보유 장비')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    // 커버된 물성은 전체 대비로 읽힌다.
    expect(screen.getByText('96')).toBeInTheDocument()
    expect(screen.getByText('/ 271')).toBeInTheDocument()
    // 잴 수 있는 물성과 장비 없는 물성이 갈라져 선다.
    expect(screen.getByText('탄성계수')).toBeInTheDocument()
    expect(screen.getByText('장비 1 · 보유 1')).toBeInTheDocument()
    expect(screen.getByText('밀도')).toBeInTheDocument()
    expect(screen.getByText('값 7')).toBeInTheDocument()
    expect(byProperty).not.toHaveBeenCalled()
  })

  it('딥링크(?key=)로 오면 기법별 표가 서고, 확신도 표시와 빈 칸이 산다', async () => {
    byProperty.mockResolvedValue({
      property_key: 'mechanical.youngs_modulus',
      name: '탄성계수',
      domain: 'mechanical',
      symbol: 'E',
      si_unit: 'Pa',
      test_standard: 'ISO 6892',
      techniques: [
        {
          technique: 'tensile',
          capabilities: [
            {
              id: 'c1',
              instrument: {
                id: 'i1',
                vendor: 'Instron',
                model: '5982',
                category: 'mechanical',
                owned: true,
                owned_note: null,
                owner_name: '홍측정',
              },
              standard: 'ISO 6892-1',
              range_min: 0.5,
              range_max: 100000,
              range_unit: 'N',
              resolution: '0.01',
              accuracy: null,
              temperature_min_k: 233.15,
              temperature_max_k: 573.15,
              specimen: 'dogbone',
              mapping_confidence: 'medium',
              source_detail: 'p.12',
              notes: null,
            },
          ],
        },
      ],
    })
    render(
      <MemoryRouter initialEntries={['/metrology?key=mechanical.youngs_modulus']}>
        <MetrologyPage />
      </MemoryRouter>
    )
    expect(byProperty).toHaveBeenCalledWith('mechanical.youngs_modulus')
    expect(await screen.findByText('tensile')).toBeInTheDocument()
    expect(screen.getByText(/Instron 5982/)).toBeInTheDocument()
    expect(screen.getByText('보유 (홍측정)')).toBeInTheDocument()
    expect(screen.getByText('ISO 6892-1')).toBeInTheDocument()
    expect(screen.getByText('0.5 ~ 100000 N')).toBeInTheDocument()
    expect(screen.getByText('233.15 ~ 573.15 K')).toBeInTheDocument()
    // 확신도 medium — 표시가 붙는다.
    expect(screen.getByText('⚠')).toBeInTheDocument()
    // accuracy 는 빈 칸(—)으로 보인다.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('피커에서 물성을 고르면 상세를 부른다', async () => {
    byProperty.mockResolvedValue({
      property_key: 'mechanical.youngs_modulus',
      name: '탄성계수',
      domain: 'mechanical',
      symbol: 'E',
      si_unit: 'Pa',
      test_standard: null,
      techniques: [],
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/metrology']}>
        <MetrologyPage />
      </MemoryRouter>
    )
    await user.click(await screen.findByText('탄성계수'))
    expect(byProperty).toHaveBeenCalledWith('mechanical.youngs_modulus')
    // 기법이 하나도 없으면 그 사실이 그대로 보인다.
    expect(
      await screen.findByText('이 물성을 잴 수 있는 장비가 카탈로그에 없습니다.')
    ).toBeInTheDocument()
  })
})
