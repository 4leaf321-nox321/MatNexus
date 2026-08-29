/**
 * 시험종류 정의 — **볼 수 있게 열었으면 못 고치는 것도 보여야 한다.**
 *
 * 목록을 모두에게 연 뒤(서버는 원래 열려 있었다) 남는 위험은 하나다: 쓰기 단추가
 * 그대로 있으면 멤버가 누르고 **403 을 본다.** 사이드바에 「미구현」 배지를 단 것과
 * 같은 자리다 — 눌러 보고 알게 하지 않는다.
 *
 * 그래서 무는 자리를 「목록이 뜬다」 가 아니라 **「누구에게 어떤 단추가 있나」** 에
 * 둔다. 이쪽이 틀리면 화면은 멀쩡해 보이는데 누르는 사람만 막힌다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TestTypesPage from '@/modules/tests/TestTypesPage'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const list = vi.fn()
let memberships: { role: string }[] = []

vi.mock('@/modules/tests/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/tests/api')>('@/modules/tests/api')
  return { ...actual, testsApi: { types: () => list(), removeType: vi.fn() } }
})

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: false, memberships } }),
}))

const TYPE = {
  key: 'tensile',
  label: '인장',
  status: 'active',
  description: null,
  channels: [],
  conditions: [],
  run_count: 0,
  max_upload_bytes_effective: 20 * 1024 * 1024,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  is_global: true,
}

async function show() {
  list.mockResolvedValue([TYPE])
  render(
    <MemoryRouter>
      <LeftPanelProvider>
        <LeftPanelHost />
        <TestTypesPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
  await waitFor(() => expect(list).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
  memberships = [{ role: 'member' }]
})

describe('멤버', () => {
  it('목록은 보되 고치는 단추는 없다', async () => {
    // **서버는 원래 열려 있었다.** 막고 있던 것은 사이드바뿐이라, 실험하는 사람이
    // 「우리 시험이 무엇을 받나」 를 물을 데가 없었다.
    await show()
    expect((await screen.findAllByText(/인장/)).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /종류 만들기/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '편집' })).not.toBeInTheDocument()
  })
})

describe('부서 관리자', () => {
  it('고치는 단추가 있다', async () => {
    memberships = [{ role: 'manager' }]
    await show()
    expect(await screen.findByRole('button', { name: /종류 만들기/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '편집' })).toBeInTheDocument()
  })
})
