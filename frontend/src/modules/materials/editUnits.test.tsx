/**
 * 수정 창 — **API 의 SI 를 표시 단위로 받아, 표시 단위를 적어 되보낸다**(2026-09-24).
 *
 * 밀도·두께가 REST 에서 SI 가 되었다(ADR 0036 D4). 화면이 그 값을 그대로 상자에 넣으면 라벨은
 * tonne/mm³ 인데 7850 이 서고, 고치지 않고 저장해도 10¹² 배가 된다 — 2026-09-05 에 실제로 났던
 * 사고(라벨과 값의 단위가 갈림)의 거울이다. 그래서 보는 것은 왕복 하나다: 상자에 무엇이 서고,
 * 고치지 않고 저장하면 무엇이 가나.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EditMaterialDialog } from '@/modules/materials/EditMaterialDialog'
import { EditSampleDialog } from '@/modules/materials/EditSampleDialog'
import type { Material, Sample } from '@/modules/materials/api'

const update = vi.fn()
const updateSample = vi.fn()
const previewName = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/modules/materials/api')>()
  return {
    ...original,
    materialsApi: {
      update: (...args: unknown[]) => update(...args),
      updateSample: (...args: unknown[]) => updateSample(...args),
      previewName: (...args: unknown[]) => previewName(...args),
    },
  }
})

/** 기준정보 피커는 서버에 묻는다 — 여기서는 단위만 본다. */
vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ label, value }: { label: string; value: string }) => (
    <label>
      {label}
      <input readOnly aria-label={label} value={value} />
    </label>
  ),
}))
vi.mock('@/modules/vocabulary/VocabularyMultiField', () => ({
  VocabularyMultiField: () => null,
}))

//: API 가 주는 모양 그대로 — **SI 다.**
const MATERIAL = {
  id: 'm1',
  record_name: 'SECC_MDOI_1.2',
  family: 'Metal',
  category: 'Steel',
  grade: 'SECC',
  details: 'MDOI',
  spec_thickness: 0.0012,
  spec_thickness_unit: 'm',
  density: 7850,
  density_unit: 'kg/m3',
  poisson_ratio: 0.3,
  applied_products: [],
  applied_parts: [],
  alias: null,
  note: null,
} as unknown as Material

const SAMPLE = {
  id: 's1',
  record_name: 'SECC_MDOI_1.2__01',
  lot_no: 'L1',
  alias: null,
  manufacturer: null,
  distributor: null,
  primary_vendor: null,
  sales_type: null,
  production_date: null,
  density: 7900,
  density_unit: 'kg/m3',
  note: null,
} as unknown as Sample

beforeEach(() => {
  vi.clearAllMocks()
  update.mockResolvedValue({})
  updateSample.mockResolvedValue({})
  previewName.mockResolvedValue({ record_name: 'SECC_MDOI_1.2', taken: false })
})

describe('재료 수정 창', () => {
  it('SI 를 라벨의 단위로 보이고, 고치지 않고 저장하면 같은 값이 그 단위를 달고 간다', async () => {
    const user = userEvent.setup()
    render(<EditMaterialDialog material={MATERIAL} open onClose={() => {}} onDone={() => {}} />)

    // 0.0012 나 7850 이 서면 그것이 사고다 — 라벨은 mm · tonne/mm³ 다.
    expect(screen.getByLabelText(/스펙 두께/)).toHaveValue('1.2')
    expect(screen.getByLabelText(/밀도/)).toHaveValue('7.85e-9')

    await user.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, body] = update.mock.calls[0] as [string, Record<string, unknown>]
    expect(body).toMatchObject({
      spec_thickness: 1.2,
      spec_thickness_unit: 'mm',
      density: 7.85e-9,
      density_unit: 'tonne/mm3',
    })
  })
})

describe('시료 수정 창', () => {
  it('로트 밀도도 같다 — SI 를 tonne/mm³ 로 보이고 그 단위를 달고 간다', async () => {
    const user = userEvent.setup()
    render(<EditSampleDialog sample={SAMPLE} open onClose={() => {}} onSaved={() => {}} />)

    expect(screen.getByLabelText(/밀도/)).toHaveValue('7.9e-9')

    await user.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(updateSample).toHaveBeenCalled())
    const [, body] = updateSample.mock.calls[0] as [string, Record<string, unknown>]
    expect(body).toMatchObject({ density: 7.9e-9, density_unit: 'tonne/mm3' })
  })
})
