/**
 * 계정 관리 — **삭제된 계정은 「삭제됨」 탭에서만, 단추 없이.**
 *
 * 삭제가 소프트라(`deleted_at` + `suspended`) 전에는 「정지」 로 섞여 나왔고, 그 줄의
 * 「활성화」 가 지운 계정을 되살렸다(2026-09-18).
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountsAdminPage from '@/modules/accounts/AccountsAdminPage'

const list = vi.fn()

vi.mock('@/modules/accounts/api', () => ({
  accountsApi: {
    list: (...args: unknown[]) => list(...args),
    summary: () => Promise.resolve({ active_system_admins: 2 }),
  },
}))
vi.mock('@/modules/workspaces/api', () => ({
  workspacesApi: { options: () => Promise.resolve([{ slug: 'metal', name: '금속재료팀' }]) },
}))
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'me', is_system_admin: true, memberships: [] } }),
}))

function account(overrides: Record<string, unknown>) {
  return {
    id: 'u1',
    email: 'hong@samsung.com',
    display_name: '홍길동',
    status: 'suspended',
    is_system_admin: false,
    must_change_password: false,
    home_workspace_slug: null,
    requested_workspace_slug: null,
    memberships: [],
    created_at: '2026-09-01T00:00:00Z',
    decided_at: null,
    decision_note: null,
    deleted_at: null,
    ...overrides,
  }
}

/** 서버의 쪽 모양 — `fetchAll` 이 `total` 을 보고 이어 받는다. */
function page(items: unknown[], limit = 200, offset = 0, total = items.length) {
  return { items: items.slice(offset, offset + limit), total, limit, offset }
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockImplementation((status?: string, limit?: number, offset?: number) =>
    Promise.resolve(page(
      status === 'deleted'
        ? [
            account({
              email: 'hong@samsung.com#deleted-20260918T030000Z',
              deleted_at: '2026-09-18T03:00:00Z',
            }),
          ]
        : status === 'pending'
          ? []
          : [account({ id: 'u2', email: 'park@samsung.com', display_name: '박연구' })],
      limit,
      offset
    ))
  )
})

describe('삭제된 계정', () => {
  it('「삭제됨」 탭에서만 보이고, 원래 아이디와 삭제 날짜가 보이며, 단추가 없다', async () => {
    render(
      <MemoryRouter>
        <AccountsAdminPage />
      </MemoryRouter>
    )
    await userEvent.click(await screen.findByRole('tab', { name: '전체' }))
    expect(await screen.findByText('park@samsung.com')).toBeInTheDocument()
    // 「전체」 는 삭제된 계정을 안 묻는다 — 정지와 섞이지 않는다.
    expect(screen.queryByText(/hong/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '활성화' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '삭제됨' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('deleted', 200, 0))
    expect(await screen.findByText('hong@samsung.com')).toBeInTheDocument()
    expect(screen.getAllByText('삭제됨')).toHaveLength(2) // 탭 + 배지
    expect(screen.getByText(/되살릴 수 없습니다/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '활성화' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '계정 삭제' })).not.toBeInTheDocument()
  })
})

describe('사용자가 많을 때', () => {
  const many = Array.from({ length: 230 }, (_, at) =>
    account({
      id: `m${at}`,
      email: `many${String(at).padStart(3, '0')}@samsung.com`,
      display_name: `사람 ${at}`,
      status: 'active',
    })
  )

  it('쪽을 이어 받아 목록 끝까지 보이고, 몇 명인지 말한다', async () => {
    list.mockImplementation((status?: string, limit = 200, offset = 0) =>
      Promise.resolve(page(status ? [] : many, limit, offset))
    )
    render(
      <MemoryRouter>
        <AccountsAdminPage />
      </MemoryRouter>
    )
    await userEvent.click(await screen.findByRole('tab', { name: '전체' }))
    // 데이터로 그려진 것을 기다린다 — 마지막 쪽의 마지막 사람이 보일 때다. 전에는 50명에서 멈췄다.
    expect(await screen.findByText('many229@samsung.com')).toBeInTheDocument()
    expect(list).toHaveBeenCalledWith(undefined, 200, 0)
    expect(list).toHaveBeenCalledWith(undefined, 200, 200)
    expect(screen.getByRole('status')).toHaveTextContent('230명')
    expect(screen.getByRole('status')).not.toHaveTextContent('일부')
  })

  it('서버가 더 주지 않아 멈추면 전체 중 몇 명만인지 말한다', async () => {
    list.mockImplementation((status?: string, limit = 200, offset = 0) =>
      Promise.resolve(page(status ? [] : many.slice(0, 3), limit, offset, status ? 0 : 2500))
    )
    render(
      <MemoryRouter>
        <AccountsAdminPage />
      </MemoryRouter>
    )
    await userEvent.click(await screen.findByRole('tab', { name: '전체' }))
    expect(await screen.findByText('many002@samsung.com')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('전체 2,500명 중 앞의 3명만 표시합니다')
  })
})

describe('메일 주소 복사', () => {
  const people = ['hong', 'kim', 'lee', 'park'].map((name, at) =>
    account({
      id: `p${at}`,
      email: `${name}@samsung.com`,
      display_name: name,
      status: 'active',
    })
  )

  async function showAll() {
    list.mockImplementation((status?: string, limit = 200, offset = 0) =>
      Promise.resolve(page(status === 'deleted' ? people.slice(0, 1) : status ? [] : people, limit, offset))
    )
    render(
      <MemoryRouter>
        <AccountsAdminPage />
      </MemoryRouter>
    )
    await userEvent.click(await screen.findByRole('tab', { name: '전체' }))
    await screen.findByText('park@samsung.com')
  }

  it('Shift 로 범위를 골라 고른 사람의 주소만 한 줄로 연다', async () => {
    const user = userEvent.setup()
    await showAll()
    expect(screen.queryByRole('button', { name: /메일 주소 복사/ })).toBeNull()

    await user.click(screen.getByLabelText('kim 고르기'))
    await user.keyboard('{Shift>}')
    await user.click(screen.getByLabelText('park 고르기'))
    await user.keyboard('{/Shift}')
    await user.click(screen.getByRole('button', { name: '메일 주소 복사 (3명)' }))

    const dialog = await screen.findByRole('dialog')
    expect((within(dialog).getByLabelText('메일 주소') as HTMLTextAreaElement).value).toBe(
      'kim@samsung.com; lee@samsung.com; park@samsung.com'
    )
  })

  it('전부 고르기는 이 목록 전부, 탭을 바꾸면 고른 것이 풀린다', async () => {
    const user = userEvent.setup()
    await showAll()
    await user.click(screen.getByLabelText('이 목록 전부 고르기'))
    expect(screen.getByRole('button', { name: '메일 주소 복사 (4명)' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: '승인 대기' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('pending', 200, 0))
    expect(screen.queryByRole('button', { name: /메일 주소 복사/ })).toBeNull()
  })

  it('삭제됨 탭에는 고르는 칸이 없다 — 지운 계정에는 메일이 안 간다', async () => {
    const user = userEvent.setup()
    await showAll()
    await user.click(screen.getByRole('tab', { name: '삭제됨' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('deleted', 200, 0))
    await screen.findByText('hong@samsung.com')
    expect(screen.queryByLabelText('이 목록 전부 고르기')).toBeNull()
    expect(screen.queryByLabelText('hong 고르기')).toBeNull()
  })
})
