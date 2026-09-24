/**
 * BOM 혼합 덱 화면.
 *
 *   기억된 매칭이 자동으로 앉고, 사내 재료를 고르면 확정 카드가 따라온다
 *   빌드 페이로드 — 카드가 있으면 card_id(문헌은 비움), 없으면 문헌으로
 *   빌드 뒤 매칭 기억과 문헌 연결(둘 다 고른 줄)이 저장된다
 *   엑셀 다열은 열 매핑을 물어본다
 *   단위계는 고른 키를 그대로 싣는다 — 비우면 서버 기본(mm·N·tonne)이 된다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BomDeckPage from '@/modules/fitting/BomDeckPage'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()

vi.mock('@/shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    put: (...args: unknown[]) => put(...args),
  },
}))

const MATERIAL_ID = '11111111-1111-1111-1111-111111111111'
const CARD_ID = '22222222-2222-2222-2222-222222222222'
const CATALOG_ID = '33333333-3333-3333-3333-333333333333'

function mockApis({
  remembered = [null, null],
  cards = [{ id: CARD_ID, label: '대표 TD' }],
}: {
  remembered?: unknown[]
  cards?: unknown[]
} = {}) {
  get.mockImplementation((url: unknown) => {
    const path = String(url)
    // 기본이 첫째가 아니다 — 순서로 고르면 통과해 버린다.
    if (path.startsWith('/fitting/unit-systems'))
      return Promise.resolve([
        { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
        { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
      ])
    if (path.startsWith('/fitting/formats'))
      return Promise.resolve([
        { key: 'abaqus', label: 'Abaqus', extension: 'inp', describe: '', requires: [] },
        { key: 'json', label: 'JSON', extension: 'json', describe: '', requires: [] },
      ])
    if (path.startsWith('/fitting/cards'))
      return Promise.resolve({ total: cards.length, limit: 1, offset: 0, items: cards })
    if (path.startsWith('/materials/'))
      return Promise.resolve({ id: MATERIAL_ID, code: 'M-000001', record_name: 'SGARC440_-_1.2' })
    if (path.startsWith('/materials'))
      return Promise.resolve({
        total: 1,
        limit: 5,
        offset: 0,
        items: [{ id: MATERIAL_ID, code: 'M-000001', record_name: 'SGARC440_-_1.2' }],
      })
    throw new Error(`뜻밖의 GET: ${path}`)
  })
  post.mockImplementation((url: unknown) => {
    const path = String(url)
    if (path.startsWith('/workbench/bom-aliases/lookup'))
      return Promise.resolve({ found: remembered })
    if (path.startsWith('/catalog/deck/match'))
      return Promise.resolve([
        {
          query: 'SGARC440',
          mid: 1,
          candidates: [
            { id: CATALOG_ID, name: 'SGARC440 steel', category: 'metal', value_count: 7, score: 2 },
          ],
        },
        { query: 'SUS304', mid: 2, candidates: [] },
      ])
    if (path.startsWith('/fitting/decks/bom'))
      return Promise.resolve({
        text: '*KEYWORD\n*END\n',
        filename: 'bom_deck_si.k',
        format_family: 'dyna',
        skipped: [],
        notes: [],
        card_count: 1,
        literature_count: 0,
        synthetic_count: 0,
      })
    throw new Error(`뜻밖의 POST: ${path}`)
  })
  put.mockResolvedValue({})
}

async function pasteAndMatch(user: ReturnType<typeof userEvent.setup>) {
  render(
    <MemoryRouter>
      <BomDeckPage />
    </MemoryRouter>
  )
  await user.click(screen.getByPlaceholderText(/SUS304/))
  await user.paste('1, SGARC440\n2, SUS304')
  await user.click(screen.getByRole('button', { name: '매칭' }))
  await screen.findByText(/매칭 확인/)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApis()
})

describe('BOM 혼합 덱', () => {
  it('기억된 사내 매칭이 자동으로 앉고 확정 카드가 따라온다', async () => {
    mockApis({ remembered: [{ query: 'SGARC440', material_id: MATERIAL_ID }, null] })
    const user = userEvent.setup()
    await pasteAndMatch(user)
    expect(await screen.findByText('SGARC440_-_1.2')).toBeInTheDocument()
    expect(screen.getByText(/카드: 대표 TD/)).toBeInTheDocument()
    expect(screen.getByText('(기억)')).toBeInTheDocument()
    expect(screen.getByText('사내 카드 (곡선)')).toBeInTheDocument()
  })

  it('빌드 — 카드 줄은 card_id 로(문헌은 비움), 기억·연결이 저장된다', async () => {
    mockApis({ remembered: [{ query: 'SGARC440', material_id: MATERIAL_ID }, null] })
    const user = userEvent.setup()
    await pasteAndMatch(user)
    await screen.findByText('SGARC440_-_1.2')

    // SGARC440 줄에 문헌 재료도 고른다 — 연결이 함께 걸려야 한다.
    const pickers = screen.getAllByRole('combobox')
    await user.selectOptions(pickers[0], CATALOG_ID)

    await user.click(screen.getByRole('button', { name: '덱 생성' }))
    await waitFor(() => expect(screen.getByText('bom_deck_si.k')).toBeInTheDocument())

    const [, body] = post.mock.calls.find(([url]) => String(url) === '/fitting/decks/bom') as [
      string,
      { rows: Array<Record<string, unknown>>; units: unknown; format: unknown },
    ]
    expect(body.rows[0]).toMatchObject({ mid: 1, card_id: CARD_ID, catalog_material_id: null })
    // 안 고르면 서버가 기본이라 한 계 — 키를 적어 보낸다(ADR 0036).
    expect(body.units).toBe('mm_n_tonne')
    // 솔버를 안 고르면 서버 기본(LS-DYNA 자동) — null 로 간다.
    expect(body.format).toBeNull()

    // 매칭 기억 + 문헌 연결.
    const putUrls = put.mock.calls.map(([url]) => String(url))
    expect(putUrls).toContain('/workbench/bom-aliases')
    expect(putUrls).toContain(`/catalog/links/${MATERIAL_ID}`)
  })

  it('SI 를 고르면 si 가 실린다 — 비워 보내면 mm·N·tonne 이 된다', async () => {
    // 전에는 「SI 면 비워 보낸다」 였다. 서버 기본이 mm·N·tonne 으로 바뀐 뒤로 그 빈칸은
    // mm 덱이 되어, SI 를 고른 사람이 오류 없이 1000배 다른 덱을 받을 뻔했다(2026-09-24).
    mockApis({ remembered: [{ query: 'SGARC440', material_id: MATERIAL_ID }, null] })
    const user = userEvent.setup()
    await pasteAndMatch(user)
    await screen.findByText('SGARC440_-_1.2')

    await user.selectOptions(await screen.findByDisplayValue('mm · N · tonne (MPa)'), 'si')
    await user.click(screen.getByRole('button', { name: '덱 생성' }))
    await waitFor(() => expect(screen.getByText('bom_deck_si.k')).toBeInTheDocument())

    const [, body] = post.mock.calls.find(([url]) => String(url) === '/fitting/decks/bom') as [
      string,
      { units: unknown },
    ]
    expect(body.units).toBe('si')
  })

  it('확정 카드가 없는 재료는 문헌 스칼라로 메꾼다', async () => {
    mockApis({ cards: [] })
    const user = userEvent.setup()
    await pasteAndMatch(user)

    // 사내 검색으로 골라도 카드가 없다 — 문헌을 고르면 문헌 스칼라.
    const pickers = screen.getAllByRole('combobox')
    await user.selectOptions(pickers[0], CATALOG_ID)
    expect(screen.getByText('문헌 스칼라')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '덱 생성' }))
    await waitFor(() =>
      expect(post.mock.calls.some(([url]) => String(url) === '/fitting/decks/bom')).toBe(true)
    )
    const [, body] = post.mock.calls.find(([url]) => String(url) === '/fitting/decks/bom') as [
      string,
      { rows: Array<Record<string, unknown>> },
    ]
    expect(body.rows[0]).toMatchObject({
      mid: 1,
      card_id: null,
      catalog_material_id: CATALOG_ID,
    })
  })

  it('곡선 합성을 켜면 표지가 서고 payload 에 실린다', async () => {
    mockApis({ cards: [] })
    const user = userEvent.setup()
    await pasteAndMatch(user)

    const pickers = screen.getAllByRole('combobox')
    await user.selectOptions(pickers[0], CATALOG_ID)
    // 문헌만 매칭된 줄에만 합성 스위치가 있다 — 사내 카드가 있으면 실측이 이긴다.
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByText('문헌 합성 곡선')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '덱 생성' }))
    await waitFor(() =>
      expect(post.mock.calls.some(([url]) => String(url) === '/fitting/decks/bom')).toBe(true)
    )
    const [, body] = post.mock.calls.find(([url]) => String(url) === '/fitting/decks/bom') as [
      string,
      { rows: Array<Record<string, unknown>> },
    ]
    expect(body.rows[0]).toMatchObject({ catalog_material_id: CATALOG_ID, synthesize: true })
  })

  it('엑셀 다열이면 열 매핑을 물어본다', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <BomDeckPage />
      </MemoryRouter>
    )
    await user.click(screen.getByPlaceholderText(/SUS304/))
    await user.paste('1\t도어 이너\tSGARC440\n2\t힌지\tSUS304')
    expect(await screen.findByText(/열 3개를 봤습니다/)).toBeInTheDocument()
    expect(screen.getByText('MID 열')).toBeInTheDocument()
    expect(screen.getByText('재료명 열')).toBeInTheDocument()
  })
})
