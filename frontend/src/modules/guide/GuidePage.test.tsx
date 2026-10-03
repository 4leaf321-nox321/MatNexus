/**
 * 핸드북 화면 — **검토자가 아니면 초안이고, 화면이 그것을 말한다.**
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import GuidePage, { headingsOf } from '@/modules/guide/GuidePage'

const documents = vi.fn()
const section = vi.fn()
const submit = vi.fn()
const search = vi.fn()
const history = vi.fn()
const coverage = vi.fn()

vi.mock('@/modules/metrology/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/metrology/api')>()),
  metrologyApi: { coverage: (...a: unknown[]) => coverage(...a) },
}))

vi.mock('@/modules/guide/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/guide/api')>('@/modules/guide/api')
  return {
    ...actual,
    guideApi: {
      documents: (...a: unknown[]) => documents(...a),
      section: (...a: unknown[]) => section(...a),
      submit: (...a: unknown[]) => submit(...a),
      search: (...a: unknown[]) => search(...a),
      history: (...a: unknown[]) => history(...a),
      approve: vi.fn(),
      reject: vi.fn(),
    },
  }
})

// 편집기는 무겁고 jsdom 에서 레이아웃을 못 잰다. 내용을 글자로 뱉는 스텁으로 대신한다.
vi.mock('@/modules/guide/GuideEditor', () => ({
  GuideEditor: ({ content, editable }: { content: { content?: unknown[] }; editable?: boolean }) => (
    <div data-testid={editable ? 'editor' : 'viewer'}>{JSON.stringify(content.content ?? [])}</div>
  ),
}))

const account: { admin: boolean; role: string; steward?: boolean } = {
  admin: false,
  role: 'member',
}
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      is_system_admin: account.admin,
      // **검토자는 자료 관리자다**(ADR 0035 3단계 — 전에는 부서 관리자 이상).
      is_data_manager: account.steward ?? false,
      memberships: [{ slug: 'metal', role: account.role }],
    },
  }),
}))

const BODY = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: '시간-온도 중첩' }] },
    { type: 'paragraph', content: [{ type: 'text', text: '시프트 인자' }] },
  ],
}

const SECTION = {
  id: 's1',
  key: 'master-curve',
  title: '마스터커브',
  position: 1,
  revision_no: 1,
  pending_count: 0,
  updated_at: '2026-08-28T01:00:00Z',
  document_id: 'd1',
  document_key: 'dma-prony',
  document_title: 'DMA 에서 Prony 카드까지',
  body: BODY,
  updated_by: { id: 'u9', name: '박용진' },
}

const DOC = {
  id: 'd1',
  key: 'dma-prony',
  title: 'DMA 에서 Prony 카드까지',
  kind: 'calculation',
  topic: 'dma',
  summary: null,
  position: 0,
  source_filename: null,
  updated_at: '2026-08-28T01:00:00Z',
  sections: [
    { id: 's1', key: 'master-curve', title: '마스터커브', position: 1, revision_no: 1, pending_count: 0, updated_at: '2026-08-28T01:00:00Z' },
    { id: 's2', key: 'prony', title: 'Prony 시리즈', position: 2, revision_no: 1, pending_count: 0, updated_at: '2026-08-28T01:00:00Z' },
  ],
}

/** 측정법이 아는 물성 — 하나는 잴 장비가 있고 하나는 없다. */
const STORAGE = {
  property_key: 'rheological.storage_modulus',
  name: '저장 탄성률',
  domain: 'rheological',
  symbol: "E'",
  si_unit: 'Pa',
  technique_count: 1,
  instrument_count: 2,
  owned_instrument_count: 1,
  value_count: 40,
}
const LOSS_TANGENT = { ...STORAGE, property_key: 'rheological.tan_delta', name: '손실 탄젠트', instrument_count: 0 }

function mount(path = '/guide') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/guide" element={<GuidePage />} />
        <Route path="/guide/:documentKey/:sectionKey" element={<GuidePage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  account.admin = false
  account.role = 'member'
  account.steward = false
  documents.mockResolvedValue([DOC])
  section.mockResolvedValue(SECTION)
  submit.mockResolvedValue({ id: 'r1', status: 'pending' })
  search.mockResolvedValue([])
  history.mockResolvedValue([])
  coverage.mockResolvedValue({ covered: [STORAGE], gaps: [LOSS_TANGENT] })
})

describe('첫 화면', () => {
  it('종류별 입구에 문서가 선다', async () => {
    mount()
    expect(await screen.findByRole('heading', { name: '물성 핸드북' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '물성 계산' })).toBeInTheDocument()
    expect(screen.getAllByText('DMA 에서 Prony 카드까지').length).toBeGreaterThan(0)
  })
})

