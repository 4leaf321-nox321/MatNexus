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

const account: { admin: boolean; role: string } = { admin: false, role: 'member' }
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      is_system_admin: account.admin,
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
  documents.mockResolvedValue([DOC])
  section.mockResolvedValue(SECTION)
  submit.mockResolvedValue({ id: 'r1', status: 'pending' })
  search.mockResolvedValue([])
  history.mockResolvedValue([])
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
    await user.click(screen.getByRole('button', { name: '초안 보내기' }))
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith('s1', expect.objectContaining({ note: '오타', publish: false }))
    )
    expect(await screen.findByText(/초안으로 보냈습니다/)).toBeInTheDocument()
  })

  it('검토자는 바로 반영한다', async () => {
    account.role = 'manager'
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
