/**
 * 아이디 내보내기 — **서버가 모은 한 줄을 그대로 보이고 복사한다.**
 *
 *   기본은 활성만, 체크하면 승인 대기·정지도 함께(서버에 다시 묻는다)
 *   복사 단추가 그 줄을 클립보드에 넣는다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExportIdsDialog } from '@/modules/accounts/ExportIdsDialog'

const ids = vi.fn()
const copyText = vi.fn()

vi.mock('@/modules/accounts/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/accounts/api')>()),
  accountsApi: { ids: (...args: unknown[]) => ids(...args) },
}))

vi.mock('@/shared/lib/clipboard', () => ({
  copyText: (text: string) => copyText(text),
}))

describe('아이디 내보내기', () => {
  beforeEach(() => {
    ids.mockReset()
    copyText.mockReset()
  })

  it('활성만 기본으로 모아 보이고, 포함을 켜면 다시 묻고, 복사한다', async () => {
    ids.mockImplementation((includeInactive: boolean) =>
      Promise.resolve(
        includeInactive
          ? { count: 3, ids: ['a@x', 'b@x', 'p@x'], text: 'a@x;b@x;p@x' }
          : { count: 2, ids: ['a@x', 'b@x'], text: 'a@x;b@x' }
      )
    )
    copyText.mockResolvedValue(true)
    render(<ExportIdsDialog open onClose={() => undefined} />)

    const box = await screen.findByLabelText('아이디 목록')
    await waitFor(() => expect(box).toHaveValue('a@x;b@x'))
    expect(screen.getByText('2명 · 아이디순')).toBeInTheDocument()
    expect(ids).toHaveBeenLastCalledWith(false)

    const user = userEvent.setup()
    await user.click(screen.getByLabelText('승인 대기·정지 계정도 포함'))
    await waitFor(() => expect(box).toHaveValue('a@x;b@x;p@x'))
    expect(ids).toHaveBeenLastCalledWith(true)

    await user.click(screen.getByRole('button', { name: '복사' }))
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('a@x;b@x;p@x'))
    expect(await screen.findByRole('button', { name: '복사됨' })).toBeInTheDocument()
  })
})
