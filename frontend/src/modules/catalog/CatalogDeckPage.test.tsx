/**
 * 문헌 덱 만들기 — BOM 3단계.
 *
 *   매칭은 후보를 사람 앞에 세운다     자동 확정하지 않는다
 *   MID 없는 줄은 이어지는 번호        지정과 자동이 섞여도 안 겹친다
 *   모자란 재료는 이유와 함께 선다      조용히 빠진 재료는 없는 재료다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogDeckPage from '@/modules/catalog/CatalogDeckPage'

const deckMatch = vi.fn()
const deckBuild = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    deckMatch: (...args: unknown[]) => deckMatch(...args),
    deckBuild: (...args: unknown[]) => deckBuild(...args),
  },
}))

const SUS_ID = '11111111-1111-1111-1111-111111111111'
const FR4_ID = '22222222-2222-2222-2222-222222222222'

const MATCHED = [
  {
    query: 'SUS304',
    mid: 101,
    candidates: [
      { id: SUS_ID, name: 'SUS304', category: 'metal', value_count: 42, score: 3 },
    ],
  },
  {
    query: 'FR-4',
    mid: null,
    candidates: [
      { id: FR4_ID, name: 'FR-4 generic', category: 'composite', value_count: 7, score: 2 },
    ],
  },
]

const BUILT = {
  filename: 'matnexus_catalog_si.k',
  text: '*KEYWORD\n$ youngs_modulus = 1.93E+11 — 어느 논문 [tier 1]\n*MAT_ELASTIC\n*END\n',
  material_count: 1,
  skipped: [{ mid: 1, name: 'FR-4 generic', missing: ['푸아송비', '밀도'] }],
  notes: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  deckMatch.mockResolvedValue(MATCHED)
  deckBuild.mockResolvedValue(BUILT)
})

async function toStep2() {
  render(
    <MemoryRouter>
      <CatalogDeckPage />
    </MemoryRouter>
  )
  await userEvent.type(screen.getByLabelText('재료 목록'), '101, SUS304\nFR-4')
  await userEvent.click(screen.getByRole('button', { name: '매칭' }))
  await screen.findByText(/매칭 확인/)
}

describe('BOM 3단계', () => {
  it('후보가 서고, MID 없는 줄은 이어지는 번호를 받는다', async () => {
    await toStep2()
    expect(screen.getByLabelText('SUS304 의 MID')).toHaveValue(101)
    // FR-4 는 MID 가 없었다 — 1부터 비는 번호.
    expect(screen.getByLabelText('FR-4 의 MID')).toHaveValue(1)
    expect(screen.getByRole('option', { name: /SUS304 · 물성 42 · 정확/ })).toBeInTheDocument()
  })

  it('덱을 만들면 미리보기와 「못 실은 재료」 가 이유와 함께 선다', async () => {
    await toStep2()
    await userEvent.click(screen.getByRole('button', { name: /덱 만들기/ }))
    await waitFor(() => expect(deckBuild).toHaveBeenCalledTimes(1))
    const body = deckBuild.mock.calls[0][0] as {
      items: { mid: number; catalog_material_id: string }[]
      format: string
    }
    expect(body.items).toEqual([
      { mid: 101, catalog_material_id: SUS_ID },
      { mid: 1, catalog_material_id: FR4_ID },
    ])
    expect(body.format).toBe('dyna_elastic')

    expect(await screen.findByText(/어느 논문/)).toBeInTheDocument()
    expect(screen.getByText(/물성이 모자라 덱에 못 실은 재료 1건/)).toBeInTheDocument()
    expect(screen.getByText(/없는 것: 푸아송비, 밀도/)).toBeInTheDocument()
  })
})
