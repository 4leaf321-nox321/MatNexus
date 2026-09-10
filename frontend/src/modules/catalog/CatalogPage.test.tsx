/**
 * 문헌 물성 목록 — 검색·패싯·더 보기.
 *
 *   규모가 먼저 보인다        재료·값·출처 수 — 이 저수지가 얼마나 큰가
 *   분류는 우리 표기로        metal 이 아니라 Metal (CATEGORY_MAP)
 *   상한에 닿으면 말한다      더 못 보여 줄 때 「좁혀 달라」 고 말한다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogPage from '@/modules/catalog/CatalogPage'

const summary = vi.fn()
const materials = vi.fn()

const download = vi.fn()

vi.mock('@/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/client')>()),
  downloadFile: (...args: unknown[]) => download(...args),
}))

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    summary: (...args: unknown[]) => summary(...args),
    materials: (...args: unknown[]) => materials(...args),
    material: vi.fn(),
  },
}))

const SUMMARY = {
  materials: 2663,
  values: 42209,
  sources: 3013,
  definitions: 271,
  subsystems: { pcb: 182, '': 1835 },
  categories: { metal: 320, polymer: 807 },
  domains: { mechanical: 9000 },
  tiers: { 1: 25949 },
}

const PAGE = {
  total: 2,
  limit: 50,
  offset: 0,
  items: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      name: 'SUS304',
      material_code: null,
      category: 'metal',
      subsystem: 'housing',
      role: 'product',
      manufacturer: 'POSCO',
      material_class: null,
      grade: null,
      value_count: 42,
    },
    {
      id: '22222222-2222-2222-2222-222222222222',
      name: 'FR-4 generic',
      material_code: null,
      category: 'composite',
      subsystem: null,
      role: null,
      manufacturer: null,
      material_class: null,
      grade: null,
      value_count: 7,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  summary.mockResolvedValue(SUMMARY)
  materials.mockResolvedValue(PAGE)
})

function show(routes: string[] = ['/catalog']) {
  render(
    <MemoryRouter initialEntries={routes}>
      <CatalogPage />
    </MemoryRouter>
  )
}

describe('문헌 물성 목록', () => {
  it('규모와 재료 줄이 뜬다', async () => {
    show()
    expect(await screen.findByText(/재료 2,663종/)).toBeInTheDocument()
    expect(await screen.findByText('SUS304')).toBeInTheDocument()
    expect(screen.getByText('FR-4 generic')).toBeInTheDocument()
    // 분류는 우리 표기(Metal), 계통 미분류는 「미분류」 로 말한다.
    expect(screen.getByText('Metal')).toBeInTheDocument()
    expect(screen.getAllByText('미분류').length).toBeGreaterThan(0)
  })

  it('전부 보여 줬으면 더 보기가 없다', async () => {
    show()
    await screen.findByText('SUS304')
    expect(screen.queryByRole('button', { name: /더 보기/ })).toBeNull()
  })

  it('남은 것이 있으면 더 보기가 뜬다', async () => {
    materials.mockResolvedValue({ ...PAGE, total: 500 })
    show()
    expect(await screen.findByRole('button', { name: /더 보기/ })).toBeInTheDocument()
  })

  it('지금 거른 조건 그대로 내보낸다', async () => {
    // **화면과 다른 것이 내려오면** 사람은 그 사실을 모른 채 그 파일로 계산한다.
    // 전부 받으면 70MB 가 넘으므로, 좁혀 놓고 받는 길이 기본이다.
    const user = userEvent.setup()
    show(['/catalog?q=SUS'])
    await screen.findByText('SUS304')

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    expect(download).toHaveBeenCalledWith(
      expect.stringContaining('/catalog/export?q=SUS'),
      expect.stringContaining('.json')
    )
  })
})
