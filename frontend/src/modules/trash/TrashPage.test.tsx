/**
 * 휴지통 화면 — **되살릴 수 있는지 화면이 정하지 않는다.**
 *
 * 무는 자리를 고를 때 「표가 그려진다」 보다 **「못 되살리는 이유가 보인다」**·
 * 「영구 삭제가 곧장 안 나간다」 를 우선한다. 앞엣것은 시험이 없어도 눈에
 * 보이지만, 뒤엣것은 조용히 틀리고 되돌릴 수 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TrashPage from '@/modules/trash/TrashPage'

const list = vi.fn()
const restore = vi.fn()
const purge = vi.fn()

vi.mock('@/modules/trash/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/trash/api')>(
    '@/modules/trash/api'
  )
  return {
    ...actual,
    trashApi: {
      list: (...args: unknown[]) => list(...args),
      restore: (...args: unknown[]) => restore(...args),
      purge: (...args: unknown[]) => purge(...args),
    },
  }
})

const FREE = {
  kind: 'specimen',
  kind_label: '시편',
  id: 's1',
  name: 'SECC__01_MD_01',
  deleted_at: '2026-08-28T01:00:00Z',
  workspace_id: null,
  below: {},
  blocked: null,
}

const BLOCKED = {
  kind: 'material',
  kind_label: '재료',
  id: 'm1',
  name: 'SECC_MDOI_1.0',
  deleted_at: '2026-08-28T02:00:00Z',
  workspace_id: null,
  below: { 시료: 2, 시편: 6 },
  blocked: '같은 이름의 재료가 이미 살아 있습니다: SECC_MDOI_1.0.',
}

beforeEach(() => {
  list.mockReset()
  restore.mockReset()
  purge.mockReset()
  list.mockResolvedValue([FREE, BLOCKED])
  restore.mockResolvedValue({ name: 'x', counts: {}, said: '시편 1건' })
  purge.mockResolvedValue({ name: 'x', counts: {}, said: '시편 1건' })
})

describe('되살리기', () => {
  it('막힌 줄은 이유를 적고 단추를 잠근다', async () => {
    /**
     * **단추만 끄면 사람은 그 자리에서 멈춘다.** 처리 화면이 「돌려 보기가 그냥
     * 비활성」 이었을 때 같은 실패를 했다 — 왜 안 되는지가 안 보였다.
     */
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    expect(screen.getByText(/이미 살아 있습니다/)).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: '되살리기' })
    // 목록 순서는 서버가 준 그대로 — 둘째 줄이 막힌 것이다.
    expect(buttons[1]).toBeDisabled()
    expect(buttons[0]).not.toBeDisabled()
  })

  it('함께 돌아오는 것을 서버가 준 대로 보인다', async () => {
    // 화면이 스스로 세면 사람이 본 숫자와 실제가 어긋난다.
    render(<TrashPage />)
    expect(await screen.findByText('시료 2건 · 시편 6건')).toBeInTheDocument()
  })

  it('누르면 그 종류와 id 로 부른다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '되살리기' })[0])
    await waitFor(() => expect(restore).toHaveBeenCalledWith('specimen', 's1'))
  })
})

describe('영구 삭제', () => {
  it('묻기 전에는 안 부른다', async () => {
    /** **되돌릴 수 없다.** 단추 한 번에 나가면 안 된다. */
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[0])
    expect(purge).not.toHaveBeenCalled()
  })

  it('무엇이 사라지는지 이름과 수로 적는다', async () => {
    // 「정말 지울까요?」 만으로는 사람이 무엇에 동의하는지 모른다.
    render(<TrashPage />)
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[1])
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('SECC_MDOI_1.0')
    expect(dialog).toHaveTextContent('시료 2건 · 시편 6건')
  })

  it('확인해야 나간다', async () => {
    render(<TrashPage />)
    await screen.findByText('SECC__01_MD_01')

    await userEvent.click(screen.getAllByRole('button', { name: '영구 삭제' })[0])
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '영구 삭제', hidden: false }))

    await waitFor(() => expect(purge).toHaveBeenCalledWith('specimen', 's1'))
  })
})
