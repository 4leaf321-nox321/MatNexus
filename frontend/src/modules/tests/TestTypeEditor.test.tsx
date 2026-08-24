/**
 * 시험 종류 편집기 — **받은 리비전을 그대로 돌려보낸다**(ADR 0015).
 *
 * 이 정의는 한 벌 통째로 갈아 끼운다. 화면이 리비전을 안 보내면 서버가 못
 * 막고, 못 막으면 뒤에 저장한 쪽이 앞의 채널·조건을 **덮는 것이 아니라 통째로
 * 지운다.**
 *
 * 그리고 409 가 났을 때 **서버가 적어 보낸 말이 화면에 그대로 떠야 한다.**
 * "저장하지 못했습니다" 로 뭉개면 사람은 새로고침하고 자기 작업을 다시 잃는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TestTypeEditor } from '@/modules/tests/TestTypeEditor'

const updateType = vi.fn()
const createType = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    updateType: (...args: unknown[]) => updateType(...args),
    createType: (...args: unknown[]) => createType(...args),
    parsers: () => Promise.resolve([]),
  },
}))

// 편집기는 소유 부서 칸을 그리려고 로그인 정보를 읽는다. 이 시험이 보는 것은
// 리비전 왕복이라, 시스템 관리자 한 명이면 충분하다.
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

const TYPE = {
  id: 't1',
  key: 'tensile',
  label: '인장시험',
  abbr: 'TEN',
  description: null,
  parser_key: null,
  extensions: [],
  is_active: true,
  max_upload_bytes: null,
  max_upload_bytes_effective: 52428800,
  revision: 7,
  run_count: 0,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  is_global: true,
  channels: [
    {
      key: 'force',
      label: '하중',
      dimension: 'force',
      si_unit: 'N',
      is_required: true,
      sort_order: 0,
    },
  ],
  conditions: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  updateType.mockResolvedValue(TYPE)
})

async function save() {
  await userEvent.click(await screen.findByRole('button', { name: /저장/ }))
}

describe('시험 종류 편집기', () => {
  it('열었을 때 받은 리비전을 그대로 돌려보낸다', async () => {
    render(<TestTypeEditor type={TYPE} open onSaved={vi.fn()} onClose={vi.fn()} />)
    await save()
    await waitFor(() => expect(updateType).toHaveBeenCalled())
    const [, payload] = updateType.mock.calls[0] as [string, Record<string, unknown>]
    expect(payload.expected_revision).toBe(7)
  })

  it('충돌하면 서버가 적어 보낸 말을 그대로 보인다', async () => {
    // **"저장하지 못했습니다" 로 뭉개면 안 된다.** 무엇을 해야 하는지가 그 말에
    // 들어 있다 — 누가 언제 고쳤고, 지금 저장하면 그것이 지워진다는 것.
    updateType.mockRejectedValue(
      new Error(
        '이 시험 종류가 그사이 바뀌었습니다 (열었을 때 7, 지금 9). ' +
          '홍길동 이 2026-08-24 17:30 에 고쳤습니다 — ' +
          '새로 고쳐서 다시 여세요 — 지금 저장하면 그 변경이 지워집니다.'
      )
    )
    render(<TestTypeEditor type={TYPE} open onSaved={vi.fn()} onClose={vi.fn()} />)
    await save()
    expect(await screen.findByText(/열었을 때 7, 지금 9/)).toBeInTheDocument()
    expect(screen.getByText(/지워집니다/)).toBeInTheDocument()
  })

  it('충돌하면 저장됐다고 하지 않는다', async () => {
    const onSaved = vi.fn()
    updateType.mockRejectedValue(new Error('이 시험 종류가 그사이 바뀌었습니다.'))
    render(<TestTypeEditor type={TYPE} open onSaved={onSaved} onClose={vi.fn()} />)
    await save()
    await waitFor(() => expect(updateType).toHaveBeenCalled())
    expect(onSaved).not.toHaveBeenCalled()
  })
})
