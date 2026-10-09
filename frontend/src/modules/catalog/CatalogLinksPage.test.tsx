/**
 * 사내 재료 연결 후보 화면.
 *
 *   후보를 근거와 함께 보인다      어느 칸이 · 왜 걸렸나 · 물성값 수
 *   한 건씩 잇고 그 자리에 남긴다   이은 줄은 「이음」 + 되돌리기
 *   권한이 없으면 단추를 잠근다
 *   상한에 잘렸으면 그렇다고 말한다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogLinksPage from '@/modules/catalog/CatalogLinksPage'

const linkCandidateList = vi.fn()
const setLink = vi.fn()
const clearLink = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    linkCandidateList: (...args: unknown[]) => linkCandidateList(...args),
    setLink: (...args: unknown[]) => setLink(...args),
    clearLink: (...args: unknown[]) => clearLink(...args),
  },
}))

const T6 = '11111111-1111-1111-1111-111111111111'
const T5 = '22222222-2222-2222-2222-222222222222'

function candidate(id: string, name: string, count: number) {
  return {
    catalog_material_id: id,
    name,
    category: 'metal',
    value_count: count,
    matched_by: 'prefix',
    matched_on: 'grade',
    matched_text: 'AL6063',
  }
}

const PAGE = {
  unlinked: 7,
  with_candidates: 3,
  items: [
    {
      material_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      code: 'M-0001',
      record_name: 'AL6063_-_1.0',
      family: 'Metal',
      category: 'Aluminum',
      grade: 'AL6063',
      alias: null,
      can_edit: true,
      candidates: [candidate(T6, 'Al6063-T6 Bilinear', 64), candidate(T5, 'Al6063-T5 Bilinear', 49)],
    },
    {
      material_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      code: 'M-0002',
      record_name: 'SUS304_-_1.0',
      family: 'Metal',
      category: 'Steel',
      grade: 'SUS304',
      alias: null,
      can_edit: false,
      candidates: [
        { ...candidate(T6, 'SUS304_annealed Bilinear', 59), matched_text: 'SUS304' },
      ],
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  linkCandidateList.mockResolvedValue(PAGE)
  setLink.mockResolvedValue({})
  clearLink.mockResolvedValue(undefined)
})

function show() {
  render(
    <MemoryRouter>
      <CatalogLinksPage />
    </MemoryRouter>
  )
}

describe('사내 재료 연결 후보', () => {
  it('후보를 근거와 함께 보이고, 잘렸으면 그렇다고 말한다', async () => {
    show()
    expect(await screen.findByText(/물성값 64건/)).toBeInTheDocument()
    expect(screen.getByText(/안 이어진 사내 재료 7종 · 그중 후보가 있는 것 3종 · 앞의 2종만/)).toBeInTheDocument()
    expect(screen.getAllByText(/등급 「AL6063」 · 이름이 이것으로 시작한다/)).toHaveLength(2)
  })

  it('한 건씩 잇고, 이은 줄은 그 자리에 남아 되돌릴 수 있다', async () => {
    show()
    await userEvent.click(
      await screen.findByRole('button', { name: 'AL6063_-_1.0 을 Al6063-T6 Bilinear 에 연결' })
    )
    await waitFor(() =>
      expect(setLink).toHaveBeenCalledWith('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', T6)
    )
    expect(await screen.findByText(/에 이음/)).toBeInTheDocument()
    // 다른 후보는 내려간다 — 재료당 연결은 하나다.
    expect(screen.queryByText('Al6063-T5 Bilinear')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /되돌리기/ }))
    await waitFor(() =>
      expect(clearLink).toHaveBeenCalledWith('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
    )
    expect(await screen.findByText('Al6063-T5 Bilinear')).toBeInTheDocument()
  })

  it('고칠 권한이 없는 재료는 단추가 잠긴다', async () => {
    show()
    expect(
      await screen.findByRole('button', { name: 'SUS304_-_1.0 을 SUS304_annealed Bilinear 에 연결' })
    ).toBeDisabled()
  })

  it('후보가 있는 재료가 없으면 이름으로 찾는 길을 알린다', async () => {
    linkCandidateList.mockResolvedValue({ unlinked: 4, with_candidates: 0, items: [] })
    show()
    expect(await screen.findByText(/후보가 있는 재료가 없습니다/)).toBeInTheDocument()
  })
})
