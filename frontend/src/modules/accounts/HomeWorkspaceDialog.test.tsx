/**
 * 대표 소속 — **로그인해서 처음 서는 자리를 사람이 정한다.**
 *
 * 안 정하면 `memberships[0]`, 즉 이름 순 첫 부서로 떨어진다. 부서 하나뿐인
 * 사람에게는 맞지만 시스템 관리자처럼 여러 부서에 든 사람은 매번 엉뚱한 곳에
 * 선다.
 *
 * 여기서 지키는 것 둘:
 *
 *   ① **그 사람의 부서만 고를 수 있다.** 멤버가 아닌 부서를 주면 그 사람은
 *      자기가 못 보는 곳에 서고, 목록이 비어 보인다 — 데이터가 없는 것과
 *      구별이 안 된다. 서버도 막지만, 고를 수 없는 것을 보여 주고 나서
 *      거절하는 것은 화면의 일이 아니다.
 *   ② **안 바뀐 값으로는 저장하지 않는다.** 감사 기록에 아무 일도 안 한 줄이
 *      쌓이면 "누가 언제 옮겼나" 를 찾을 때 그 줄들을 걷어내야 한다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomeWorkspaceDialog } from '@/modules/accounts/HomeWorkspaceDialog'
import type { Account } from '@/modules/accounts/api'

const setHomeWorkspace = vi.fn()

vi.mock('@/modules/accounts/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/accounts/api')>()),
  accountsApi: {
    setHomeWorkspace: (...args: unknown[]) => setHomeWorkspace(...args),
  },
}))

/** 전사 부서 셋. 이 사람은 그중 둘에만 들어 있다. */
const WORKSPACES = [
  { slug: 'metal', name: '금속재료팀', path: '개발본부 / 금속재료팀', depth: 1 },
  { slug: 'polymer', name: '고분자팀', path: '개발본부 / 고분자팀', depth: 1 },
  { slug: 'quality', name: '품질보증팀', path: '품질본부 / 품질보증팀', depth: 1 },
]

const ACCOUNT = {
  id: 'account-1',
  email: 'hong',
  display_name: '홍길동',
  status: 'active',
  is_system_admin: false,
  must_change_password: false,
  home_workspace_slug: 'metal',
  requested_workspace_slug: 'metal',
  memberships: ['metal', 'polymer'],
} as unknown as Account

function show(account: Account = ACCOUNT, onSaved = vi.fn()) {
  render(
    <HomeWorkspaceDialog
      account={account}
      workspaces={WORKSPACES}
      onClose={vi.fn()}
      onSaved={onSaved}
    />
  )
  return onSaved
}

describe('대표 소속', () => {
  beforeEach(() => {
    setHomeWorkspace.mockReset()
    setHomeWorkspace.mockResolvedValue(ACCOUNT)
  })

  it('그 사람이 속한 부서만 고를 수 있다', async () => {
    const user = userEvent.setup()
    show()

    await user.click(screen.getByRole('button', { name: /금속재료팀/ }))

    expect(await screen.findByText('고분자팀')).toBeInTheDocument()
    // **멤버가 아닌 부서는 아예 안 보인다.** 보여 주고 나서 거절하면, 사람은
    // 무엇이 잘못됐는지가 아니라 "왜 안 되지" 를 묻게 된다.
    expect(screen.queryByText('품질보증팀')).not.toBeInTheDocument()
  })

  it('고른 부서를 보낸다', async () => {
    const user = userEvent.setup()
    const onSaved = show()

    await user.click(screen.getByRole('button', { name: /금속재료팀/ }))
    await user.click(await screen.findByText('고분자팀'))
    await user.click(screen.getByRole('button', { name: '정하기' }))

    await waitFor(() => expect(setHomeWorkspace).toHaveBeenCalledWith('account-1', 'polymer'))
    expect(onSaved).toHaveBeenCalledWith(expect.stringContaining('고분자팀'))
  })

  it('지금 값 그대로면 저장할 수 없다', () => {
    show()
    expect(screen.getByRole('button', { name: '정하기' })).toBeDisabled()
  })

  it('대표 소속이 없던 사람도 정할 수 있다', async () => {
    const user = userEvent.setup()
    show({ ...ACCOUNT, home_workspace_slug: null })

    await user.click(screen.getByRole('button', { name: /부서 고르기/ }))
    await user.click(await screen.findByText('금속재료팀'))
    await user.click(screen.getByRole('button', { name: '정하기' }))

    await waitFor(() => expect(setHomeWorkspace).toHaveBeenCalledWith('account-1', 'metal'))
  })
})
