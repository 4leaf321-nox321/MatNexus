/**
 * 물성 사용 보류(2026-11-14, VOC 60) — 자료 관리자만 걸고 풀며, 걸린 시험은 사유를 보인다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HoldPanel } from '@/modules/tests/HoldPanel'

const hold = vi.fn()
const release = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    hold: (...args: unknown[]) => hold(...args),
    release: (...args: unknown[]) => release(...args),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  hold.mockResolvedValue({})
  release.mockResolvedValue({})
})

describe('물성 사용 보류', () => {
  it('자료 관리자는 사유를 적어 건다', async () => {
    const onChanged = vi.fn()
    const user = userEvent.setup()
    render(<HoldPanel runId="r1" canSteward onChanged={onChanged} />)
    await user.click(screen.getByRole('button', { name: /물성 사용 보류/ }))
    const save = screen.getByRole('button', { name: '보류 걸기' })
    expect(save).toBeDisabled() // 사유 없는 보류는 없다
    await user.type(screen.getByLabelText('보류 사유'), '그립 미끄럼 의심')
    await user.click(save)
    await waitFor(() => expect(hold).toHaveBeenCalledWith('r1', '그립 미끄럼 의심'))
    expect(onChanged).toHaveBeenCalled()
  })

  it('걸린 시험은 사유를 보이고, 자료 관리자는 푼다', async () => {
    const user = userEvent.setup()
    render(
      <HoldPanel runId="r1" holdReason="재시험 대기" heldBy="김관리" canSteward onChanged={() => {}} />
    )
    expect(screen.getByText('재시험 대기')).toBeInTheDocument()
    expect(screen.getByText(/김관리/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '보류 풀기' }))
    await waitFor(() => expect(release).toHaveBeenCalledWith('r1'))
  })

  it('자료 관리자가 아니면 사유만 보고 단추가 없다', () => {
    render(<HoldPanel runId="r1" holdReason="재시험 대기" canSteward={false} onChanged={() => {}} />)
    expect(screen.getByText('재시험 대기')).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('보류가 아니고 자료 관리자도 아니면 아무것도 안 그린다', () => {
    const { container } = render(<HoldPanel runId="r1" canSteward={false} onChanged={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
