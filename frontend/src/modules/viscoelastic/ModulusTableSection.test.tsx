/**
 * 주파수 지정 온도별 E′ 표 — **DMA 온도별 E′ 를 잰 물성으로 · 카드로**(v1.285.0 보고).
 *
 *   주파수를 넣어 표를 만든다          서버가 곡선 여럿을 읽는다
 *   표에서 카드를 만든다              이름을 비우면 주파수가 든 이름
 *   표를 지운다                       확인 창을 거친다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModulusTableSection } from '@/modules/viscoelastic/ModulusTableSection'

const modulusTables = vi.fn()
const createModulusTable = vi.fn()
const removeModulusTable = vi.fn()
const createDmaTemperature = vi.fn()

vi.mock('@/modules/viscoelastic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/viscoelastic/api')>()),
  viscoelasticApi: {
    modulusTables: (...args: unknown[]) => modulusTables(...args),
    createModulusTable: (...args: unknown[]) => createModulusTable(...args),
    removeModulusTable: (...args: unknown[]) => removeModulusTable(...args),
  },
}))

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: { createDmaTemperature: (...args: unknown[]) => createDmaTemperature(...args) },
}))

const TABLE = {
  id: 'table-1',
  test_run_id: 'run-1',
  frequency_hz: 1,
  modulus_basis: 'E',
  rows: [
    { temperature_k: 253.15, storage_pa: 2e9, loss_pa: 2e8, tan_delta: 0.1 },
    { temperature_k: 293.15, storage_pa: 1e9, loss_pa: 1.5e8, tan_delta: 0.15 },
  ],
  source_curve_keys: ['a', 'b'],
  notes: ['\'60 °C\' 는 범위 밖이라 그 온도를 뺐습니다.'],
  created_at: '2026-10-22T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  modulusTables.mockResolvedValue([])
})

describe('주파수 지정 온도별 E′ 표', () => {
  it('주파수를 넣어 표를 만들고 온도마다 한 줄을 보인다', async () => {
    const user = userEvent.setup()
    createModulusTable.mockResolvedValue(TABLE)
    render(<ModulusTableSection testRunId="run-1" />)
    await waitFor(() => expect(modulusTables).toHaveBeenCalled())
    const input = screen.getByLabelText(/주파수/)
    await user.clear(input)
    await user.type(input, '1')
    modulusTables.mockResolvedValue([TABLE])
    await user.click(screen.getByRole('button', { name: '표 만들기' }))
    await waitFor(() => expect(createModulusTable).toHaveBeenCalledWith('run-1', 1))
    // 데이터로 그려진 줄을 기다린다 — 표 머리만 먼저 서면 안 된다.
    expect(await screen.findByText(/범위 밖이라 그 온도를 뺐습니다/)).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
  })

  it('표에서 카드를 만들면 그 표를 근거로 싣는다', async () => {
    const user = userEvent.setup()
    modulusTables.mockResolvedValue([TABLE])
    createDmaTemperature.mockResolvedValue({ label: '저장 탄성률 1 Hz' })
    render(<ModulusTableSection testRunId="run-1" />)
    await user.click(await screen.findByRole('button', { name: '이 표로 카드 만들기' }))
    await waitFor(() =>
      expect(createDmaTemperature).toHaveBeenCalledWith({
        modulus_table_id: 'table-1',
        label: '저장 탄성률 1 Hz',
      })
    )
    expect(await screen.findByText(/카드 「저장 탄성률 1 Hz」 를 만들었습니다/)).toBeInTheDocument()
  })

  it('표를 지운다 — 확인 창을 거친다', async () => {
    const user = userEvent.setup()
    modulusTables.mockResolvedValue([TABLE])
    removeModulusTable.mockResolvedValue(undefined)
    render(<ModulusTableSection testRunId="run-1" />)
    await user.click(await screen.findByRole('button', { name: '이 표 지우기' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('카드가 근거로 든 표면 서버가 막습니다')
    await user.click(within(dialog).getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(removeModulusTable).toHaveBeenCalledWith('table-1'))
  })
})
