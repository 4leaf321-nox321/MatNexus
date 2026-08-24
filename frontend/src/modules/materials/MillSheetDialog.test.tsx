/**
 * 밀시트 — 적은 값과 잰 값을 한 자리에(ADR 0016).
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   판정하지 않는다        차이를 비율로 낼 뿐, 맞다·틀리다를 말하지 않는다
 *   잰 적이 없으면 말한다   줄을 비우면 사람은 잰 값이 0 이라고 읽는다
 *   층을 서버에 묻는다      시료에 넣을 수 있는 항목만 서버가 갈라 준다
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MillSheetDialog } from '@/modules/materials/MillSheetDialog'
import type { Sample } from '@/modules/materials/api'

const millCheck = vi.fn()
const propertyItems = vi.fn()
const updateSample = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    millCheck: (...args: unknown[]) => millCheck(...args),
    propertyItems: (...args: unknown[]) => propertyItems(...args),
    updateSample: (...args: unknown[]) => updateSample(...args),
  },
}))

const SAMPLE = {
  id: 's-1',
  record_name: 'SECC_MDOI_1.0__01',
  declared_properties: [],
} as unknown as Sample

const ROWS = [
  {
    item: '인장강도',
    label: '인장강도',
    declared: 400e6,
    declared_unit: 'MPa',
    reference: 'MTC-2024-0812',
    measured: 412e6,
    measured_count: 3,
    si_unit: 'Pa',
    difference: 0.03,
    note: null,
  },
  {
    item: '연신율',
    label: '연신율',
    declared: 0.32,
    declared_unit: '%',
    reference: 'MTC-2024-0812',
    measured: null,
    measured_count: 0,
    si_unit: '1',
    difference: null,
    note: '우리가 재는 값으로 이어져 있지 않습니다.',
  },
]

function dialog() {
  render(
    <MillSheetDialog sample={SAMPLE} open onClose={vi.fn()} onSaved={vi.fn()} />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  millCheck.mockResolvedValue({ sample_name: SAMPLE.record_name, rows: ROWS })
  propertyItems.mockResolvedValue([])
})

describe('밀시트', () => {
  it('밀시트 값과 잰 값을 나란히 놓는다', async () => {
    dialog()
    expect(await screen.findByText('412 MPa')).toBeInTheDocument()
    expect(screen.getByText('400 MPa')).toBeInTheDocument()
    expect(screen.getByText('n=3')).toBeInTheDocument()
  })

  it('판정하지 않고 차이만 낸다', async () => {
    // **몇 %부터 문제인지는 규격과 용도가 정한다.** 화면이 「합격」을 말하면
    // 그 판정 기준이 어디에도 안 적힌 채로 굳는다.
    dialog()
    expect(await screen.findByText('+3.0%')).toBeInTheDocument()
    expect(screen.queryByText(/합격|불합격|맞음|틀림/)).not.toBeInTheDocument()
  })

  it('잰 적이 없으면 왜 없는지 말한다', async () => {
    // **조용히 빼지 않는다.** 줄이 비면 사람은 잰 값이 0 이라고 읽거나,
    // 적은 값이 사라진 줄 안다.
    dialog()
    expect(
      await screen.findByText(/우리가 재는 값으로 이어져 있지 않습니다/)
    ).toBeInTheDocument()
  })

  it('시료 층 항목만 묻는다', async () => {
    // **화면이 층을 판정하지 않는다.** 탄성계수를 시료에 적으면 같은 값을
    // 로트 수만큼 적게 되고, 그중 하나만 고쳐진다.
    dialog()
    await waitFor(() => expect(propertyItems).toHaveBeenCalledWith('시료'))
  })
})
