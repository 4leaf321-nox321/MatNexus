/**
 * 시험 골라 담기 — **업무가 처음 거르기를 정하고, 담은 것은 다시 안 고른다**(ADR 0058).
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RunCollector } from '@/modules/tests/RunCollector'

const runs = vi.fn()
const types = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    runs: (...args: unknown[]) => runs(...args),
    types: (...args: unknown[]) => types(...args),
  },
}))
vi.mock('@/modules/materials/MaterialPicker', () => ({
  MaterialPicker: ({ onSelect }: { onSelect: (one: { id: string }) => void }) => (
    <button type="button" onClick={() => onSelect({ id: 'm1' })}>
      재료 SECC
    </button>
  ),
}))

function row(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    code: `T-${id}`,
    record_name: `시편-${id}`,
    status: 'parsed',
    material_name: 'SECC',
    test_type_label: '인장',
    result_count: 0,
    adopted_result_id: null,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  types.mockResolvedValue([{ key: 'tensile', label: '인장' }])
  runs.mockResolvedValue({
    items: [row('1'), row('2', { result_count: 2 }), row('3')],
    total: 3,
    limit: 100,
    offset: 0,
  })
})

describe('시험 골라 담기', () => {
  it('업무가 정한 처리 상태로 처음 거르고, 사람이 바꾼다', async () => {
    render(<RunCollector processing="results" taken={[]} onPick={vi.fn()} />)
    await screen.findByText('시편-1')
    expect(runs.mock.calls[0][0]).toMatchObject({ processing: 'results', limit: 100 })
    await userEvent.selectOptions(screen.getByLabelText('처리 상태'), '')
    await waitFor(() => expect(runs.mock.calls.at(-1)?.[0].processing).toBeUndefined())
    await userEvent.click(screen.getByRole('button', { name: '재료 SECC' }))
    await waitFor(() => expect(runs.mock.calls.at(-1)?.[0]).toMatchObject({ material_id: 'm1' }))
  })

  it('담은 것은 「담김」 으로 서고 다시 못 고른다', async () => {
    const onPick = vi.fn().mockResolvedValue(undefined)
    render(<RunCollector taken={['2']} onPick={onPick} />)
    const taken = within((await screen.findByText('시편-2')).closest('tr')!)
    expect(taken.getByText('담김')).toBeInTheDocument()
    expect(taken.getByRole('checkbox')).toBeDisabled()

    // 「보이는 것 모두」 는 담긴 것을 빼고 센다.
    await userEvent.click(screen.getByRole('button', { name: '보이는 2건 모두 담기' }))
    expect(onPick).toHaveBeenCalledWith(['1', '3'])
  })

  it('고른 것만 담고, 담으면 고른 것을 비운다', async () => {
    const onPick = vi.fn().mockResolvedValue(undefined)
    render(<RunCollector taken={[]} onPick={onPick} />)
    await userEvent.click(await screen.findByLabelText('시편-3 고르기'))
    await userEvent.click(screen.getByRole('button', { name: '고른 1건 담기' }))
    expect(onPick).toHaveBeenCalledWith(['3'])
    expect(await screen.findByRole('button', { name: '고른 0건 담기' })).toBeDisabled()
  })

  it('잘렸으면 몇 건 중 몇 건인지 말한다', async () => {
    // 잘렸다는 사실을 숨기면 없는 시험처럼 보인다.
    runs.mockResolvedValue({ items: [row('1')], total: 340, limit: 100, offset: 0 })
    render(<RunCollector taken={[]} onPick={vi.fn()} />)
    expect(await screen.findByText(/340건 중 최근 1건/)).toBeInTheDocument()
  })

  it('읽기로 연 작업이면 담지 못한다', async () => {
    render(<RunCollector taken={[]} disabled onPick={vi.fn()} />)
    await screen.findByText('시편-1')
    expect(screen.getByLabelText('시편-1 고르기')).toBeDisabled()
    expect(screen.getByRole('button', { name: /모두 담기/ })).toBeDisabled()
  })
})
