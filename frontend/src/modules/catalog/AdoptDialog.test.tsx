/**
 * 카탈로그에서 채우기 — **병합이 정확해야 한다.**
 *
 *   기존 선언 줄은 살아남는다        통째 교체 PATCH 라 되보내야 한다
 *   온도별 값은 한 줄의 점들이 된다    CTE 2개 → 항목 1줄 · 점 2개
 *   SI 그대로 · input_unit 비움      변환 규칙이 화면에 생기면 안 된다
 *   출처·등급이 따라간다             reference 에 문헌·tier 표기
 *   못 담는 값은 목록에 없다          음의 포아송비(서버 제약 밖)
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdoptDialog } from '@/modules/catalog/AdoptDialog'
import type { CatalogMaterialDetail } from '@/modules/catalog/api'

const get = vi.fn()
const patch = vi.fn()

vi.mock('@/shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    patch: (...args: unknown[]) => patch(...args),
  },
}))

function value(over: Record<string, unknown>) {
  return {
    id: crypto.randomUUID(),
    property_name: '',
    domain: 'mechanical',
    symbol: null,
    value_text: null,
    unit: 'Pa',
    uncertainty: null,
    conditions: null,
    method: 'measured',
    quality_tier: 1,
    source: {
      id: crypto.randomUUID(),
      kind: 'journal',
      doi: '10.1/x',
      url: null,
      title: '어느 논문',
      year: 2020,
      publisher: null,
      license: null,
    },
    source_detail: null,
    notes: null,
    representative: true,
    n_candidates: 1,
    separated_by: null,
    ...over,
  }
}

const DETAIL = {
  id: crypto.randomUUID(),
  name: 'SUS304',
  material_code: null,
  category: 'metal',
  description: null,
  subsystem: null,
  role: null,
  manufacturer: null,
  material_class: null,
  grade: null,
  attributes: {},
  values: [
    value({
      property_key: 'mechanical.youngs_modulus',
      value_num: 1.93e11,
      conditions: { temperature_k: 296.15 },
    }),
    value({
      property_key: 'thermal.expansion_linear',
      value_num: 1.7e-5,
      unit: '1/K',
      conditions: { temperature_k: 373.15 },
      n_candidates: 2,
    }),
    value({
      property_key: 'thermal.expansion_linear',
      value_num: 1.9e-5,
      unit: '1/K',
      conditions: { temperature_k: 473.15 },
      representative: false,
      separated_by: '온도',
      n_candidates: 2,
    }),
    value({ property_key: 'physical.density', value_num: 7930, unit: 'kg/m^3' }),
    // 음의 포아송비 — 서버 제약(0 ≤ ν < 0.5) 밖이라 목록에 오르면 안 된다.
    value({ property_key: 'mechanical.poisson_ratio', value_num: -0.2, unit: '1' }),
  ],
} as unknown as CatalogMaterialDetail

const TARGET = {
  id: '33333333-3333-3333-3333-333333333333',
  record_name: 'SGARC440 1.2t',
  alias: null,
  density: null,
  poisson_ratio: null,
  declared_properties: [
    {
      item: '비열',
      points: [{ temperature_k: null, value_si: 460, value: 460 }],
      input_unit: null,
      scale: null,
      source: 'literature',
      reference: '기존 핸드북',
      note: null,
    },
  ],
}

/** 기준정보의 물성 항목 층 — 항복강도·인장강도는 시료에 붙는다(실물 규율). */
const PROPERTY_ITEMS = [
  { item: '탄성계수', level: '재료' },
  { item: '전단탄성계수', level: '재료' },
  { item: '선팽창계수(CTE)', level: '재료' },
  { item: '열전도율', level: '재료' },
  { item: '비열', level: '재료' },
  { item: '항복강도', level: '시료' },
  { item: '인장강도', level: '시료' },
]

/** 서버의 매핑 — 기준정보 물성 매핑에서 이은 것. **화면이 표를 안 든다.** */
const ADOPTABLE = [
  { property_key: 'mechanical.youngs_modulus', place: 'declared', item: '탄성계수' },
  { property_key: 'mechanical.shear_modulus', place: 'declared', item: '전단탄성계수' },
  { property_key: 'mechanical.yield_strength', place: 'declared', item: '항복강도' },
  { property_key: 'mechanical.tensile_strength', place: 'declared', item: '인장강도' },
  { property_key: 'mechanical.elongation_at_break', place: 'declared', item: '연신율' },
  { property_key: 'thermal.specific_heat', place: 'declared', item: '비열' },
  { property_key: 'thermal.conductivity', place: 'declared', item: '열전도율' },
  { property_key: 'thermal.expansion_linear', place: 'declared', item: '선팽창계수(CTE)' },
  { property_key: 'physical.density', place: 'column', field: 'density' },
  { property_key: 'mechanical.poisson_ratio', place: 'column', field: 'poisson_ratio' },
]

