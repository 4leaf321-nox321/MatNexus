/**
 * 공지 게시판 — **VOC 와 같은 짜임**(2026-09-24).
 *
 *   번호는 게시판의 차례          가장 오래된 것이 1
 *   안 읽은 글이 보인다           굵게, 「새 글」 — 팝업은 중요한 것에만 켠다
 *   배포에 실려 온 안내           「알 수 없음」 이 아니라 「배포 안내」
 *   제목·내용으로 찾고, 안 읽은 것만 고른다
 *   쓰는 것은 시스템 관리자만
 *   「모두 읽음」 — 안 읽은 글이 있을 때만, 누르면 목록과 수를 다시 읽는다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NoticesPage from '@/modules/notices/NoticesPage'

const list = vi.fn()
const unreadCount = vi.fn()
const readAll = vi.fn()
let admin = false

vi.mock('@/modules/notices/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/notices/api')>()),
  noticesApi: {
    list: (...args: unknown[]) => list(...args),
    unreadCount: () => unreadCount(),
    readAll: () => readAll(),
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
    title: '공지',
    body: '본문',
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

function page(items: unknown[], total = items.length) {
  return { items, total, limit: 50, offset: 0 }
}

function show() {
  render(
    <MemoryRouter initialEntries={['/notices']}>
      <NoticesPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  admin = false
  unreadCount.mockResolvedValue({ unread: 0 })
  readAll.mockResolvedValue({ unread: 0 })
})

describe('공지 게시판', () => {
  it('번호는 차례, 안 읽은 글은 「새 글」, 배포에 실려 온 안내는 그렇게 적는다', async () => {
    list.mockResolvedValue(
      page([
        notice({ id: 'n3', title: '새 기능', is_read: false, created_by: null, from_release: true }),
        notice({ id: 'n2', title: '점검 안내' }),
        notice({ id: 'n1', title: '첫 공지' }),
      ])
    )
    show()
    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1)
    expect(rows.map((row) => within(row).getAllByRole('cell')[0].textContent)).toEqual([
      '3',
      '2',
      '1',
    ])
    expect(within(rows[0]).getByText('새 글')).toBeInTheDocument()
    expect(within(rows[0]).getByText('배포 안내')).toBeInTheDocument()
    expect(within(rows[1]).queryByText('새 글')).toBeNull()
    expect(within(rows[1]).getByText('시스템 관리자')).toBeInTheDocument()
  })

  it('제목·내용으로 찾고, 안 읽은 것만 고른다 — 걸러서 없으면 그렇게 말한다', async () => {
    const user = userEvent.setup()
    list.mockResolvedValue(page([]))
    show()
    await screen.findByText('공지가 없습니다.')

    await user.type(screen.getByLabelText('공지 찾기'), '점검{Enter}')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({ q: '점검', unread: false, limit: 50, offset: 0 })
    )
    await user.click(screen.getByRole('checkbox', { name: '안 읽은 것만' }))
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({ q: '점검', unread: true, limit: 50, offset: 0 })
    )
    expect(await screen.findByText('거른 조건에 맞는 공지가 없습니다.')).toBeInTheDocument()
  })

  it('쓰는 것은 시스템 관리자만', async () => {
    list.mockResolvedValue(page([notice()]))
    show()
    await screen.findByRole('table')
    expect(screen.queryByRole('button', { name: /공지 작성/ })).toBeNull()
  })

  it('관리자에게는 쓰는 단추가 선다', async () => {
    admin = true
    list.mockResolvedValue(page([notice()]))
    show()
    await screen.findByRole('table')
    expect(screen.getByRole('button', { name: /공지 작성/ })).toBeInTheDocument()
  })

  it('안 읽은 글이 있으면 「모두 읽음」 이 서고, 누르면 목록과 수를 다시 읽는다', async () => {
    const user = userEvent.setup()
    list.mockResolvedValue(page([notice({ id: 'n2', title: '새 기능', is_read: false })]))
    unreadCount.mockResolvedValueOnce({ unread: 7 })
    show()
    // 이 쪽에 한 건만 보여도 수는 전체다 — 목록은 쪽으로 잘려 있다.
    const button = await screen.findByRole('button', { name: /모두 읽음 \(7\)/ })

    list.mockResolvedValue(page([notice({ id: 'n2', title: '새 기능', is_read: true })]))
    await user.click(button)
    await waitFor(() => expect(readAll).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /모두 읽음/ })).not.toBeInTheDocument()
    )
    const row = within(await screen.findByRole('table')).getAllByRole('row')[1]
    await waitFor(() => expect(within(row).queryByText('새 글')).toBeNull())
    expect(list.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('다 읽었으면 「모두 읽음」 이 없다', async () => {
    list.mockResolvedValue(page([notice()]))
    show()
    await screen.findByRole('table')
    await waitFor(() => expect(unreadCount).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /모두 읽음/ })).toBeNull()
  })
})
