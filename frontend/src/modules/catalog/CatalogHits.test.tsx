/**
 * 통합 검색 조각 — 검색은 하나다.
 *
 *   검색어가 있으면 문헌도 친다      같은 q 로 카탈로그 검색
 *   맞는 게 없으면 조용하다          블록 자체가 안 선다 (보조일 뿐)
 *   실패도 조용히 삼키지 않는다      「문헌 검색 실패」 한 줄
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CatalogHits } from '@/modules/catalog/CatalogHits'

const materials = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: { materials: (...args: unknown[]) => materials(...args) },
}))

const PAGE = {
  total: 12,
  limit: 5,
  offset: 0,
  items: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      name: 'SUS304',
      category: 'metal',
      subsystem: 'housing',
      value_count: 42,
      material_code: null,
      role: null,
      manufacturer: null,
      material_class: null,
      grade: null,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  materials.mockResolvedValue(PAGE)
})

function show(q: string) {
  render(
    <MemoryRouter>
      <CatalogHits q={q} />
    </MemoryRouter>
  )
}

describe('통합 검색', () => {
  it('검색어가 있으면 문헌 결과 블록이 선다 — 전부 보기까지', async () => {
    show('SUS')
    expect(await screen.findByText(/문헌 물성에서 12건/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /SUS304/ })).toHaveAttribute(
      'href',
      '/catalog/11111111-1111-1111-1111-111111111111'
    )
    expect(screen.getByRole('link', { name: '전부 보기' })).toHaveAttribute(
      'href',
      '/catalog?q=SUS'
    )
  })

  it('검색어가 없으면 서버를 부르지도, 그리지도 않는다', () => {
    show('  ')
    expect(materials).not.toHaveBeenCalled()
    expect(screen.queryByText(/문헌 물성/)).toBeNull()
  })

  it('맞는 것이 없으면 조용하다', async () => {
    materials.mockResolvedValue({ ...PAGE, total: 0, items: [] })
    show('없는재료')
    await waitFor(() => expect(materials).toHaveBeenCalled())
    expect(screen.queryByText(/문헌 물성/)).toBeNull()
  })

  it('실패하면 실패했다고 말한다', async () => {
    materials.mockRejectedValue(new Error('boom'))
    show('SUS')
    expect(await screen.findByText(/문헌 물성 검색에 실패/)).toBeInTheDocument()
  })
})