function mockGets(searchItems: unknown[] = [TARGET]) {
  get.mockImplementation((url: unknown) => {
    if (String(url).startsWith('/materials/property-items')) return Promise.resolve(PROPERTY_ITEMS)
    if (String(url).startsWith('/catalog/properties/adoptable')) return Promise.resolve(ADOPTABLE)
    return Promise.resolve({ total: 1, limit: 8, offset: 0, items: searchItems })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGets()
  patch.mockResolvedValue(TARGET)
})

async function pickTarget() {
  render(<AdoptDialog detail={DETAIL} open onClose={() => {}} />)
  await userEvent.click(await screen.findByRole('button', { name: /SGARC440/ }))
}

describe('병합이 정확해야 한다', () => {
  it('기존 줄을 되보내고, 온도별 값은 한 줄의 점들로 담는다', async () => {
    await pickTarget()
    // CTE 대안(473.15K)도 골라 넣는다 — 온도점이 둘이 된다.
    const boxes = screen.getAllByRole('checkbox')
    for (const box of boxes) {
      if (!(box as HTMLInputElement).checked) await userEvent.click(box)
    }
    await userEvent.click(screen.getByRole('button', { name: /추가/ }))

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
    const [path, body] = patch.mock.calls[0] as [string, Record<string, unknown>]
    expect(path).toBe(`/materials/${TARGET.id}`)

    const rows = body.declared_properties as Array<Record<string, unknown>>
    // 기존 비열 줄이 살아 있다.
    expect(rows.some((row) => row.item === '비열' && row.reference === '기존 핸드북')).toBe(true)
    // CTE 는 항목 1줄 · 온도점 2개(오름차순).
    const cte = rows.find((row) => row.item === '선팽창계수(CTE)') as {
      points: Array<{ temperature_k: number | null; value: number }>
      input_unit?: string | null
      reference: string
    }
    expect(cte.points).toEqual([
      { temperature_k: 373.15, value: 1.7e-5 },
      { temperature_k: 473.15, value: 1.9e-5 },
    ])
    // input_unit 비움 = 정본 SI — 변환 없이 그대로.
    expect(cte.input_unit).toBeUndefined()
    expect(cte.reference).toContain('어느 논문')
    expect(cte.reference).toContain('실측')
    // 밀도는 기본 칸으로, SI 단위 명시.
    expect(body.density).toBe(7930)
    expect(body.density_unit).toBe('kg/m3')
    // 음의 포아송비는 애초에 목록에 없었으니 patch 에도 없다.
    expect(body.poisson_ratio).toBeUndefined()
  })

  it('기본 선택은 대표값이고, 못 담는 값(음의 포아송비)은 목록에 없다', async () => {
    await pickTarget()
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
    // 대표 3개(영률·CTE 373K·밀도)만 기본 체크, CTE 대안은 해제 상태.
    expect(boxes).toHaveLength(4)
    expect(boxes.filter((box) => box.checked)).toHaveLength(3)
    expect(screen.queryByText('포아송비')).toBeNull()
  })

  it('이미 있는 항목이면 「담으면 교체」 를 말한다', async () => {
    const withYoungs = {
      ...TARGET,
      declared_properties: [
        ...TARGET.declared_properties,
        {
          item: '탄성계수',
          points: [{ temperature_k: null, value_si: 2e11, value: 200 }],
          input_unit: 'GPa',
          scale: null,
          source: 'datasheet',
          reference: '밀시트',
          note: null,
        },
      ],
    }
    mockGets([withYoungs])
    await pickTarget()
    expect(await screen.findByText(/이미 있음 — 담으면 교체/)).toBeInTheDocument()
  })

  it('시료 층 항목도 문헌 공칭값은 담긴다 — 벤더 시트까지(밀시트만 잠긴다)', async () => {
    // 실측(2026-09-06): 항복강도 하나가 섞이자 PATCH 전체가 422 — 9건이 무산됐다.
    // 서버 규칙(ADR 0016): 층을 가르는 것은 값의 성격 — 문헌 공칭값은 재료에.
    const withStrength = {
      ...DETAIL,
      values: [
        ...DETAIL.values,
        // journal 출처 — 공칭값이라 담긴다.
        value({ property_key: 'mechanical.yield_strength', value_num: 2.05e8 }),
        // 벤더 데이터시트 — Grade 스펙이라 담긴다(2026-09-06 출처 분리 후).
        value({
          property_key: 'mechanical.tensile_strength',
          value_num: 5.2e8,
          source: {
            id: crypto.randomUUID(),
            kind: 'datasheet',
            doi: null,
            url: null,
            title: '벤더 시트',
            year: null,
            publisher: 'Vendor',
            license: null,
          },
        }),
      ],
    } as unknown as CatalogMaterialDetail
    render(<AdoptDialog detail={withStrength} open onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /SGARC440/ }))

    // 둘 다 열려 있다 — 문헌(journal)도, 벤더 제품시트(datasheet)도 Grade 공칭값.
    for (const label of ['항복강도', '인장강도']) {
      const row = screen.getByText(label).closest('label') as HTMLElement
      expect((row.querySelector('input') as HTMLInputElement).disabled).toBe(false)
    }

    await userEvent.click(screen.getByRole('button', { name: /추가/ }))
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
    const [, body] = patch.mock.calls[0] as [string, Record<string, unknown>]
    const rows = body.declared_properties as Array<Record<string, unknown>>
    const yield_ = rows.find((one) => one.item === '항복강도')
    expect(yield_).toBeDefined()
    expect(yield_?.source).toBe('literature')
    const uts = rows.find((one) => one.item === '인장강도')
    expect(uts?.source).toBe('datasheet')
  })
})

