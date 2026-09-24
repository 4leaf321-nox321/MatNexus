/**
 * 공지 한 건 — **읽고, 관리자는 여기서 고치고 지운다**(2026-09-24).
 *
 *   본문의 `**굵게**` · `` `코드` `` 는 그려서 — 별표가 글자로 보이지 않는다
 *   열면 읽음으로 남긴다 — 이미 읽은 것은 다시 안 찍는다
 *   지우는 단추는 관리자에게만, 지우면 목록으로
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NoticeDetailPage from '@/modules/notices/NoticeDetailPage'

const get = vi.fn()
const read = vi.fn()
const remove = vi.fn()
let admin = false

vi.mock('@/modules/notices/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/notices/api')>()),
  noticesApi: {
    get: (...args: unknown[]) => get(...args),
    read: (...args: unknown[]) => read(...args),
    remove: (...args: unknown[]) => remove(...args),
    update: vi.fn(),
    create: vi.fn(),
  },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: admin, memberships: [] } }),
  useMaybeAuth: () => ({ user: { is_system_admin: admin, memberships: [] } }),
}))

function notice(over: Record<string, unknown> = {}) {
  return {
    id: 'n1',
    title: '연동 안내',
    body: '**연동이 바뀐다** — `units=si` 를 붙이세요.',
    is_published: true,
    is_popup: false,
    created_at: '2026-09-20T00:00:00Z',
    published_at: '2026-09-20T00:00:00Z',
    is_read: true,
    created_by: '시스템 관리자',
    from_release: false,
    ...over,
  }
}

function show() {
  render(
    <MemoryRouter initialEntries={['/notices/n1']}>
      <Routes>
        <Route path="/notices/:id" element={<NoticeDetailPage />} />
        <Route path="/notices" element={<p>목록으로 왔다</p>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  admin = false
  read.mockResolvedValue(undefined)
  remove.mockResolvedValue(undefined)
})

describe('공지 한 건', () => {
  it('본문의 굵게·코드를 그려서 보이고, 쓴 사람을 적는다', async () => {
    get.mockResolvedValue(notice())
    show()
    const bold = await screen.findByText('연동이 바뀐다')
    expect(bold.tagName).toBe('STRONG')
    expect(screen.getByText('units=si').tagName).toBe('CODE')
    expect(screen.queryByText(/\*\*/)).toBeNull()
    expect(screen.getByText(/시스템 관리자/)).toBeInTheDocument()
  })

  it('안 읽은 공지는 열면 읽음으로 남긴다', async () => {
    get.mockResolvedValue(notice({ is_read: false }))
    show()
    await screen.findByRole('heading', { name: '연동 안내' })
    await waitFor(() => expect(read).toHaveBeenCalledWith('n1'))
  })

  it('이미 읽은 것은 다시 안 찍는다', async () => {
    get.mockResolvedValue(notice({ is_read: true }))
    show()
    await screen.findByRole('heading', { name: '연동 안내' })
    expect(read).not.toHaveBeenCalled()
  })

  it('남에게는 지우는 단추가 없다', async () => {
    get.mockResolvedValue(notice())
    show()
    await screen.findByRole('heading', { name: '연동 안내' })
    expect(screen.queryByRole('button', { name: /삭제/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /편집/ })).toBeNull()
  })

  it('관리자가 지우면 묻고 나서 지우고 목록으로 간다', async () => {
    admin = true
    const user = userEvent.setup()
    get.mockResolvedValue(notice())
    show()
    await screen.findByRole('heading', { name: '연동 안내' })
    await user.click(screen.getByRole('button', { name: /삭제/ }))
    // 확인 창이 떴고 아직 안 지웠다.
    expect(remove).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('button', { name: '삭제' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith('n1'))
    expect(await screen.findByText('목록으로 왔다')).toBeInTheDocument()
  })
})
