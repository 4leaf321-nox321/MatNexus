/**
 * 계정 관리 — **삭제된 계정은 「삭제됨」 탭에서만, 단추 없이.**
 *
 * 삭제가 소프트라(`deleted_at` + `suspended`) 전에는 「정지」 로 섞여 나왔고, 그 줄의
 * 「활성화」 가 지운 계정을 되살렸다(2026-09-18).
 */

import { render, screen, waitFor } from '@testing-library/react'
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

beforeEach(() => {
  vi.clearAllMocks()
  list.mockImplementation((status?: string) =>
    Promise.resolve(
      status === 'deleted'
        ? [
            account({
              email: 'hong@samsung.com#deleted-20260918T030000Z',
              deleted_at: '2026-09-18T03:00:00Z',
            }),
          ]
        : status === 'pending'
          ? []
          : [account({ id: 'u2', email: 'park@samsung.com', display_name: '박연구' })]
    )
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
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('deleted'))
    expect(await screen.findByText('hong@samsung.com')).toBeInTheDocument()
    expect(screen.getAllByText('삭제됨')).toHaveLength(2) // 탭 + 배지
    expect(screen.getByText(/되살릴 수 없습니다/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '활성화' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '계정 삭제' })).not.toBeInTheDocument()
  })
})
