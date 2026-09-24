/**
 * 누가 고치나 — 넘기는 창(ADR 0035).
 *
 *   못 넘기는 사람에게는 칸을 안 연다       편집 부서 사람은 고쳐도 넘기지는 못한다
 *   **안 바꾼 칸은 안 보낸다**             등록자만 넘기다 부서 부여가 사라지면 안 된다
 *   건너뛴 것을 이름과 까닭으로 말한다      남이 붙인 것은 그 사람이 넘긴다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OwnershipDialog } from '@/modules/ownership/OwnershipDialog'
import type { Ownership } from '@/modules/ownership/api'

const get = vi.fn()
const change = vi.fn()
const people = vi.fn()

vi.mock('@/modules/ownership/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/ownership/api')>()),
  ownershipApi: {
    get: (...args: unknown[]) => get(...args),
    change: (...args: unknown[]) => change(...args),
    people: (...args: unknown[]) => people(...args),
  },
}))

vi.mock('@/modules/workspaces/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workspaces/api')>()),
  workspacesApi: {
    options: () => Promise.resolve([{ slug: 'polymer', name: '고분자팀', path: '고분자팀', depth: 0 }]),
  },
}))

function ownership(overrides: Partial<Ownership['access']> = {}): Ownership {
  return {
    kind: 'material',
    id: 'm-1',
    name: 'SECC_-_1.0',
    access: {
      can_edit: true,
      can_hand_over: true,
      registrant_id: 'u-1',
      registrant: '앨리스',
      edit_workspace_slug: 'metal',
      edit_workspace: '금속팀',
      reason: null,
      ...overrides,
    },
    children: [{ kind: 'sample', label: '시료', total: 2, changeable: 1 }],
  }
}

beforeEach(() => {
  get.mockReset()
  change.mockReset()
  people.mockReset()
})

describe('넘기는 창', () => {
  it('넘길 수 없는 사람에게는 칸을 안 열고 까닭을 말한다', async () => {
    get.mockResolvedValue(
      ownership({ can_hand_over: false, can_edit: true, registrant: '보라' })
    )
    render(<OwnershipDialog kind="material" id="m-1" onClose={() => {}} />)

    expect(await screen.findByText(/등록자와 자료 관리자만 넘길 수 있습니다/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '넘기기' })).not.toBeInTheDocument()
  })

  it('등록자만 넘기면 편집 부서 칸은 보내지 않는다', async () => {
    get.mockResolvedValue(ownership())
    people.mockResolvedValue([{ id: 'u-2', display_name: '앨런', workspace: '금속팀' }])
    change.mockResolvedValue({ changed: 1, skipped: [], access: ownership().access })
    const user = userEvent.setup()
    render(<OwnershipDialog kind="material" id="m-1" onClose={() => {}} />)

    await user.type(await screen.findByPlaceholderText('이름으로 찾기'), '앨런')
    await user.click(await screen.findByRole('button', { name: /앨런/ }))
    await user.click(screen.getByRole('button', { name: '넘기기' }))

    await waitFor(() => expect(change).toHaveBeenCalled())
    const body = change.mock.calls[0][2] as Record<string, unknown>
    expect(body.registrant_id).toBe('u-2')
    // **안 보낸 것과 비운 것은 다르다** — 칸이 아예 없어야 서버가 그대로 둔다.
    expect('edit_workspace_slug' in body).toBe(false)
  })

  it('부여를 걷으면 null 을 보낸다', async () => {
    get.mockResolvedValue(ownership())
    change.mockResolvedValue({ changed: 1, skipped: [], access: ownership().access })
    const user = userEvent.setup()
    render(<OwnershipDialog kind="material" id="m-1" onClose={() => {}} />)

    await user.click(await screen.findByLabelText('부여 걷기'))
    await user.click(screen.getByRole('button', { name: '넘기기' }))

    await waitFor(() => expect(change).toHaveBeenCalled())
    const body = change.mock.calls[0][2] as Record<string, unknown>
    expect(body.edit_workspace_slug).toBeNull()
    expect('registrant_id' in body).toBe(false)
  })

  it('건너뛴 것을 이름과 까닭으로 말한다', async () => {
    get.mockResolvedValue(ownership())
    change.mockResolvedValue({
      changed: 1,
      skipped: [
        {
          kind: 'sample',
          name: 'SECC_-_1.0__02',
          reason: '등록자 보라 — 등록자와 자료 관리자만 넘길 수 있습니다.',
        },
      ],
      access: ownership().access,
    })
    const user = userEvent.setup()
    render(<OwnershipDialog kind="material" id="m-1" onClose={() => {}} />)

    await user.click(await screen.findByLabelText('부여 걷기'))
    await user.click(screen.getByLabelText('아래에 딸린 것도 함께'))
    await user.click(screen.getByRole('button', { name: '넘기기' }))

    expect(await screen.findByText(/1건을 넘겼습니다/)).toBeInTheDocument()
    expect(screen.getByText(/SECC_-_1.0__02 — 등록자 보라/)).toBeInTheDocument()
    expect(change.mock.calls[0][2]).toMatchObject({ include_children: true })
  })
})
