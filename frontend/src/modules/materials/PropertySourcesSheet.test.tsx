/**
 * 값 출처 — **SI 로 받아 표시 단위로 적는다**(2026-09-24).
 *
 *   두께 0.001 m        → 1 mm
 *   밀도 7850 kg/m³     → 7.850e-9 tonne/mm³
 *   푸아송비(무차원)     → 단위 없이
 *
 * 전에는 서버가 표시 단위로 바꿔 `display_unit` 과 함께 줬다. 이제 바꾸는 것은 화면이고,
 * 다른 화면과 같은 표(`shared/units`)를 쓴다 — SI 를 그대로 적으면 두께가 0.001 로 보인다.
 */

import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PropertySourcesSheet } from '@/modules/materials/PropertySourcesSheet'

const propertySources = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    propertySources: (...args: unknown[]) => propertySources(...args),
  },
}))

function row(key: string, label: string, value: number | null, si_unit: string) {
  return {
    key,
    label,
    value,
    si_unit,
    level: 'material',
    origin: null,
    status: value === null ? 'missing' : 'ok',
    used_for: '쓰임',
    edit_hint: null,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('값 출처', () => {
  it('SI 로 온 값을 표시 단위로 적는다', async () => {
    propertySources.mockResolvedValue({
      material_id: 'm1',
      material_name: 'SECC_MDOI_1.0',
      rows: [
        row('spec_thickness', '규격 두께', 0.001, 'm'),
        row('density', '밀도', 7850, 'kg/m3'),
        row('poisson_ratio', '푸아송비', 0.3, ''),
        row('youngs_modulus', '탄성계수', null, 'Pa'),
      ],
    })
    render(<PropertySourcesSheet materialId="m1" open onClose={() => {}} />)

    expect(await screen.findByText('1 mm')).toBeInTheDocument()
    expect(screen.getByText('7.850e-9 tonne/mm³')).toBeInTheDocument()
    expect(screen.getByText('0.3')).toBeInTheDocument()
    // SI 숫자가 그대로 새지 않는다.
    expect(screen.queryByText(/^0\.001/)).toBeNull()
    expect(screen.queryByText(/^7850/)).toBeNull()
  })
})
