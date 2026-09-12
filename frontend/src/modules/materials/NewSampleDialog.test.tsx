/**
 * 시료 추가 — **지난 시료의 제조사·유통 경로를 물려받는다.**
 *
 * 시료마다 제조사·유통사·주 벤더·판매 유형을 다시 적는 것이 반복의 정체였다(VOC
 * 2026-09-13). 로트번호·생산일·밀도는 안 물려받는다 — 앞 둘은 새 시료의 정체성이고
 * 밀도는 그 로트에서 잰 값이다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NewSampleDialog } from '@/modules/materials/NewSampleDialog'

const createSample = vi.fn()
const samples = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/modules/materials/api')>()
  return {
    ...original,
    materialsApi: {
      createSample: (...args: unknown[]) => createSample(...args),
      samples: (...args: unknown[]) => samples(...args),
    },
  }
})

/** 기준정보 피커는 서버에 묻는다 — 여기서는 값이 들어왔는지만 본다. */
vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ label, value }: { label: string; value: string }) => (
    <label>
      {label}
      <input readOnly aria-label={label} value={value} />
    </label>
  ),
}))

const LATEST = {
  id: 's3',
  seq_no: 3,
  record_name: 'SPCC_-_1.0__03',
  manufacturer: '포스코',
  distributor: '삼성물산',
  primary_vendor: null,
  sales_type: '직거래',
  lot_no: 'L240601',
  production_date: '2026-06-01',
  density: 7850,
}

beforeEach(() => {
  createSample.mockReset()
  createSample.mockResolvedValue({ id: 's4', seq_no: 4 })
  samples.mockReset()
  samples.mockResolvedValue([{ ...LATEST, id: 's1', seq_no: 1, manufacturer: '옛 제조사' }, LATEST])
})

describe('시료 추가', () => {
  it('가장 최근 시료의 제조사·유통 경로를 채우고, 로트·생산일·밀도는 비워 둔다', async () => {
    render(<NewSampleDialog materialId="m1" open onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(await screen.findByLabelText('제조사')).toHaveValue('포스코')
    expect(screen.getByLabelText('유통사')).toHaveValue('삼성물산')
    expect(screen.getByLabelText('판매 유형')).toHaveValue('직거래')
    expect(screen.getByText(/SPCC_-_1\.0__03/)).toBeInTheDocument()
    expect(screen.getByLabelText('로트번호')).toHaveValue('')
    expect(screen.getByLabelText('생산일')).toHaveValue('')
    expect(screen.getByLabelText(/밀도/)).toHaveValue('')
  })

  it('물려받은 것을 비울 수 있고, 보낼 때는 물려받은 값이 실린다', async () => {
    const user = userEvent.setup()
    render(<NewSampleDialog materialId="m1" open onClose={vi.fn()} onCreated={vi.fn()} />)
    await screen.findByText(/채워 두었습니다/)

    await user.type(screen.getByLabelText('로트번호'), 'L240901')
    await user.click(screen.getByRole('button', { name: '추가' }))
    await waitFor(() => expect(createSample).toHaveBeenCalled())
    const [, payload] = createSample.mock.calls[0] as [string, Record<string, unknown>]
    expect(payload).toMatchObject({
      lot_no: 'L240901',
      manufacturer: '포스코',
      distributor: '삼성물산',
      sales_type: '직거래',
      density: null,
      production_date: null,
    })
  })

  it('첫 시료면 아무것도 안 채운다', async () => {
    samples.mockResolvedValue([])
    render(<NewSampleDialog materialId="m1" open onClose={vi.fn()} onCreated={vi.fn()} />)
    await screen.findByLabelText('제조사')
    expect(screen.queryByText(/채워 두었습니다/)).toBeNull()
    expect(screen.getByLabelText('제조사')).toHaveValue('')
  })

  it('비우기를 누르면 물려받은 칸이 빈다', async () => {
    const user = userEvent.setup()
    render(<NewSampleDialog materialId="m1" open onClose={vi.fn()} onCreated={vi.fn()} />)
    await screen.findByText(/채워 두었습니다/)
    await user.click(screen.getByRole('button', { name: '비우기' }))
    expect(screen.getByLabelText('제조사')).toHaveValue('')
    expect(screen.queryByText(/채워 두었습니다/)).toBeNull()
  })
})
