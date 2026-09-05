/**
 * 문헌 재료 상세 — **진 후보를 숨기지 않는다.**
 *
 *   대표가 먼저, 후보 수와 함께     「대표값 · 후보 2」
 *   진 후보는 밀린 자리와 함께      「대안 · 등급」
 *   가정값은 가정이라고 말한다      tier4 + assumption → 「가정」 배지 (제외는 안 한다)
 *   출처가 값 옆에 산다            제목·연도·DOI 링크
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogMaterialPage from '@/modules/catalog/CatalogMaterialPage'

const material = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    summary: vi.fn(),
    materials: vi.fn(),
    material: (...args: unknown[]) => material(...args),
  },
}))

const SOURCE = {
  id: '99999999-9999-9999-9999-999999999999',
  kind: 'journal',
  doi: '10.1000/x',
  url: null,
  title: '어느 논문',
  year: 2020,
  publisher: null,
  license: null,
}

const DETAIL = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'SUS304',
  material_code: null,
  category: 'metal',
  description: null,
  subsystem: 'housing',
  role: 'product',
  manufacturer: 'POSCO',
  material_class: null,
  grade: null,
  attributes: {},
  values: [
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000001',
      property_key: 'mechanical.youngs_modulus',
      property_name: '영률',
      domain: 'mechanical',
      symbol: 'E',
      value_num: 1.93e11,
      value_text: null,
      unit: 'Pa',
      uncertainty: null,
      conditions: { temperature_k: 296.15, corrected_by: '54차 PA' },
      method: 'measured',
      quality_tier: 1,
      source: SOURCE,
      source_detail: 'Table 2',
      notes: null,
      representative: true,
      n_candidates: 2,
      separated_by: null,
    },
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000002',
      property_key: 'mechanical.youngs_modulus',
      property_name: '영률',
      domain: 'mechanical',
      symbol: 'E',
      value_num: 2.0e11,
      value_text: null,
      unit: 'Pa',
      uncertainty: null,
      conditions: { assumption: true },
      method: 'estimated',
      quality_tier: 4,
      source: null,
      source_detail: null,
      notes: null,
      representative: false,
      n_candidates: 2,
      separated_by: '등급',
    },
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000003',
      property_key: 'thermal.glass_transition',
      property_name: '유리전이온도',
      domain: 'thermal',
      symbol: 'Tg',
      value_num: 408.15,
      value_text: null,
      unit: 'K',
      uncertainty: null,
      conditions: null,
      method: 'handbook',
      quality_tier: 2,
      source: SOURCE,
      source_detail: null,
      notes: null,
      representative: true,
      n_candidates: 1,
      separated_by: null,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  material.mockResolvedValue(DETAIL)
})

function show() {
  render(
    <MemoryRouter initialEntries={['/catalog/11111111-1111-1111-1111-111111111111']}>
      <Routes>
        <Route path="/catalog/:id" element={<CatalogMaterialPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('진 후보를 숨기지 않는다', () => {
  it('대표는 후보 수와, 대안은 밀린 자리와 함께 선다', async () => {
    show()
    expect(await screen.findByText(/대표값 · 후보 2/)).toBeInTheDocument()
    expect(screen.getByText(/대안 · 등급/)).toBeInTheDocument()
  })

  it('가정값은 「가정」 배지를 달고 그대로 보인다 — 제외하지 않는다', async () => {
    show()
    expect(await screen.findByText('가정')).toBeInTheDocument()
    // 값 자체도 표에 있다.
    expect(screen.getByText(/2\.000e\+11 Pa/)).toBeInTheDocument()
  })

  it('도메인으로 갈라 서고, 조건과 출처가 값 옆에 있다', async () => {
    show()
    expect(await screen.findByText('기계')).toBeInTheDocument()
    expect(screen.getByText('열')).toBeInTheDocument()
    expect(screen.getByText(/T 296\.15 K/)).toBeInTheDocument()
    // 같은 출처가 값 두 줄(영률·Tg)에 붙어 링크도 둘이다 — 전부 DOI 로 간다.
    const links = screen.getAllByRole('link', { name: '어느 논문' })
    expect(links).toHaveLength(2)
    for (const link of links) {
      expect(link).toHaveAttribute('href', 'https://doi.org/10.1000/x')
    }
  })

  it('관리 표지(corrected_by 등)는 조건 줄에 안 보인다', async () => {
    show()
    await screen.findByText(/T 296\.15 K/)
    expect(screen.queryByText(/corrected_by/)).toBeNull()
  })
})
