/**
 * VOC 고치기·지우기 — **누구에게 단추가 보이는가.**
 *
 * 규칙은 서버가 정한다(`voc/routes.py` 의 `_mine`) — 낸 사람은 답변 전까지,
 * 관리자는 언제나. 화면이 그것과 다르면 두 가지로 틀린다.
 *
 *   보이면 안 되는데 보인다   눌러야 막힌다. 사람은 「고장」 으로 읽는다
 *   보여야 하는데 안 보인다   기능이 없는 것과 구별이 안 된다
 *
 * 그리고 **내 것인지는 서버가 준 `is_mine` 으로 안다.** 작성자 이름으로 짐작하면
 * 동명이인이 남의 제보를 고치게 된다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import VocPage from '@/modules/voc/VocPage'

const list = vi.fn()
const remove = vi.fn()

vi.mock('@/modules/voc/api', () => ({
  vocApi: {
    list: () => list(),
    create: vi.fn(),
    update: vi.fn(),
    remove: (id: string) => remove(id),
    reply: vi.fn(),
  },
}))

let isAdmin = false
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { display_name: '홍길동', is_system_admin: isAdmin } }),
}))

const item = (over: Record<string, unknown> = {}) => ({
  id: 'voc-1',
  title: '목록이 느려요',
  body: '시험 목록이 느립니다',
  status: 'open',
  page_path: '/w/metal/tests',
  created_at: '2026-08-27T10:00:00Z',
  created_by: '홍길동',
  is_mine: true,
  reply: null,
  replied_at: null,
  ...over,
})

async function show(rows: unknown[]) {
  list.mockResolvedValue(rows)
  render(<VocPage />)
  await waitFor(() => expect(list).toHaveBeenCalled())
}

describe('VOC 고치기·지우기', () => {
  beforeEach(() => {
    isAdmin = false
    list.mockReset()
    remove.mockReset()
    remove.mockResolvedValue(undefined)
  })

  it('내가 낸 것은 답변 전까지 고치고 지울 수 있다', async () => {
    await show([item()])
    expect(await screen.findByLabelText('목록이 느려요 고치기')).toBeInTheDocument()
    expect(screen.getByLabelText('목록이 느려요 삭제')).toBeInTheDocument()
  })

  it('답변이 달리면 단추가 사라진다', async () => {
    // 본문이 바뀌면 답변이 딴 소리가 된다 — 그때는 새로 내는 것이 맞다.
    await show([item({ reply: '고쳤습니다', status: 'resolved' })])
    await screen.findByText('목록이 느려요')
    expect(screen.queryByLabelText('목록이 느려요 고치기')).not.toBeInTheDocument()
  })

  it('남이 낸 것에는 단추가 없다', async () => {
    // **이름이 같아도 안 된다.** `created_by` 가 아니라 `is_mine` 이 정한다.
    await show([item({ is_mine: false, created_by: '홍길동' })])
    await screen.findByText('목록이 느려요')
    expect(screen.queryByLabelText('목록이 느려요 삭제')).not.toBeInTheDocument()
  })

  it('관리자는 답변이 달린 남의 것도 고칠 수 있다', async () => {
    isAdmin = true
    await show([item({ is_mine: false, reply: '고쳤습니다', status: 'resolved' })])
    expect(await screen.findByLabelText('목록이 느려요 고치기')).toBeInTheDocument()
  })

  it('지우기 전에 묻는다 — 무엇이 없어지는지와 함께', async () => {
    const user = userEvent.setup()
    await show([item()])

    await user.click(await screen.findByLabelText('목록이 느려요 삭제'))
    // 「무슨 제보가 있었는지」 까지 없어진다는 것이 이 창의 요점이다.
    expect(await screen.findByText(/무슨 제보가 있었는지/)).toBeInTheDocument()
    expect(remove).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith('voc-1'))
  })
})
