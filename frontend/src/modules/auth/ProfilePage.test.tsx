/**
 * 내 정보 화면 — 팝업에서 옮겨 온 것이 그대로 동작하는가.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProfilePage from '@/modules/auth/ProfilePage'

const patchApi = vi.fn()
const reload = vi.fn()

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client')
  return { ...actual, api: { ...actual.api, patch: (...args: unknown[]) => patchApi(...args) } }
})

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'yj', display_name: '박용진', is_system_admin: false, memberships: [] },
    reload: (...args: unknown[]) => reload(...args),
    logout: vi.fn(),
  }),
}))

vi.mock('@/shared/components/AccessTokens', () => ({
  AccessTokens: () => <div>토큰 패널</div>,
}))

beforeEach(() => {
  vi.clearAllMocks()
  patchApi.mockResolvedValue({})
  reload.mockResolvedValue(undefined)
})

describe('ProfilePage', () => {
  it('아이디는 읽기 전용, 토큰 패널이 있다', () => {
    render(<ProfilePage />)
    expect(screen.getByLabelText('아이디')).toBeDisabled()
    expect(screen.getByText('토큰 패널')).toBeInTheDocument()
  })

  it('이름을 고치면 저장하고 상단 바를 새로 읽는다', async () => {
    const user = userEvent.setup()
    render(<ProfilePage />)
    const input = screen.getByLabelText('표시 이름')
    await user.clear(input)
    await user.type(input, '박용진 (금속)')
    await user.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() =>
      expect(patchApi).toHaveBeenCalledWith('/auth/me', { display_name: '박용진 (금속)' })
    )
    expect(reload).toHaveBeenCalled()
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument()
  })

  it('이름이 그대로면 저장 단추가 꺼져 있다', () => {
    render(<ProfilePage />)
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
  })
})
