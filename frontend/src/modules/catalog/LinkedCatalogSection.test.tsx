/**
 * 문헌 연결 섹션 — 사내 재료 상세에서 잇고, 풀고, 채우기로 이어진다.
 *
 *   비어 있으면 잇는 길이 보인다     「문헌 재료 연결」 → 검색 → 선택
 *   이어져 있으면 요약이 보인다      이름·분류·물성값 수 + 채우기·해제
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LinkedCatalogSection } from '@/modules/catalog/LinkedCatalogSection'
import type { components } from '@/shared/api/schema'

const link = vi.fn()
const setLink = vi.fn()
const clearLink = vi.fn()
const materials = vi.fn()
const material = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    link: (...args: unknown[]) => link(...args),
    setLink: (...args: unknown[]) => setLink(...args),
    clearLink: (...args: unknown[]) => clearLink(...args),
    materials: (...args: unknown[]) => materials(...args),
    material: (...args: unknown[]) => material(...args),
  },
}))

const MATERIAL = {
  id: '33333333-3333-3333-3333-333333333333',
  record_name: 'SGARC440 1.2t',
  declared_properties: [],
  density: null,
  poisson_ratio: null,
} as unknown as components['schemas']['MaterialOut']

const LINKED = {
  catalog_material_id: '11111111-1111-1111-1111-111111111111',
  name: 'SUS304',
  category: 'metal',
  subsystem: 'housing',
  value_count: 42,
}

const EMPTY = { catalog_material_id: null, name: null, category: null, subsystem: null, value_count: 0 }

beforeEach(() => {
  vi.clearAllMocks()
  material.mockResolvedValue({ id: LINKED.catalog_material_id, name: 'SUS304', values: [] })
  materials.mockResolvedValue({
    total: 1,
    limit: 8,
    offset: 0,
    items: [{ id: LINKED.catalog_material_id, name: 'SUS304', category: 'metal' }],
  })
})

function show() {
  render(
    <MemoryRouter>
      <LinkedCatalogSection material={MATERIAL} />
    </MemoryRouter>
  )
}

describe('문헌 연결', () => {
  it('비어 있으면 검색해서 잇는다', async () => {
    link.mockResolvedValue(EMPTY)
    setLink.mockResolvedValue(LINKED)
    show()
    await userEvent.click(await screen.findByRole('button', { name: /문헌 재료 연결/ }))
    await userEvent.click(await screen.findByRole('button', { name: /SUS304/ }))
    await waitFor(() =>
      expect(setLink).toHaveBeenCalledWith(String(MATERIAL.id), LINKED.catalog_material_id)
    )
    expect(await screen.findByText(/물성값 42건/)).toBeInTheDocument()
  })

  it('이어져 있으면 요약과 채우기·해제가 보인다', async () => {
    link.mockResolvedValue(LINKED)
    clearLink.mockResolvedValue(undefined)
    show()
    expect(await screen.findByRole('link', { name: 'SUS304' })).toHaveAttribute(
      'href',
      `/catalog/${LINKED.catalog_material_id}`
    )
    expect(screen.getByText(/물성값 42건/)).toBeInTheDocument()
    // 채우기용 상세를 미리 받는다.
    await waitFor(() => expect(material).toHaveBeenCalled())

    await userEvent.click(screen.getByRole('button', { name: /연결 해제/ }))
    await waitFor(() => expect(clearLink).toHaveBeenCalledWith(String(MATERIAL.id)))
  })
})
