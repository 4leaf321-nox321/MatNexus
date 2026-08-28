/**
 * 액세스 토큰 패널 — **평문은 한 번, 폐기는 물어본다.**
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AccessTokens } from '@/shared/components/AccessTokens'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      get: (...args: unknown[]) => get(...args),
      post: (...args: unknown[]) => post(...args),
      delete: (...args: unknown[]) => del(...args),
    },
  }
})

const ALIVE = {
  id: 't1',
  name: '인장기-1',
  prefix: 'mnx_pat_abc',
  created_at: '2026-08-28T01:00:00Z',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  get.mockResolvedValue([
    ALIVE,
    { ...ALIVE, id: 't0', name: '옛것', revoked_at: '2026-08-01T00:00:00Z' },
  ])
  post.mockResolvedValue({ token: 'mnx_pat_PLAINTEXT', pat: { ...ALIVE, id: 't2', name: '새것' } })
  del.mockResolvedValue(undefined)
})

describe('AccessTokens', () => {
  it('폐기된 것은 목록에서 뺀다', async () => {
    render(<AccessTokens />)
    expect(await screen.findByText('인장기-1')).toBeInTheDocument()
    expect(screen.queryByText('옛것')).not.toBeInTheDocument()
  })

  it('발급하면 평문을 한 번 보여 준다', async () => {
    const user = userEvent.setup()
    render(<AccessTokens />)
    await screen.findByText('인장기-1')
    await user.type(screen.getByLabelText('토큰 이름'), '새것')
    await user.click(screen.getByRole('button', { name: '발급' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/auth/tokens', { name: '새것' }))
    expect(await screen.findByText('mnx_pat_PLAINTEXT')).toBeInTheDocument()
  })

  it('이름이 비면 발급 단추가 꺼져 있다', async () => {
    render(<AccessTokens />)
    await screen.findByText('인장기-1')
    expect(screen.getByRole('button', { name: '발급' })).toBeDisabled()
  })

  it('폐기는 물어보고, 아니오면 안 보낸다', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<AccessTokens />)
    await user.click(await screen.findByRole('button', { name: '폐기' }))
    expect(del).not.toHaveBeenCalled()

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: '폐기' }))
    await waitFor(() => expect(del).toHaveBeenCalledWith('/auth/tokens/t1'))
  })
})
