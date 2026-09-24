/**
 * 시험종류 정의 — **볼 수 있게 열었으면 못 고치는 것도 보여야 한다.**
 *
 * 목록을 모두에게 연 뒤(서버는 원래 열려 있었다) 남는 위험은 하나다: 쓰기 단추가
 * 그대로 있으면 멤버가 누르고 **403 을 본다.** 사이드바에 「미구현」 배지를 단 것과
 * 같은 자리다 — 눌러 보고 알게 하지 않는다.
 *
 * 그래서 무는 자리를 「목록이 뜬다」 가 아니라 **「누구에게 어떤 단추가 있나」** 에
 * 둔다. 이쪽이 틀리면 화면은 멀쩡해 보이는데 누르는 사람만 막힌다.
 *
 * **3단계에서 기준이 사람으로 바뀌었다**(ADR 0035). 만들기는 누구나, 고치기는 정의마다
 * 서버가 말한다(`access`) — 부서 관리자라는 자리가 단추를 정하지 않는다.
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
  id: 't1',
  owner_workspace_slug: null,
  owner_workspace_name: null,
}

/** 이 사람이 고칠 수 있나 — 서버가 정의마다 싣는다. */
function access(canEdit: boolean) {
  return {
    can_edit: canEdit,
    can_hand_over: canEdit,
    registrant_id: canEdit ? 'u1' : null,
    registrant: canEdit ? '앨리스' : null,
    edit_workspace_slug: null,
    edit_workspace: null,
    reason: canEdit ? null : '자료 관리자만 고칠 수 있습니다.',
  }
}

async function show(canEdit = false) {
  list.mockResolvedValue([{ ...TYPE, access: access(canEdit) }])
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

describe('만들기', () => {
  it('누구나 만든다 — 부서 관리자를 기다리지 않는다', async () => {
    // 전에는 부서 관리자만 「종류 생성」 을 봤다. 새 장비를 붙이는 사람은 대개 그 장비를
    // 쓰는 사람이고, 관리자를 기다리는 동안 파일은 쌓였다(ADR 0035 3단계).
    await show()
    expect(await screen.findByRole('button', { name: /종류 생성/ })).toBeInTheDocument()
  })
})

describe('고치기', () => {
  it('못 고치는 정의는 단추를 막고 누구에게 물을지 말한다', async () => {
    // **서버는 원래 열려 있었다.** 막고 있던 것은 사이드바뿐이라, 실험하는 사람이
    // 「우리 시험이 무엇을 받나」 를 물을 데가 없었다. 보는 것과 고치는 것은 다르다.
    await show(false)
    const edit = await screen.findByRole('button', { name: '편집' })
    expect(edit).toBeDisabled()
    expect(edit).toHaveAttribute('title', '자료 관리자만 고칠 수 있습니다.')
    expect(screen.getByText('읽기 전용')).toBeInTheDocument()
  })

  it('고칠 수 있으면 단추가 열린다', async () => {
    await show(true)
    expect(await screen.findByRole('button', { name: '편집' })).not.toBeDisabled()
    expect(screen.queryByText('읽기 전용')).not.toBeInTheDocument()
  })
})