/**
 * **주파수를 타는 항목**(2026-10-01). 선언 물성 PATCH 는 통째 교체라, 되보낼 때 조건을 하나라도
 * 떨어뜨리면 그 조건은 담기 한 번에 조용히 사라진다 — 온도만 옮기던 코드가 그랬을 것이다.
 */
describe('주파수를 타는 항목', () => {
  const WITH_DK_ITEMS = [
    ...PROPERTY_ITEMS,
    { item: '비유전율', level: '재료', condition_key: 'frequency_hz' },
  ]
  const WITH_DK_ADOPTABLE = [
    ...ADOPTABLE,
    { property_key: 'electrical.dielectric_constant', place: 'declared', item: '비유전율' },
  ]

  function mockWith(searchItems: unknown[]) {
    get.mockImplementation((url: unknown) => {
      if (String(url).startsWith('/materials/property-items')) return Promise.resolve(WITH_DK_ITEMS)
      if (String(url).startsWith('/catalog/properties/adoptable'))
        return Promise.resolve(WITH_DK_ADOPTABLE)
      return Promise.resolve({ total: 1, limit: 8, offset: 0, items: searchItems })
    })
  }

  it('기존 유전율 줄의 주파수를 되보낸다 — 다른 값을 담아도 안 빠진다', async () => {
    const withDk = {
      ...TARGET,
      declared_properties: [
        {
          item: '비유전율',
          points: [{ temperature_k: null, frequency_hz: 1e9, wavelength_m: null, value_si: 3.6, value: 3.6 }],
          input_unit: '1',
          scale: null,
          source: 'datasheet',
          reference: 'Isola 370HR',
          note: null,
        },
      ],
    }
    mockWith([withDk])
    await pickTarget()
    await userEvent.click(await screen.findByRole('button', { name: /추가/ }))

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
    const rows = (patch.mock.calls[0][1] as { declared_properties: Array<Record<string, unknown>> })
      .declared_properties
    const dk = rows.find((row) => row.item === '비유전율') as {
      points: Array<{ frequency_hz: number | null }>
    }
    expect(dk.points[0].frequency_hz).toBe(1e9)
  })

  it('문헌의 유전율은 주파수 점으로 담고, 섭씨 온도도 읽으며, 측정 온도가 다르면 비우고 적는다', async () => {
    mockWith([TARGET])
    const withDk = {
      ...DETAIL,
      values: [
        value({
          property_key: 'electrical.dielectric_constant',
          domain: 'electrical',
          unit: '1',
          value_num: 3.6,
          conditions: { frequency_hz: 1e9, temperature_c: 23 },
        }),
        value({
          property_key: 'electrical.dielectric_constant',
          domain: 'electrical',
          unit: '1',
          value_num: 3.8,
          conditions: { frequency_hz: 1e6, temperature_c: 25 },
          representative: false,
          separated_by: '주파수',
          n_candidates: 2,
        }),
      ],
    } as unknown as CatalogMaterialDetail
    render(<AdoptDialog detail={withDk} open onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /SGARC440/ }))
    for (const box of screen.getAllByRole('checkbox')) {
      if (!(box as HTMLInputElement).checked) await userEvent.click(box)
    }
    await userEvent.click(screen.getByRole('button', { name: /추가/ }))

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
    const rows = (patch.mock.calls[0][1] as { declared_properties: Array<Record<string, unknown>> })
      .declared_properties
    const dk = rows.find((row) => row.item === '비유전율') as {
      points: Array<{ frequency_hz: number; temperature_k: number | null; value: number }>
      note: string
    }
    // 주파수 오름차순 — 1 MHz 다음 1 GHz.
    expect(dk.points.map((point) => point.frequency_hz)).toEqual([1e6, 1e9])
    // 23 ℃ 와 25 ℃ — 측정 온도가 달라 비웠고, 그 사실을 메모에 남겼다.
    expect(dk.points.every((point) => point.temperature_k === null)).toBe(true)
    expect(dk.note).toContain('측정 온도가 달라')
  })
})
