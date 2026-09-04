/**
 * 부서 합치기 창 — **무엇이 옮겨지는지 보고 누른다.**
 *
 *   옮겨질 목록이 먼저 뜬다        총계만 적으면 그 안에 뭐가 있는지 모른다
 *   대상을 안 고르면 못 누른다      어디로 가는지 없이 옮겨지면 안 된다
 *   끝나면 몇 건이 갔는지 말한다    결과 없이 닫히면 「됐나?」 로 남는다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MergeWorkspaceDialog } from '@/modules/workspaces/MergeWorkspaceDialog'
import type { Workspace } from '@/modules/workspaces/api'

const references = vi.fn()
const merge = vi.fn()

vi.mock('@/modules/workspaces/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workspaces/api')>()),
  workspacesApi: {
    references: (...args: unknown[]) => references(...args),
    merge: (...args: unknown[]) => merge(...args),
  },
}))

const SOURCE = { slug: 'old-team', name: '옛 팀', is_active: true } as Workspace
const CANDIDATES = [
  SOURCE,
  { slug: 'new-team', name: '새 팀', is_active: true } as Workspace,
  { slug: 'sleepy', name: '보관된 팀', is_active: false } as Workspace,
]

const MOVED = [
  { table: 'materials', column: 'owner_workspace_id', label: '재료', count: 12 },
  { table: 'test_runs', column: 'workspace_id', label: '시험', count: 34 },
]

function show(onDone = vi.fn()) {
  render(
    <MergeWorkspaceDialog
      workspace={SOURCE}
      candidates={CANDIDATES}
      onClose={() => {}}
      onDone={onDone}
    />
  )
  return onDone
}

beforeEach(() => {
  vi.clearAllMocks()
  references.mockResolvedValue(MOVED)
  merge.mockResolvedValue(MOVED)
})

describe('무엇이 옮겨지는지 보고 누른다', () => {
  it('옮겨질 목록이 이름과 수로 먼저 뜬다', async () => {
    show()
    expect(await screen.findByText(/옮겨질 자료 46건/)).toBeInTheDocument()
    expect(screen.getByText(/재료 · 12건/)).toBeInTheDocument()
    expect(merge).not.toHaveBeenCalled()
  })

  it('대상을 안 고르면 못 누른다', async () => {
    show()
    expect(await screen.findByRole('button', { name: /46건을 옮기고 합치기/ })).toBeDisabled()
  })

  it('원본과 보관된 부서는 대상 후보에 없다', async () => {
    // 자기 자신으로 합치기·보관된 부서로 합치기는 서버도 거절하지만,
    // 고를 수 있는데 못 쓰는 것이 가장 나쁘다 — 목록에서 뺀다.
    show()
    await userEvent.click(await screen.findByLabelText('합칠 대상 부서'))
    expect(screen.queryByRole('option', { name: /옛 팀/ })).toBeNull()
    expect(screen.queryByRole('option', { name: /보관된 팀/ })).toBeNull()
    expect(screen.getByRole('option', { name: /새 팀/ })).toBeInTheDocument()
  })

  it('고르고 누르면 옮기고, 몇 건이 갔는지 말한다', async () => {
    const onDone = show()
    await userEvent.click(await screen.findByLabelText('합칠 대상 부서'))
    await userEvent.click(screen.getByRole('option', { name: /새 팀/ }))
    await userEvent.click(screen.getByRole('button', { name: /46건을 옮기고 합치기/ }))

    await waitFor(() => expect(merge).toHaveBeenCalledWith('old-team', 'new-team'))
    expect(await screen.findByText(/46건이 대상 부서 소속이 됐습니다/)).toBeInTheDocument()
    expect(onDone).toHaveBeenCalled()
  })
})
