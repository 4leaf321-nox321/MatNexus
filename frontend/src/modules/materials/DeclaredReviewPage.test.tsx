/**
 * 승인 대기 값 — 모아서 보이고, **승인하는 자리로 곧장 보낸다**(2026-10-04).
 *
 * 재료 값은 「물성」 탭에서, 시료 값(밀시트)은 「시료·시편」 탭에서 승인한다 — 링크가 엉뚱한
 * 탭을 열면 사람은 그 값을 다시 찾아야 한다.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import DeclaredReviewPage from '@/modules/materials/DeclaredReviewPage'

const declaredReview = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    declaredReview: (...args: unknown[]) => declaredReview(...args),
  },
}))

const BASE = {
  source: 'literature',
  reference: 'ASM Handbook p.120',
  si_unit: 'Pa',
  point_count: 1,
  sample_id: null,
  sample_name: null,
  lot_no: null,
}

beforeEach(() => {
  declaredReview.mockResolvedValue({
    items: [
      {
        ...BASE,
        level: '재료',
        material_id: 'm1',
        material_name: 'SECC_-_1.0',
        item: '탄성계수',
        first_value_si: 2.0e11,
        quality_tier: 3,
        tier_if_approved: 2,
      },
      {
        ...BASE,
        level: '시료',
        material_id: 'm2',
        material_name: 'SPCC_-_1.2',
        sample_id: 's1',
        sample_name: 'SPCC_-_1.2_S01',
        lot_no: 'L-7',
        item: '인장강도',
        source: 'estimate',
        first_value_si: 4.2e8,
        point_count: 2,
        quality_tier: 4,
        tier_if_approved: 3,
      },
    ],
    total: 2,
    limit: 200,
    offset: 0,
  })
})

it('값을 화면 단위로 보이고, 승인하는 탭으로 링크한다', async () => {
  render(
    <MemoryRouter>
      <DeclaredReviewPage />
    </MemoryRouter>
  )

  const material = await screen.findByRole('link', { name: 'SECC_-_1.0' })
  expect(material).toHaveAttribute('href', '/materials/m1?tab=properties')
  expect(screen.getByRole('link', { name: 'SPCC_-_1.2' })).toHaveAttribute(
    'href',
    '/materials/m2?tab=samples'
  )
  expect(screen.getByText('3 → 2')).toBeInTheDocument()
  expect(screen.getByText('4 → 3')).toBeInTheDocument()
  expect(screen.getByText('시료 · 로트 L-7')).toBeInTheDocument()
  expect(screen.getByText(/외 1점/)).toBeInTheDocument()
  // 첫 쪽만 읽고 끝내지 않는다 — 한 쪽 상한에서 자르면 나머지가 「없는」 것이 된다.
  expect(declaredReview).toHaveBeenCalledWith(200, 0)
})
