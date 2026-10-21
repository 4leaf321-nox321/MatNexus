/**
 * 한 시편의 시험 — **골라 지운다**(2026-10-20).
 *
 * 사용자 보고: 잘못된 옵션으로 올린 시험을 하나씩 열어 지워야 했다. 「실패만 고르기」 가
 * 읽기에 실패한 것만 고르는지, 지운 뒤 시편 표가 수를 다시 세게 알리는지를 본다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenTests } from '@/modules/tests/SpecimenTests'

const runs = vi.fn()
const removeMany = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    runs: (...args: unknown[]) => runs(...args),
    removeMany: (...args: unknown[]) => removeMany(...args),
  },
}))

vi.mock('@/modules/tests/UploadDialog', () => ({ UploadDialog: () => null }))

const run = (id: string, name: string, status: string) => ({
  id,
  record_name: name,
  status,
  warnings: [],
  row_count: status === 'parsed' ? 120 : null,
})

beforeEach(() => {
  vi.clearAllMocks()
  runs.mockResolvedValue({
    items: [
      run('r1', 'MD_01__TEN_01', 'parsed'),
      run('r2', 'MD_01__TEN_02', 'failed'),
      run('r3', 'MD_01__TEN_03', 'failed'),
    ],
    total: 3,
    limit: 50,
    offset: 0,
  })
})

describe('골라 지우기 (2026-10-20)', () => {
  it('「실패만 고르기」 가 실패한 것만 고르고, 지우면 시편 표에 알린다', async () => {
    removeMany.mockResolvedValue({ deleted: 2, blocked: [] })
    const onChanged = vi.fn()
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <SpecimenTests specimenId="p1" specimenName="MD_01" onChanged={onChanged} />
      </MemoryRouter>
    )
    // **데이터로 그려진 것을 기다린다** — 단추는 실패한 시험이 와야 선다.
    await user.click(await screen.findByRole('button', { name: /실패만 고르기 \(2\)/ }))
    expect(screen.getByRole('checkbox', { name: 'MD_01__TEN_01 선택' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'MD_01__TEN_02 선택' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'MD_01__TEN_03 선택' })).toBeChecked()

    await user.click(screen.getByRole('button', { name: '삭제' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('MD_01__TEN_02')
    expect(dialog).not.toHaveTextContent('MD_01__TEN_01')
    await user.click(within(dialog).getByRole('button', { name: '삭제' }))

    await waitFor(() => expect(removeMany).toHaveBeenCalledWith(['r2', 'r3']))
    expect(await screen.findByText('시험 2건을 지웠습니다.')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('못 지운 것은 이름과 이유를 말한다', async () => {
    removeMany.mockResolvedValue({
      deleted: 0,
      blocked: ['MD_01__TEN_02 — 이 시험을 고칠 권한이 없습니다'],
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <SpecimenTests specimenId="p1" specimenName="MD_01" />
      </MemoryRouter>
    )
    await user.click(await screen.findByRole('checkbox', { name: 'MD_01__TEN_02 선택' }))
    await user.click(screen.getByRole('button', { name: '삭제' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '삭제' }))
    expect(await screen.findByText(/권한이 없습니다/)).toBeInTheDocument()
  })
})
