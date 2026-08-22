/**
 * 값을 지우기 전에 묻는다.
 *
 * **지우기는 되돌릴 길이 없다.** 그런데 줄에서 한 번 누르면 끝나는 자리에 있고,
 * 감추기 바로 옆이라 손이 미끄러지기도 쉽다.
 *
 * 그리고 **쓰이는 값은 못 지운다.** 지우면서 참조를 끊으면 그 시료가 어느
 * 제조사였는지 영영 알 수 없게 되는데, 그건 값을 정리하는 것과 전혀 다른 일이다.
 * 눌러 보고 알게 하는 대신 미리 말하고, 대신 쓸 길을 짚는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConfirmDeleteDialog } from '@/modules/vocabulary/VocabularyAdminPage'
import type { Term } from '@/modules/vocabulary/api'

const removeMany = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: { removeMany: (...args: unknown[]) => removeMany(...args) },
}))

const term = (usage = 0): Term =>
  ({ id: 'term-1', value: '쓰는 곳 1', usage_count: usage, status: 'active' }) as unknown as Term

function show(usage = 0) {
  const onRemoved = vi.fn()
  render(
    <ConfirmDeleteDialog
      slug="manufacturer"
      term={term(usage)}
      onClose={() => {}}
      onRemoved={onRemoved}
    />
  )
  return onRemoved
}

beforeEach(() => {
  vi.clearAllMocks()
  removeMany.mockResolvedValue({ deleted: 1, blocked: 0, items: [{ deleted: true }] })
})

describe('지우기 확인', () => {
  it('무엇을 지우는지 이름으로 다시 보여 준다', async () => {
    show()
    expect(await screen.findByText('쓰는 곳 1')).toBeInTheDocument()
    expect(screen.getByText(/되돌릴 수 없습니다/)).toBeInTheDocument()
  })

  it('묻기 전에는 아무것도 안 지운다', async () => {
    show()
    await screen.findByText('쓰는 곳 1')
    expect(removeMany).not.toHaveBeenCalled()
  })

  it('확인하면 지운다', async () => {
    const user = userEvent.setup()
    const onRemoved = show()
    await user.click(await screen.findByRole('button', { name: '지우기' }))

    await waitFor(() => expect(removeMany).toHaveBeenCalledWith('manufacturer', ['term-1']))
    expect(onRemoved).toHaveBeenCalled()
  })

  it('쓰이는 값은 못 지운다고 미리 말한다', async () => {
    // **눌러 보고 알게 하지 않는다.** 그리고 대신 쓸 길을 짚는다.
    show(12)
    const notice = await screen.findByText(/12곳/)
    expect(notice.closest('p')).toHaveTextContent('감추기')
    expect(notice.closest('p')).toHaveTextContent('병합')
    expect(screen.getByRole('button', { name: '지우기' })).toBeDisabled()
  })

  it('서버가 막으면 그 이유를 그대로 보여 준다', async () => {
    // **막힌 이유는 서버가 안다.** 화면이 다시 판단하면 두 규칙이 갈라진다 —
    // 하위 값이 달린 경우는 화면이 모른다.
    const user = userEvent.setup()
    removeMany.mockResolvedValue({
      deleted: 0,
      blocked: 1,
      items: [{ deleted: false, reason: '하위 값 3개가 달려 있습니다.' }],
    })
    show()
    await user.click(await screen.findByRole('button', { name: '지우기' }))

    expect(await screen.findByText('하위 값 3개가 달려 있습니다.')).toBeInTheDocument()
  })
})
