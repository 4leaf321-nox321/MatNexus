/**
 * 고른 시험의 칸 하나를 한 번에 맞추는 창.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   위험한 칸이 안 보인다      상태·시편·종류는 목록에 아예 없다
 *   칸을 바꾸면 값이 비워진다  장비에 적은 글자가 사업부로 넘어가면 안 된다
 *   비운 채 눌러도 뜻이 있다   그 값을 지운다 — 그것을 미리 말한다
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BulkEditDialog } from '@/modules/tests/BulkEditDialog'

const bulkUpdate = vi.fn()
const search = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { bulkUpdate: (...args: unknown[]) => bulkUpdate(...args) },
}))

vi.mock('@/modules/vocabulary/api', () => ({
  vocabularyApi: {
    search: (...args: unknown[]) => search(...args),
    create: vi.fn(),
  },
}))

const IDS = ['r-1', 'r-2', 'r-3']

function open(onDone = vi.fn()) {
  return render(
    <BulkEditDialog open runIds={IDS} onClose={vi.fn()} onDone={onDone} />
  )
}

beforeEach(() => {
  bulkUpdate.mockReset()
  bulkUpdate.mockResolvedValue({ updated: 3, unchanged: 0, blocked: [] })
  search.mockReset()
  search.mockResolvedValue({ items: [] })
})

describe('일괄 수정', () => {
  it('몇 건을 고치는지 단추에 적는다', () => {
    open()
    expect(screen.getByRole('button', { name: '3건에 적용' })).toBeInTheDocument()
  })

  it('처음 고르는 칸이 사업부다', async () => {
    // 이 기능을 만든 이유가 그것이다 — 올릴 때 빠뜨리는 칸.
    open()
    fireEvent.click(screen.getByRole('button', { name: '3건에 적용' }))
    await waitFor(() => expect(bulkUpdate).toHaveBeenCalled())
    expect(bulkUpdate.mock.calls[0][1]).toBe('division')
  })

  it('위험한 칸은 목록에 없다', async () => {
    // **막는 것이 아니라 보이지 않는다.** 상태·시편·종류를 손으로 옮기면
    // 「읽힌 적 없는데 처리됨」 같은 상태가 만들어진다.
    open()
    fireEvent.keyDown(screen.getByLabelText('고칠 칸'), { key: 'Enter' })
    const options = await screen.findAllByRole('option')
    const labels = options.map((one) => one.textContent)
    expect(labels).toEqual(['사업부', '장비', '시험자', '시험일', '메모'])
  })

  it('칸을 바꾸면 적어 둔 값을 비운다', async () => {
    // **장비에 적은 글자가 사업부 칸에 그대로 남아 있으면** 그것이 그대로
    // 스무 건에 들어간다. 사람은 칸만 바꿨다고 생각한다.
    open()
    fireEvent.keyDown(screen.getByLabelText('고칠 칸'), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: '시험자' }))

    const box = await screen.findByLabelText('시험자로')
    fireEvent.change(box, { target: { value: '박' } })
    expect(box).toHaveValue('박')

    fireEvent.keyDown(screen.getByLabelText('고칠 칸'), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: '메모' }))
    expect(await screen.findByLabelText('메모로')).toHaveValue('')
  })

  it('비우면 지운다고 미리 말한다', () => {
    // 값을 확인만 하려고 창을 열었다 무심코 누른 사람이 스무 건을 비운다.
    open()
    expect(screen.getByText(/비워 두고 적용하면 그 값을 지웁니다/)).toBeInTheDocument()
  })

  it('빈 칸은 비우는 뜻으로 나간다', async () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: '3건에 적용' }))
    await waitFor(() => expect(bulkUpdate).toHaveBeenCalled())
    expect(bulkUpdate.mock.calls[0][2]).toBe('')
  })

  it('이미 그 값이던 것을 함께 말한다', async () => {
    // **조용히 성공으로 세지 않는다.** 3건을 골랐는데 「1건 바꿨습니다」 가
    // 나오면 나머지 둘이 왜 빠졌는지 알 수 있어야 한다.
    bulkUpdate.mockResolvedValue({ updated: 1, unchanged: 2, blocked: ['r-3'] })
    open()
    fireEvent.click(screen.getByRole('button', { name: '3건에 적용' }))
    const line = await screen.findByText(/1건을 바꿨습니다/)
    expect(line).toHaveTextContent('2건은 이미 그 값이었습니다')
    expect(screen.getByText(/1건은 권한이 없어/)).toBeInTheDocument()
  })

  it('막힌 것이 있으면 창을 닫지 않는다', async () => {
    const onClose = vi.fn()
    bulkUpdate.mockResolvedValue({ updated: 2, unchanged: 0, blocked: ['r-3'] })
    render(<BulkEditDialog open runIds={IDS} onClose={onClose} onDone={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '3건에 적용' }))
    await waitFor(() => expect(bulkUpdate).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
  })
})