describe('절', () => {
  it('본문과 절 안 목차, 다음 절을 보여 준다', async () => {
    mount('/guide/dma-prony/master-curve')
    expect(await screen.findByRole('heading', { name: '마스터커브' })).toBeInTheDocument()
    expect(screen.getByTestId('viewer')).toHaveTextContent('시프트 인자')
    expect(screen.getByText('시간-온도 중첩')).toBeInTheDocument()
    expect(screen.getByText('Prony 시리즈 →')).toBeInTheDocument()
  })

  it('구성원의 저장은 초안이고, 화면이 그렇게 말한다', async () => {
    const user = userEvent.setup()
    mount('/guide/dma-prony/master-curve')
    await user.click(await screen.findByRole('button', { name: '편집' }))
    expect(screen.getByTestId('editor')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '저장 (바로 반영)' })).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('고친 이유'), '오타')
    await user.click(screen.getByRole('button', { name: '초안 전송' }))
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith('s1', expect.objectContaining({ note: '오타', publish: false }))
    )
    expect(await screen.findByText(/초안으로 보냈습니다/)).toBeInTheDocument()
  })

  it('검토자는 바로 반영한다', async () => {
    account.steward = true
    submit.mockResolvedValue({ id: 'r1', status: 'approved' })
    const user = userEvent.setup()
    mount('/guide/dma-prony/master-curve')
    await user.click(await screen.findByRole('button', { name: '편집' }))
    await user.click(screen.getByRole('button', { name: '저장 (바로 반영)' }))
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith('s1', expect.objectContaining({ publish: true }))
    )
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument()
  })
})

describe('찾기', () => {
  it('두 글자부터 서버에 묻고, 맞은 자리를 보여 준다', async () => {
    search.mockResolvedValue([
      {
        section_id: 's1',
        document_key: 'dma-prony',
        document_title: 'DMA 에서 Prony 카드까지',
        kind: 'calculation',
        topic: 'dma',
        section_key: 'master-curve',
        section_title: '마스터커브',
        snippet: '…시프트 인자를 온도마다…',
      },
    ])
    const user = userEvent.setup()
    mount()
    await user.type(await screen.findByLabelText('핸드북에서 찾기'), '시프트')
    expect(await screen.findByText('…시프트 인자를 온도마다…')).toBeInTheDocument()
    expect(search).toHaveBeenCalledWith('시프트')
  })
})

it('절 안 목차는 제목만 뽑는다', () => {
  expect(headingsOf(BODY)).toEqual([{ level: 2, text: '시간-온도 중첩' }])
})

describe('측정법과 잇는다 (2026-10-03)', () => {
  const MENTIONS = {
    type: 'doc',
    content: [
      { type: 'paragraph', content: [{ type: 'text', text: '손실 탄젠트 봉우리와 저장 탄성률을 함께 본다.' }] },
    ],
  }

  it('절에 나온 물성을 나온 차례로 세우고, 측정법으로 보낸다 — 장비가 없으면 그렇다고', async () => {
    section.mockResolvedValue({ ...SECTION, body: MENTIONS })
    mount('/guide/dma-prony/master-curve')
    const storage = await screen.findByRole('link', { name: '저장 탄성률' })
    expect(storage).toHaveAttribute('href', '/metrology?key=rheological.storage_modulus')
    const loss = screen.getByRole('link', { name: '손실 탄젠트' })
    // 처음 나온 것이 위 — 절이 다루는 순서다.
    expect(loss.compareDocumentPosition(storage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(loss.closest('li')).toHaveTextContent('장비 없음')
  })

  it('앱 사용 문서에는 세우지 않는다 — 거기 나온 물성 이름은 재는 법이 아니다', async () => {
    documents.mockResolvedValue([{ ...DOC, kind: 'platform' }])
    section.mockResolvedValue({ ...SECTION, body: MENTIONS })
    mount('/guide/dma-prony/master-curve')
    expect(await screen.findByRole('heading', { name: '마스터커브' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '저장 탄성률' })).not.toBeInTheDocument()
  })

  it('측정법이 `?q=` 로 보내면 그 말로 찾은 채 열린다', async () => {
    search.mockResolvedValue([
      {
        section_id: 's1',
        document_key: 'dma-prony',
        document_title: 'DMA 에서 Prony 카드까지',
        kind: 'calculation',
        topic: 'dma',
        section_key: 'master-curve',
        section_title: '마스터커브',
        snippet: '… ISO 6721 …',
      },
    ])
    mount('/guide?q=ISO%206721')
    expect(screen.getByRole('textbox', { name: '핸드북에서 찾기' })).toHaveValue('ISO 6721')
    expect(await screen.findByText('… ISO 6721 …')).toBeInTheDocument()
    expect(search).toHaveBeenCalledWith('ISO 6721')
  })
})
