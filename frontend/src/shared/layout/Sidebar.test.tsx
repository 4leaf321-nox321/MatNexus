/**
 * 사이드바 머리글의 버전.
 *
 * **서버가 정본이다.** 번들에 박으면 그것은 *빌드된* 버전이지 *지금 도는* 서버가
 * 아니다 — 배포가 반쯤 끝났거나 서비스가 안 내려갔다 올라온 상태에서 둘이 갈리고,
 * 그때 화면이 거짓말을 한다. 답이 틀린 것은 못 답하는 것보다 나쁘다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Sidebar } from '@/shared/layout/Sidebar'

const health = vi.fn()

vi.mock('@/shared/api/system', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/system')>()),
  systemApi: { health: () => health() },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: false, memberships: [] } }),
}))

function sidebar() {
  render(
    <MemoryRouter>
      <Sidebar collapsed={false} workspaceSlug="ws" />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  health.mockResolvedValue({ status: 'ok', version: 'v1.73.0' })
})

describe('사이드바 머리글', () => {
  it('서버가 준 버전을 보인다', async () => {
    sidebar()
    expect(await screen.findByText('v1.73.0')).toBeInTheDocument()
    expect(screen.getByText('MatNexus')).toBeInTheDocument()
  })

  it('못 찾았으면 안 적는다', async () => {
    // **`unknown` 을 그대로 띄우면 버전 자리가 고장난 것처럼 보인다.** 실제로는
    // 개발 경로에서 돈다는 뜻이다.
    health.mockResolvedValue({ status: 'ok', version: 'unknown' })
    sidebar()
    await waitFor(() => expect(health).toHaveBeenCalled())
    expect(screen.queryByText('unknown')).not.toBeInTheDocument()
  })

  it('서버가 안 답해도 머리글은 뜬다', async () => {
    // 버전 하나 때문에 사이드바가 통째로 비면 안 된다.
    health.mockRejectedValue(new Error('끊김'))
    sidebar()
    expect(await screen.findByText('MatNexus')).toBeInTheDocument()
  })
})
