/**
 * 곡선 · 표 한 벌 넣기 — **붙여넣은 표가 그대로 한 벌이 되는가**(2026-10-22, ADR 0067).
 *
 *   축은 고른 물성의 조건축에서      온도면 °C 로 받고 서버가 K 로
 *   미리보기 뒤에야 넣는다           저장될 점을 그래프로 보고 나서
 *   붙여넣기는 머리 줄을 건너뛴다     엑셀에서 머리까지 복사해도 된다
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SeriesDialog } from '@/modules/catalog/SeriesDialog'
import { parseConditions, parseRows } from '@/modules/catalog/catalogForms'
import type { CatalogMaterialDetail } from '@/modules/catalog/api'

const resolveProperty = vi.fn()
const previewSeries = vi.fn()
const createSeries = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    resolveProperty: (...args: unknown[]) => resolveProperty(...args),
    previewSeries: (...args: unknown[]) => previewSeries(...args),
    createSeries: (...args: unknown[]) => createSeries(...args),
  },
}))

const DETAIL = { id: 'm1', name: 'SAC305', values: [], series: [] } as unknown as CatalogMaterialDetail

const CANDIDATE = {
  key: 'mechanical.youngs_modulus',
  name: '탄성계수',
  domain: 'mechanical',
  si_unit: 'Pa',
  symbol: 'E',
  value_count: 10,
  internal_items: [],
  measured_keys: [],
  parameterized: false,
  terms: [],
  matched_by: 'name',
  matched_text: '탄성계수',
  notes: [],
  deprecated: false,
  condition_axes: ['temperature_k', 'strain_rate_s'],
}

const MADE = {
  series: {
    id: 's1',
    kind: 'curve',
    label: '온도별 탄성계수',
    x_key: 'temperature_k',
    x_unit: 'K',
    columns: [{ property_key: 'mechanical.youngs_modulus', property_name: '탄성계수', unit: 'Pa' }],
    model: null,
    point_count: 2,
    conditions: null,
    method: 'digitized',
    quality_tier: 2,
    source: null,
    source_detail: null,
    notes: null,
    created_by: '홍길동',
    created_at: '2026-10-22T00:00:00Z',
  },
  points: [
    { property_key: 'mechanical.youngs_modulus', value: 5e10, unit: 'Pa', x: 298.15 },
    { property_key: 'mechanical.youngs_modulus', value: 4.5e10, unit: 'Pa', x: 373.15 },
  ],
  converted: ['탄성계수: GPa → Pa (2점)'],
}

beforeEach(() => {
  vi.clearAllMocks()
  resolveProperty.mockResolvedValue({ ambiguous: false, candidates: [CANDIDATE] })
  previewSeries.mockResolvedValue(MADE)
  createSeries.mockResolvedValue(MADE)
})

describe('곡선 · 표 입력', () => {
  it('물성을 고르면 그 조건축이 축 후보가 되고, 미리보기 뒤에 넣는다', async () => {
    const onDone = vi.fn()
    render(<SeriesDialog detail={DETAIL} open onClose={vi.fn()} onDone={onDone} />)
    fireEvent.change(screen.getByLabelText('곡선 물성 찾기'), { target: { value: '탄성' } })
    fireEvent.click(await screen.findByRole('button', { name: /탄성계수/ }))

    const axis = screen.getByLabelText('축') as HTMLSelectElement
    expect([...axis.options].map((one) => one.value)).toEqual(['temperature_k', 'strain_rate_s'])
    expect(axis.value).toBe('temperature_k')
    // 온도는 °C 로 받는다 — 서버가 K 로 바꾼다.
    expect(screen.getByLabelText('축 단위')).toHaveValue('°C')

    fireEvent.change(screen.getByLabelText('탄성계수 단위'), { target: { value: 'GPa' } })
    fireEvent.change(screen.getByLabelText(/값 붙여넣기/), {
      target: { value: '온도\t탄성계수\n25\t50\n100\t45' },
    })
    fireEvent.change(screen.getByLabelText('출처 제목'), { target: { value: 'SAC305 고온 인장' } })

    const save = screen.getByRole('button', { name: '넣기' })
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '미리보기' }))
    await waitFor(() => expect(previewSeries).toHaveBeenCalledTimes(1))
    const [materialId, payload] = previewSeries.mock.calls[0]
    expect(materialId).toBe('m1')
    expect(payload).toMatchObject({
      kind: 'curve',
      x_key: 'temperature_k',
      x_unit: '°C',
      columns: [{ property_key: 'mechanical.youngs_modulus', unit: 'GPa' }],
      rows: [
        [25, 50],
        [100, 45],
      ],
      source: { title: 'SAC305 고온 인장' },
    })
    expect(await screen.findByText(/점 2개를 넣습니다/)).toBeInTheDocument()
    expect(screen.getByText(/GPa → Pa/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '넣기' }))
    await waitFor(() => expect(createSeries).toHaveBeenCalledWith('m1', payload))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(expect.stringContaining('점 2개')))
  })

  it('칸을 바꾸면 미리보기가 지워진다 — 낡은 그림을 보고 넣지 않게', async () => {
    render(<SeriesDialog detail={DETAIL} open onClose={vi.fn()} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('곡선 물성 찾기'), { target: { value: '탄성' } })
    fireEvent.click(await screen.findByRole('button', { name: /탄성계수/ }))
    fireEvent.change(screen.getByLabelText(/값 붙여넣기/), { target: { value: '25\t50\n100\t45' } })
    fireEvent.change(screen.getByLabelText('출처 제목'), { target: { value: '논문' } })
    fireEvent.click(screen.getByRole('button', { name: '미리보기' }))
    expect(await screen.findByText(/점 2개를 넣습니다/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/값 붙여넣기/), { target: { value: '25\t50\n150\t40' } })
    await waitFor(() => expect(screen.queryByText(/점 2개를 넣습니다/)).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '넣기' })).toBeDisabled()
  })
})

describe('산점 · 라이선스 (ADR 0068)', () => {
  it('산점이면 같은 x 를 그대로 보내고 줄 끝 칸 1 을 런아웃으로, 라이선스를 출처에 싣는다', async () => {
    render(<SeriesDialog detail={DETAIL} open onClose={vi.fn()} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('곡선 물성 찾기'), { target: { value: '탄성' } })
    fireEvent.click(await screen.findByRole('button', { name: /탄성계수/ }))
    fireEvent.click(screen.getByLabelText(/산점/))
    fireEvent.change(screen.getByLabelText(/값 붙여넣기/), {
      target: { value: '25\t50\n100\t45\n100\t44\t1' },
    })
    fireEvent.change(screen.getByLabelText('출처 제목'), { target: { value: '논문' } })
    fireEvent.change(screen.getByLabelText('라이선스'), { target: { value: 'CC-BY-4.0' } })
    fireEvent.click(screen.getByRole('button', { name: '미리보기' }))
    await waitFor(() => expect(previewSeries).toHaveBeenCalledTimes(1))
    const [, payload] = previewSeries.mock.calls[0]
    expect(payload).toMatchObject({
      kind: 'scatter',
      rows: [
        [25, 50],
        [100, 45],
        [100, 44],
      ],
      row_conditions: [{}, {}, { runout: true }],
      source: { title: '논문', license: 'CC-BY-4.0' },
    })
  })
})

describe('붙여넣기 읽기', () => {
  it('탭 · 쉼표 · 공백으로 가르고, 머리 줄을 건너뛰고, 빈 칸은 null', () => {
    expect(parseRows('T\tE\n25\t200\n100\t\n200,180')).toEqual([
      [25, 200],
      [100, null],
      [200, 180],
    ])
    expect(parseRows('1 2\n3 4')).toEqual([
      [1, 2],
      [3, 4],
    ])
  })

  it('머리 뒤에 수가 아닌 칸이 있으면 그 줄을 말한다', () => {
    expect(() => parseRows('25\t200\n100\tabc')).toThrow(/100\tabc/)
  })

  it('공통 조건은 「키=값」 — 수로 읽히면 수로', () => {
    expect(parseConditions('frequency_hz=1, specimen=bar')).toEqual({
      frequency_hz: 1,
      specimen: 'bar',
    })
  })
})
