/**
 * 물성 지도 — **문헌 곡선 · 산점 한 벌은 한 줄**이고, 「점 펼치기」 로 그 벌의 점을 받아 그 아래에
 * 편다(2026-10-26). 점마다 한 줄이면 산점이 수백 벌인 재료의 지도가 칸 7천 개였다.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PropertyCoverageTable } from '@/modules/materials/PropertyCoverageTable'
import type { CoverageEntry } from '@/modules/materials/api'

const propertyCoverage = vi.fn()
const coverageSeries = vi.fn()
vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    propertyCoverage: (...args: unknown[]) => propertyCoverage(...args),
    coverageSeries: (...args: unknown[]) => coverageSeries(...args),
  },
}))

function entry(over: Partial<CoverageEntry>): CoverageEntry {
  return {
    origin: 'catalog',
    tier: 3,
    value_si: 1.6e8,
    count: 1,
    spread_si: null,
    conditions: {},
    method: 'FatigueData-AM2022',
    ref_kind: 'catalog_value',
    ref_id: 'v0',
    ref_label: 'Ti-6Al-4V (L-PBF)',
    ...over,
  } as CoverageEntry
}

const SERIES = entry({
  ref_kind: 'catalog_series',
  ref_id: 's1',
  series_id: 's1',
  series_kind: 'scatter',
  series_label: 'Lee 2021',
  count: 3,
  low_si: 1.088e8,
  high_si: 2.204e8,
  conditions: { temperature: 298.15 },
  axis_label: '수명(반복수)',
  axis_low: 1e5,
  axis_high: 1e7,
})

/** 응답을 늦춘다 — 느린 머신에서 아직 안 그려진 화면을 보지 않게(AGENTS.md). */
function later<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 30))
}

beforeEach(() => {
  propertyCoverage.mockReset()
  coverageSeries.mockReset()
  propertyCoverage.mockImplementation(() =>
    later({
      material_id: 'm1',
      counts: {},
      unmapped: {},
      properties: [
        {
          key: 'mechanical.fatigue_strength',
          name: '피로강도',
          si_unit: 'Pa',
          entries: [SERIES, entry({ ref_id: 'v9', value_si: 4.0e8 })],
        },
      ],
    })
  )
})

describe('물성 지도의 문헌 한 벌', () => {
  it('한 줄에 점 수 · 값 범위 · 축 범위로 선다', async () => {
    render(<PropertyCoverageTable materialId="m1" />)
    const row = (await screen.findByText(/「Lee 2021」/)).closest('tr')!
    expect(within(row).getByText(/108.8~220.4 MPa/)).toBeInTheDocument()
    expect(within(row).getByText(/점 3/)).toBeInTheDocument()
    expect(within(row).getByText(/수명\(반복수\) 1.000e\+5~1.000e\+7/)).toBeInTheDocument()
    expect(coverageSeries).not.toHaveBeenCalled()
  })

  it('펼치면 그 벌의 점을 받아 아래에 펴고, 접으면 거둔다', async () => {
    coverageSeries.mockImplementation(() =>
      later({
        series_id: 's1',
        label: 'Lee 2021',
        total: 250,
        shown: 2,
        properties: [
          {
            key: 'mechanical.fatigue_strength',
            name: '피로강도',
            si_unit: 'Pa',
            entries: [
              entry({ ref_id: 'p1', value_si: 2.204e8, axis_label: '수명(반복수)', axis_low: 1e5, axis_high: 1e5 }),
              entry({ ref_id: 'p2', value_si: 1.088e8, axis_label: '수명(반복수)', axis_low: 1e7, axis_high: 1e7 }),
            ],
          },
        ],
      })
    )
    render(<PropertyCoverageTable materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: /점 펼치기 \(3\)/ }))
    expect(coverageSeries).toHaveBeenCalledWith('m1', 's1')
    expect(await screen.findByText('220.4 MPa')).toBeInTheDocument()
    expect(screen.getByText('108.8 MPa')).toBeInTheDocument()
    expect(screen.getByText(/점 250개 중 2개/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /점 접기/ }))
    expect(screen.queryByText('220.4 MPa')).not.toBeInTheDocument()
    // 다시 펴면 받은 것을 쓴다.
    await userEvent.click(screen.getByRole('button', { name: /점 펼치기 \(3\)/ }))
    expect(await screen.findByText('220.4 MPa')).toBeInTheDocument()
    expect(coverageSeries).toHaveBeenCalledTimes(1)
  })
})
