/**
 * 보유 장비 화면.
 *
 *   얼굴은 장비명 — 자산번호는 아래 작게, 없으면 「자산번호 없음」
 *   조직은 사업부와 함께 보인다(부모를 타고 나온 것)
 *   교정은 「모른다」 를 「만료」 로 안 적는다
 *   붙여넣기는 드라이런이 먼저고, **새로 생길 기준정보를 경고로 보여 준다**
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EquipmentBulkDialog } from '@/modules/equipment/EquipmentBulkDialog'
import EquipmentPage from '@/modules/equipment/EquipmentPage'
import { calibrationState } from '@/modules/equipment/api'

const units = vi.fn()
const summary = vi.fn()
const bulk = vi.fn()

vi.mock('@/modules/equipment/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/equipment/api')>()),
  equipmentApi: {
    units: (...args: unknown[]) => units(...args),
    summary: (...args: unknown[]) => summary(...args),
    bulk: (...args: unknown[]) => bulk(...args),
  },
}))

const DMA = {
  id: 'u1',
  asset_no: 'A-2019-0142',
  name: '생기연 DMA',
  ownership: 'internal',
  status: 'active',
  vendor: 'TA Instruments',
  model: 'Q800',
  serial_no: null,
  instrument_id: null,
  instrument_type: null,
  instrument_term: null,
  org: { id: 'o1', label: '생기연', parent_id: 'd1', parent_label: '모빌리티' },
  lab: { id: 'l1', label: '2공장 3층', parent_id: null, parent_label: null },
  location_detail: '3번 벤치',
  workspace_id: null,
  owner_name: null,
  owner_contact: null,
  commissioned_on: null,
  retired_on: null,
  attributes: {},
  notes: null,
  last_calibrated_on: null,
  calibration_valid_until: null,
  part_count: 2,
  created_at: '2026-09-07T00:00:00Z',
  updated_at: '2026-09-07T00:00:00Z',
}
const CHAMBER = { ...DMA, id: 'u2', name: '대형 챔버', asset_no: null, org: null, part_count: 0 }

function show() {
  return render(
    <MemoryRouter>
      <EquipmentPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  units.mockResolvedValue({ items: [DMA, CHAMBER], total: 2, limit: 100, offset: 0 })
  summary.mockResolvedValue({ total: 2, by_division: [], by_org: [], by_lab: [] })
})

describe('목록', () => {
  it('장비명이 앞에 서고 자산번호는 아래에 붙는다', async () => {
    show()
    expect(await screen.findByText('생기연 DMA')).toBeInTheDocument()
    expect(screen.getByText('A-2019-0142')).toBeInTheDocument()
  })

  it('자산번호가 없으면 그렇다고 적는다', async () => {
    // **비워 둘 수 있는 칸이다** — 스티커 없는 장비를 못 넣게 하면 가짜 번호가 생긴다.
    show()
    expect(await screen.findByText('자산번호 없음')).toBeInTheDocument()
  })

  it('조직에 사업부가 함께 보인다', async () => {
    // 장비는 조직만 가리키고 사업부는 부모를 타고 나온다.
    show()
    expect(await screen.findByText('모빌리티 › 생기연')).toBeInTheDocument()
  })
})

describe('교정 표시', () => {
  it('유효기간을 모르면 만료로 적지 않는다', () => {
    // **「모른다」 를 「만료」 로 읽으면 멀쩡한 장비가 빨갛게 물든다.**
    expect(calibrationState(null)).toEqual({ tone: 'none', text: '기간 없음' })
  })

  it('지난 것과 임박한 것을 가른다', () => {
    const day = 24 * 60 * 60 * 1000
    expect(calibrationState(new Date(Date.now() - 3 * day).toISOString()).tone).toBe('over')
    expect(calibrationState(new Date(Date.now() + 5 * day).toISOString()).tone).toBe('due')
    expect(calibrationState(new Date(Date.now() + 300 * day).toISOString()).tone).toBe('ok')
  })
})

describe('붙여넣기', () => {
  it('드라이런이 먼저고 새로 생길 기준정보를 경고한다', async () => {
    // **오타 하나가 새 조직을 만든다** — 이 화면의 가장 흔한 사고다.
    bulk.mockResolvedValue({
      dry_run: true,
      created: 1,
      skipped: 0,
      errors: 0,
      rows: [{ index: 0, name: '생기연 DMA', outcome: 'create', new_terms: ['조직: 생기연'] }],
    })
    render(<EquipmentBulkDialog onDone={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /먼저 확인/ }))
    expect(await screen.findByText('조직: 생기연')).toBeInTheDocument()
    expect(screen.getByText(/기준정보에 새로 생깁니다/)).toBeInTheDocument()
    expect(bulk).toHaveBeenCalledWith(expect.anything(), true)
  })

  it('확인 전에는 등록을 못 누른다', () => {
    render(<EquipmentBulkDialog onDone={vi.fn()} />)
    expect(screen.getByRole('button', { name: '등록' })).toBeDisabled()
  })
})
