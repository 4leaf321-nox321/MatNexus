/**
 * 물성 카드 목록 — **재료를 거치지 않고 찾는다.**
 *
 * 여기서 지키는 것은 다섯이다.
 *
 *   거르기는 서버가 한다     앞 50장만 받아 화면에서 거르면 뒤엣것이 없어진다
 *   개수도 서버가 센다       한 페이지에서 세면 필터 옆 숫자가 거짓말을 한다
 *   잘렸으면 잘렸다고 한다   표시 없이 자르면 없는 카드를 없다고 믿는다
 *   시험 없는 카드를 짚는다  `· · 시편 0개` 는 "시험이 지워졌다" 로 읽힌다
 *   못 쓰게 된 카드를 짚는다 만든 계산이 코드에 없으면 내보내기가 막힌다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CardsPage from '@/modules/fitting/CardsPage'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const cards = vi.fn()
const cardFacets = vi.fn()
const formats = vi.fn()
const downloadBundle = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    cards: (...args: unknown[]) => cards(...args),
    cardFacets: () => cardFacets(),
    formats: () => formats(),
    downloadBundle: (...args: unknown[]) => downloadBundle(...args),
    // 내보내기 메뉴가 단위계 목록을 읽는다 — **화면이 적어 두지 않는다.**
    unitSystems: () =>
      Promise.resolve([
        { key: 'si', label: 'SI', declaration: 'kg, m, s, Pa', is_default: true },
      ]),
  },
}))

function card(overrides: Record<string, unknown> = {}) {
  return {
    id: 'c1',
    material_id: 'm1',
    material_name: 'SECC_MDOI_1.0',
    test_type_key: 'tensile',
    orientation: 'MD',
    label: '인장 MD',
    status: 'draft',
    source: { sample_count: 3 },
    blocks: {},
    available_formats: ['abaqus', 'json'],
    problem: null,
    point_count: 120,
    note: null,
    owner_workspace_name: '재료연구팀',
    is_global: false,
    published_at: null,
    created_at: '2026-08-25T00:00:00Z',
    ...overrides,
  }
}

const FACETS = {
  statuses: [
    { key: 'draft', label: '초안', count: 3 },
    { key: 'published', label: '확정', count: 1 },
  ],
  test_types: [
    { key: 'tensile', label: '인장시험', count: 3 },
    { key: 'none', label: '시험 없음', count: 1 },
  ],
  owners: [
    { key: 'global', label: '(전역)', count: 1 },
    { key: 'ws-1', label: '재료연구팀', count: 3 },
  ],
}

function page() {
  render(
    <MemoryRouter>
      <LeftPanelProvider>
        <LeftPanelHost />
        <CardsPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  cards.mockResolvedValue({ items: [card()], total: 1, limit: 50, offset: 0 })
  cardFacets.mockResolvedValue(FACETS)
  formats.mockResolvedValue([
    { key: 'abaqus', label: 'Abaqus', describe: '', requires: [], extension: 'inp' },
  ])
})

describe('물성 카드 목록', () => {
  it('어느 재료의 카드인지 보이고 거기로 간다', async () => {
    // **이 화면의 존재 이유다.** 재료를 알면 재료 상세로 가면 되고, 모를 때
    // 답할 데가 없었다.
    page()
    const link = await screen.findByRole('link', { name: 'SECC_MDOI_1.0' })
    expect(link).toHaveAttribute('href', '/materials/m1')
  })

  it('거르기를 서버에 넘긴다', async () => {
    // **앞 50장만 받아 화면에서 거르면 뒤엣것이 없는 카드가 된다.**
    page()
    await waitFor(() => expect(cards).toHaveBeenCalled())
    await userEvent.click(await screen.findByRole('button', { name: /확정/ }))
    await waitFor(() =>
      expect(cards).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'published' }))
    )
  })

  it('시험 없는 카드도 거를 수 있다', async () => {
    // **`null` 을 쿼리로 못 보낸다.** 이 축이 없으면 선언 물성 카드가 어느
    // 필터에도 안 걸려 목록에서 사라진다(ADR 0016).
    page()
    await userEvent.click(await screen.findByRole('button', { name: /시험 없음/ }))
    await waitFor(() =>
      expect(cards).toHaveBeenLastCalledWith(expect.objectContaining({ test_type_key: 'none' }))
    )
  })

  it('개수를 서버가 준 것으로 적는다', async () => {
    // **한 페이지에서 세면 「인장시험 1」이라고 적히는데 실제로는 3장이다.**
    cards.mockResolvedValue({ items: [card()], total: 3, limit: 50, offset: 0 })
    page()
    const button = await screen.findByRole('button', { name: /인장시험/ })
    expect(button).toHaveTextContent('3')
  })

  it('부서는 켜야 보인다', async () => {
    // 부서가 하나인 곳에서는 그 줄이 자리만 차지한다.
    page()
    await screen.findByRole('button', { name: /인장시험/ })
    expect(screen.queryByRole('button', { name: /재료연구팀/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '꺼짐' }))
    expect(await screen.findByRole('button', { name: /재료연구팀/ })).toBeInTheDocument()
  })

  it('부서를 끄면 걸어 둔 필터도 푼다', async () => {
    // **안 풀면 안 보이는 필터가 걸린 채로 남고**, 목록이 왜 짧은지 알 방법이 없다.
    page()
    await userEvent.click(await screen.findByRole('button', { name: '꺼짐' }))
    await userEvent.click(await screen.findByRole('button', { name: /재료연구팀/ }))
    await waitFor(() =>
      expect(cards).toHaveBeenLastCalledWith(expect.objectContaining({ owner: 'ws-1' }))
    )
    await userEvent.click(screen.getByRole('button', { name: '켜짐' }))
    await waitFor(() =>
      expect(cards).toHaveBeenLastCalledWith(expect.objectContaining({ owner: undefined }))
    )
  })

  it('잘렸으면 잘렸다고 적는다', async () => {
    // **표시 없이 자르면 없는 카드를 없다고 믿는다.**
    cards.mockResolvedValue({ items: [card()], total: 43, limit: 50, offset: 0 })
    page()
    expect(await screen.findByText(/43장 중 1장/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '더 보기' })).toBeInTheDocument()
  })

  it('다 보이면 더 보기를 안 띄운다', async () => {
    page()
    await screen.findByRole('link', { name: 'SECC_MDOI_1.0' })
    expect(screen.queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument()
  })

  it('시험 없는 카드를 다른 모양으로 그린다', async () => {
    // **`· · 시편 0개` 는 "시험이 지워졌다" 로 읽힌다.**
    cards.mockResolvedValue({
      items: [card({ test_type_key: null, orientation: null, source: {} })],
      total: 1,
      limit: 50,
      offset: 0,
    })
    page()
    expect(await screen.findByText('시험 없음 · 적어 둔 값')).toBeInTheDocument()
    expect(screen.queryByText(/시편 \?개/)).not.toBeInTheDocument()
  })

  it('못 쓰게 된 카드를 짚는다', async () => {
    // 만든 계산이 지금 코드에 없으면 내보내기가 막힌다 — 전역 목록이야말로
    // "그런 카드가 몇 장인가" 를 처음 물을 수 있는 자리다.
    cards.mockResolvedValue({
      items: [card({ problem: '모르는 물성 블록입니다: imaginary.' })],
      total: 1,
      limit: 50,
      offset: 0,
    })
    page()
    expect(await screen.findByText('풀 수 없음')).toBeInTheDocument()
  })

  it('검색은 타이핑이 멎으면 서버에 묻는다', async () => {
    // 글자마다 부르면 앞 글자의 응답이 뒤늦게 와서 목록을 덮는다.
    page()
    await waitFor(() => expect(cards).toHaveBeenCalled())
    await userEvent.type(screen.getByLabelText('카드 검색'), 'SECC')
    await waitFor(
      () => expect(cards).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'SECC' })),
      { timeout: 2000 }
    )
  })
})

describe('묶음 내보내기', () => {
  /**
   * **해석 하나에 재료가 여럿 들어간다.** 한 장씩 받아 사람이 폴더에 모으면 그
   * 묶음이 무엇이었는지가 아무 데도 안 남는다(ADR 0024 ②).
   */
  const two = () => {
    cards.mockResolvedValue({
      items: [card(), card({ id: 'c2', label: '둘째 카드' })],
      total: 2,
      limit: 50,
      offset: 0,
    })
  }

  it('고르기 전에는 띠가 안 뜬다', async () => {
    // 늘 떠 있으면 목록 아래가 항상 가려진다.
    two()
    page()
    await screen.findByText('둘째 카드')
    expect(screen.queryByLabelText('묶음 내보내기')).toBeNull()
  })

  it('고른 수를 말하고 형식을 고르면 그것으로 내보낸다', async () => {
    two()
    page()
    await userEvent.click(await screen.findByLabelText('인장 MD 묶음에 담기'))
    await userEvent.click(screen.getByLabelText('둘째 카드 묶음에 담기'))

    const bar = within(screen.getByLabelText('묶음 내보내기'))
    expect(bar.getByText('2장 골랐습니다')).toBeInTheDocument()

    await userEvent.click(bar.getByRole('button', { name: /Abaqus/ }))
    await waitFor(() => expect(downloadBundle).toHaveBeenCalled())
    const [ids, format, system] = downloadBundle.mock.calls[0]
    expect(new Set(ids as string[])).toEqual(new Set(['c1', 'c2']))
    expect((format as { key: string }).key).toBe('abaqus')
    // 화면이 'si' 를 적어 두지 않는다 — 서버가 기본이라고 말한 것을 쓴다.
    expect((system as { key: string }).key).toBe('si')
  })

  it('비우면 띠가 사라진다', async () => {
    two()
    page()
    await userEvent.click(await screen.findByLabelText('인장 MD 묶음에 담기'))
    const bar = within(screen.getByLabelText('묶음 내보내기'))
    await userEvent.click(bar.getByRole('button', { name: /고른 것 비우기/ }))
    expect(screen.queryByLabelText('묶음 내보내기')).toBeNull()
  })

  it('무엇이 함께 들어가는지 미리 말한다', async () => {
    // **압축을 풀고 나서 알면 늦다.** 검산할 수 있다는 사실이 고르는 자리에 있어야
    // 그것을 쓰는 사람이 생긴다.
    two()
    page()
    await userEvent.click(await screen.findByLabelText('인장 MD 묶음에 담기'))
    const bar = within(screen.getByLabelText('묶음 내보내기'))
    expect(bar.getByText(/manifest.json/)).toBeInTheDocument()
    expect(bar.getByText(/SHA256SUMS/)).toBeInTheDocument()
  })
})
