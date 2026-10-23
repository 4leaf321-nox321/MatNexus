/**
 * 문헌 재료 상세 — **진 후보를 숨기지 않는다.**
 *
 *   대표가 먼저, 후보 수와 함께     「대표값 · 후보 2」
 *   진 후보는 밀린 자리와 함께      「대안 · 등급」
 *   가정값은 가정이라고 말한다      tier4 + assumption → 「가정」 배지 (제외는 안 한다)
 *   출처가 값 옆에 산다            제목·연도·DOI 링크
 *   직접 넣은 값은 그렇게 보인다     「직접 넣음 · 누구」, 넣은 사람만 지우기 단추
 *   요약 + 탭(2026-10-22)            물성 하나에 한 줄 · 곡선 · 출처 — 값 줄은 「전체 값」 탭
 */

import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogMaterialPage from '@/modules/catalog/CatalogMaterialPage'

const material = vi.fn()
const deleteValue = vi.fn()
const deleteSeries = vi.fn()
const seriesPoints = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    summary: vi.fn(),
    materials: vi.fn(),
    material: (...args: unknown[]) => material(...args),
    deleteValue: (...args: unknown[]) => deleteValue(...args),
    deleteSeries: (...args: unknown[]) => deleteSeries(...args),
    seriesPoints: (...args: unknown[]) => seriesPoints(...args),
  },
}))

let me = { id: 'u1', email: 'hong', display_name: '홍길동', is_system_admin: false, memberships: [] }
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: me, reload: vi.fn(), logout: vi.fn() }),
  useMaybeAuth: () => ({ user: me, reload: vi.fn(), logout: vi.fn() }),
}))

const SOURCE = {
  id: '99999999-9999-9999-9999-999999999999',
  kind: 'journal',
  doi: '10.1000/x',
  url: null,
  title: '어느 논문',
  year: 2020,
  publisher: null,
  license: null,
}

const DETAIL = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'SUS304',
  material_code: null,
  category: 'metal',
  description: null,
  subsystem: 'housing',
  role: 'product',
  manufacturer: 'POSCO',
  material_class: null,
  grade: null,
  attributes: {},
  values: [
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000001',
      property_key: 'mechanical.youngs_modulus',
      property_name: '영률',
      domain: 'mechanical',
      symbol: 'E',
      value_num: 1.93e11,
      value_text: null,
      unit: 'Pa',
      uncertainty: null,
      conditions: { temperature_k: 296.15, corrected_by: '54차 PA', regime: 'alpha1 (below Tg)' },
      distinguishing: { regime: 'alpha1 (below Tg)' },
      method: 'measured',
      quality_tier: 1,
      source: SOURCE,
      source_detail: 'Table 2',
      notes: null,
      representative: true,
      n_candidates: 2,
      separated_by: null,
    },
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000002',
      property_key: 'mechanical.youngs_modulus',
      property_name: '영률',
      domain: 'mechanical',
      symbol: 'E',
      value_num: 2.0e11,
      value_text: null,
      unit: 'Pa',
      uncertainty: null,
      conditions: { assumption: true },
      method: 'estimated',
      quality_tier: 4,
      source: null,
      source_detail: null,
      notes: null,
      representative: false,
      n_candidates: 2,
      separated_by: '등급',
    },
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000003',
      property_key: 'thermal.glass_transition',
      property_name: '유리전이온도',
      domain: 'thermal',
      symbol: 'Tg',
      value_num: 408.15,
      value_text: null,
      unit: 'K',
      uncertainty: null,
      conditions: null,
      method: 'handbook',
      quality_tier: 2,
      source: SOURCE,
      source_detail: null,
      notes: null,
      representative: true,
      n_candidates: 1,
      separated_by: null,
    },
    {
      id: 'aaaaaaaa-0000-0000-0000-000000000004',
      property_key: 'thermal.conductivity',
      property_name: '열전도율',
      domain: 'thermal',
      symbol: 'k',
      value_num: 16.2,
      value_text: null,
      unit: 'W/(m.K)',
      uncertainty: null,
      conditions: null,
      method: 'handbook',
      quality_tier: 2,
      source: SOURCE,
      source_detail: null,
      notes: null,
      representative: true,
      n_candidates: 1,
      separated_by: null,
      origin: 'local',
      created_by: '홍길동',
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  material.mockResolvedValue(DETAIL)
  deleteValue.mockResolvedValue(undefined)
  seriesPoints.mockResolvedValue({ series: null, points: [] })
  me ={ id: 'u1', email: 'hong', display_name: '홍길동', is_system_admin: false, memberships: [] }
  // 단위 모드가 브라우저에 남는다 — 시험끼리 새지 않게 지운다.
  localStorage.clear()
})

/** 값 줄을 보는 시험은 「전체 값」 탭에서 — 기본 탭은 물성 요약이다(2026-10-22). */
function show(tab = 'values') {
  const query = tab ? `?tab=${tab}` : ''
  render(
    <MemoryRouter initialEntries={[`/catalog/11111111-1111-1111-1111-111111111111${query}`]}>
      <Routes>
        <Route path="/catalog/:id" element={<CatalogMaterialPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('진 후보를 숨기지 않는다', () => {
  it('대표는 후보 수와, 대안은 밀린 자리와 함께 선다', async () => {
    show()
    expect(await screen.findByText(/대표값 · 후보 2/)).toBeInTheDocument()
    expect(screen.getByText(/대안 · 등급/)).toBeInTheDocument()
  })

  it('가정값은 「가정」 배지를 달고 그대로 보인다 — 제외하지 않는다', async () => {
    show()
    expect(await screen.findByText('가정')).toBeInTheDocument()
    // 값 자체도 표에 있다 — 기본은 표시용 단위(Pa→MPa)다.
    expect(screen.getByText(/2\.000e\+5 MPa/)).toBeInTheDocument()
  })

  it('단위 모드를 SI 로 바꾸면 Pa 로 보인다', async () => {
    show()
    await screen.findByText('가정')
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(screen.getByLabelText('단위 모드'), { target: { value: 'si' } })
    expect(await screen.findByText(/2\.000e\+11 Pa/)).toBeInTheDocument()
  })

  it('도메인으로 갈라 서고, 조건과 출처가 값 옆에 있다', async () => {
    show()
    expect(await screen.findByText('기계')).toBeInTheDocument()
    expect(screen.getByText('열')).toBeInTheDocument()
    expect(screen.getByText(/T 296\.15 K/)).toBeInTheDocument()
    // 같은 출처가 값 세 줄(영률·Tg·열전도율)에 붙어 링크도 셋이다 — 전부 DOI 로 간다.
    const links = screen.getAllByRole('link', { name: '어느 논문' })
    expect(links).toHaveLength(3)
    for (const link of links) {
      expect(link).toHaveAttribute('href', 'https://doi.org/10.1000/x')
    }
  })

  it('관리 표지(corrected_by 등)는 조건 줄에 안 보인다', async () => {
    show()
    await screen.findByText(/T 296\.15 K/)
    expect(screen.queryByText(/corrected_by/)).toBeNull()
  })
})

describe('값 표의 열 (2026-10-04)', () => {
  it('열은 물성 · 값 · 등급 · 조건 · 출처 차례다', async () => {
    show()
    await screen.findByText(/T 296\.15 K/)
    const [first] = screen.getAllByRole('table')
    const heads = within(first).getAllByRole('columnheader').map((one) => one.textContent)
    expect(heads).toEqual(['물성', '값', '등급', '조건', '출처'])
    // 칸도 같은 차례다 — 머리만 바꾸고 칸을 안 옮기면 등급 밑에 조건이 선다.
    const cells = within(within(first).getAllByRole('row')[1]).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('실측')
    expect(cells[3]).toHaveTextContent(/T 296\.15 K/)
    expect(cells[4]).toHaveTextContent('어느 논문')
  })

  it('칸이 전부 접힌다 — 폭을 박은 표에서 안 접히면 옆 칸 위로 넘친다', async () => {
    // 표 칸의 기본값이 whitespace-nowrap 이다. jsdom 은 배치를 안 하므로 접기를
    // 켰는지만 본다 — 지적(2026-10-04)은 긴 조건·출처가 옆 칸 글자와 겹친 것이었다.
    show()
    await screen.findByText(/T 296\.15 K/)
    for (const cell of screen.getAllByRole('cell')) {
      expect(cell).toHaveClass('whitespace-normal')
    }
  })
})

describe('원본에서 빠진 것 (2026-10-04)', () => {
  it('빠진 값은 「대안」 이 아니라 「원본에서 빠짐」 으로 서고, 줄은 지킨다', async () => {
    // 이관은 지우지 않고 표시만 한다 — 대표 후보에서 빠졌다는 것을 그 자리에서 말한다.
    material.mockResolvedValue({
      ...DETAIL,
      values: DETAIL.values.map((one, index) =>
        index === 1
          ? { ...one, source_missing_at: '2026-10-04T00:00:00Z', separated_by: '원본에서 빠짐' }
          : one
      ),
    })
    show()
    const badge = await screen.findByText('원본에서 빠짐')
    expect(badge).toHaveAttribute('title', expect.stringContaining('대표값 · 값 검색 · 덱에는 쓰지 않습니다'))
    expect(screen.queryByText(/대안 · /)).not.toBeInTheDocument()
  })

  it('재료가 빠졌으면 머리에 선다', async () => {
    material.mockResolvedValue({ ...DETAIL, source_missing_at: '2026-10-04T00:00:00Z' })
    show()
    expect(await screen.findByText('원본에서 빠짐')).toHaveAttribute(
      'title',
      expect.stringContaining('빠진 재료')
    )
  })
})

describe('CatalogMaterialPage — 후보를 가르는 조건', () => {
  it('갈리는 조건이 굵게, 나머지는 흐리게 선다', async () => {
    material.mockResolvedValue(DETAIL)
    show()

    // 서버가 뽑아 준 갈리는 조건이 보인다 — 사람이 넷을 대조하지 않아도 된다.
    expect(await screen.findByText(/alpha1 \(below Tg\)/)).toBeInTheDocument()
  })

  it('범위의 한쪽이면 그렇다고 말한다', async () => {
    material.mockResolvedValue({
      ...DETAIL,
      values: [
        { ...DETAIL.values[0], distinguishing: { bound: 'lower' }, n_candidates: 2 },
      ],
    })
    show()
    expect(await screen.findByText('범위 하한')).toBeInTheDocument()
  })

  it('직접 넣은 값은 「직접 넣음 · 누구」 로 보이고, 넣은 사람만 지운다', async () => {
    show()
    expect(await screen.findByText(/직접 넣음 · 홍길동/)).toBeInTheDocument()
    // 이관해 온 값에는 지우기 단추가 없다.
    expect(screen.queryByRole('button', { name: '영률 값 삭제' })).toBeNull()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { fireEvent, waitFor } = await import('@testing-library/react')
    fireEvent.click(screen.getByRole('button', { name: '열전도율 값 삭제' }))
    await waitFor(() =>
      expect(deleteValue).toHaveBeenCalledWith('aaaaaaaa-0000-0000-0000-000000000004')
    )
  })

  it('남이 넣은 값은 관리자만 지운다', async () => {
    me = { ...me, display_name: '김철수' }
    show()
    await screen.findByText(/직접 넣음 · 홍길동/)
    expect(screen.queryByRole('button', { name: '열전도율 값 삭제' })).toBeNull()
  })
})

describe('요약 + 탭 (2026-10-22)', () => {
  // 값이 366건인 재료(SAC-Q)는 같은 물성 이름이 수십 줄 섰다 — 물성 하나에 한 줄로 접고,
  // 곡선 · 출처를 탭으로 가른다(사용자 결정).
  const CURVE_SOURCE = { ...SOURCE, id: '88888888-8888-8888-8888-888888888888', title: '고온 논문' }
  const conductivity = (id: string, t: number, k: number) => ({
    ...DETAIL.values[3],
    id,
    value_num: k,
    origin: 'catalog',
    created_by: null,
    source: CURVE_SOURCE,
    conditions: { temperature_k: t },
    representative: false,
  })
  // 곡선 점은 대표로 뽑힌 것(300 K)만 상세에 실린다(ADR 0072) — 나머지는 벌을 펼칠 때 받는다.
  const storage = (id: string, t: number, e: number) => ({
    ...DETAIL.values[0],
    id,
    property_key: 'mechanical.storage_modulus',
    property_name: '저장 탄성률',
    value_num: e,
    conditions: { temperature_k: t },
    distinguishing: {},
    representative: true,
    n_candidates: 1,
    series_id: 'ssssssss-0000-0000-0000-000000000001',
    origin: 'local',
    created_by: '홍길동',
  })
  const WITH_CURVES = {
    ...DETAIL,
    values: [
      ...DETAIL.values,
      conductivity('cccccccc-0000-0000-0000-000000000001', 300, 15),
      conductivity('cccccccc-0000-0000-0000-000000000002', 350, 16),
      conductivity('cccccccc-0000-0000-0000-000000000003', 400, 17),
      storage('dddddddd-0000-0000-0000-000000000002', 300, 1e9),
    ],
    series: [
      {
        id: 'ssssssss-0000-0000-0000-000000000001',
        kind: 'curve',
        label: 'DMA 1 Hz 표',
        x_key: 'temperature_k',
        x_unit: 'K',
        x_min: 250,
        x_max: 300,
        columns: [
          {
            property_key: 'mechanical.storage_modulus',
            property_name: '저장 탄성률',
            unit: 'Pa',
            domain: 'mechanical',
            count: 2,
            low: 1e9,
            high: 2e9,
          },
        ],
        model: null,
        point_count: 2,
        conditions: { frequency_hz: 1 },
        method: 'digitized',
        quality_tier: 2,
        source: SOURCE,
        source_detail: 'Fig. 3',
        notes: null,
        created_by: '홍길동',
        created_at: '2026-10-22T00:00:00Z',
      },
    ],
  }

  it('기본은 물성 요약 — 물성 하나에 한 줄이고, 펼치면 후보가 선다', async () => {
    show('')
    expect(await screen.findByRole('button', { name: '영률 펼치기' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /펼치기$/ })).toHaveLength(3)
    const summary = screen.getByLabelText('문헌 재료 요약')
    expect(summary).toHaveTextContent('값 4')
    expect(summary).toHaveTextContent('물성 3')
    // 접혀 있을 때는 후보 줄이 없다.
    expect(screen.queryByText(/대표값 · 후보 2/)).not.toBeInTheDocument()
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.click(screen.getByRole('button', { name: '영률 펼치기' }))
    expect(await screen.findByText(/대표값 · 후보 2/)).toBeInTheDocument()
    expect(screen.getByText(/대안 · 등급/)).toBeInTheDocument()
  })

  it('곡선 · 표 — 직접 넣은 한 벌과 화면이 이은 선을 다른 이름으로 세우고, 넣은 사람이 벌째 지운다', async () => {
    material.mockResolvedValue(WITH_CURVES)
    deleteSeries.mockResolvedValue(undefined)
    seriesPoints.mockResolvedValue({
      series: WITH_CURVES.series[0],
      points: [
        { property_key: 'mechanical.storage_modulus', value: 2e9, unit: 'Pa', x: 250 },
        { property_key: 'mechanical.storage_modulus', value: 1e9, unit: 'Pa', x: 300 },
      ],
    })
    const { fireEvent, waitFor } = await import('@testing-library/react')
    show('curves')
    expect(await screen.findByText('DMA 1 Hz 표')).toBeInTheDocument()
    expect(screen.getByText('조건별 값을 이어 그림 (자동)')).toBeInTheDocument()
    // 점은 상세가 아니라 그 벌에서 받는다 — 받은 점으로 표가 선다.
    expect(seriesPoints).toHaveBeenCalledWith('ssssssss-0000-0000-0000-000000000001')
    fireEvent.click(await screen.findByRole('button', { name: '표 보기' }))
    const rows = within(screen.getAllByRole('table').at(-1) as HTMLElement).getAllByRole('row')
    expect(rows).toHaveLength(3)
    // 열전도율 세 점(같은 출처 · 온도만 다름)이 화면이 이은 선 하나다.
    expect(screen.getByText('축 온도 · 선 1')).toBeInTheDocument()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'DMA 1 Hz 표 묶음 삭제' }))
    await waitFor(() =>
      expect(deleteSeries).toHaveBeenCalledWith('ssssssss-0000-0000-0000-000000000001')
    )
  })

  it('한 벌의 점은 낱개로 안 지운다 — 대표로 실린 점은 「묶음의 점」 으로 서고 지우기 단추가 없다', async () => {
    material.mockResolvedValue(WITH_CURVES)
    show('values')
    expect((await screen.findAllByText('묶음의 점')).length).toBe(1)
    expect(screen.queryByRole('button', { name: '저장 탄성률 값 삭제' })).toBeNull()
    // 나머지 점은 여기 없다고 말한다.
    expect(screen.getByText(/곡선 · 산점의 점 2개는 여기 없습니다/)).toBeInTheDocument()
  })

  it('요약의 값 수는 벌 머리의 점까지 — 대표로 실린 점을 두 번 세지 않는다', async () => {
    material.mockResolvedValue(WITH_CURVES)
    show('')
    const summary = await screen.findByLabelText('문헌 재료 요약')
    // 낱값 4 + 열전도율 3 + 곡선 점 2(대표로 실린 점 하나는 거기 든다).
    expect(summary).toHaveTextContent('값 9')
    expect(summary).toHaveTextContent('그중 곡선 · 산점의 점 2')
    const row = screen.getByRole('button', { name: '저장 탄성률 펼치기' }).closest('tr') as HTMLElement
    expect(within(row).getAllByRole('cell')[3]).toHaveTextContent('2')
  })

  it('출처 — 출처 하나에 한 줄, 값 수와 함께', async () => {
    show('sources')
    const link = await screen.findByRole('link', { name: '어느 논문' })
    const row = link.closest('tr')
    expect(row).not.toBeNull()
    // 값 3 · 물성 3(영률 · 유리전이온도 · 열전도율).
    const cells = within(row as HTMLElement).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('3')
    expect(cells[3]).toHaveTextContent('3')
    // 출처 없는 추정값도 한 줄로 선다(값 1).
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })

  it('출처의 라이선스가 열로 선다 — 귀속 문구는 그 칸에 걸린다(ADR 0068)', async () => {
    material.mockResolvedValue({
      ...DETAIL,
      values: DETAIL.values.map((one) =>
        one.source
          ? { ...one, source: { ...one.source, license: 'CC-BY-4.0', attribution: 'Kim (2020), CC BY 4.0' } }
          : one
      ),
    })
    show('sources')
    const cell = await screen.findByText('CC-BY-4.0')
    expect(cell).toHaveAttribute('title', 'Kim (2020), CC BY 4.0')
  })

  const scatter = (id: string, label: string) => ({
    id,
    kind: 'scatter',
    label,
    x_key: 'cycles',
    x_unit: null,
    x_min: 1.2e5,
    x_max: 1e7,
    columns: [
      {
        property_key: 'mechanical.fatigue_strength',
        property_name: '피로강도',
        unit: 'Pa',
        domain: 'mechanical',
        count: 2,
        low: 2.5e8,
        high: 4e8,
      },
    ],
    model: null,
    point_count: 2,
    conditions: null,
    method: 'digitized',
    quality_tier: 3,
    source: SOURCE,
    source_detail: 'Fig. 5',
    notes: null,
    created_by: null,
    created_at: '2026-10-23T00:00:00Z',
    batch_key: 'materialcollector/fatigue-literature/2026-10-23',
  })
  const SN_POINTS = [
    { property_key: 'mechanical.fatigue_strength', value: 4e8, unit: 'Pa', x: 1.2e5, row_conditions: null },
    { property_key: 'mechanical.fatigue_strength', value: 2.5e8, unit: 'Pa', x: 1e7, row_conditions: { runout: true } },
  ]

  it('산점 한 벌은 점으로 — 런아웃은 빈 점, 반입 묶음이면 묶음 키(ADR 0068)', async () => {
    // 산점의 점은 상세에 하나도 안 실린다 — 벌을 펼칠 때 받는다(ADR 0072).
    material.mockResolvedValue({ ...DETAIL, series: [scatter('scatter-1', 'S-N R=-1')] })
    seriesPoints.mockResolvedValue({ series: null, points: SN_POINTS })
    show('curves')
    expect(await screen.findByText('S-N R=-1')).toBeInTheDocument()
    expect(screen.getByText(/반입 · materialcollector\/fatigue-literature/)).toBeInTheDocument()
    const groups = await screen.findAllByTestId('chart-dots')
    expect(groups.map((one) => one.getAttribute('aria-label'))).toEqual(['파단', '런아웃'])
  })

  it('산점만 있는 물성도 요약에 선다 — 대표 없이, 수 · 축 범위는 벌 머리에서', async () => {
    material.mockResolvedValue({ ...DETAIL, series: [scatter('scatter-1', 'S-N R=-1')] })
    show('')
    const button = await screen.findByRole('button', { name: '대표 없음 · 산점 1벌' })
    const row = button.closest('tr') as HTMLElement
    const cells = within(row).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('피로강도')
    expect(cells[3]).toHaveTextContent('2')
    expect(cells[4]).toHaveTextContent(/수명\(반복수\)/)
    // 요약 화면은 점을 받지 않는다.
    expect(seriesPoints).not.toHaveBeenCalled()
  })

  it('벌이 많으면 앞의 넷만 점을 받고, 나머지는 펼칠 때 받는다', async () => {
    const many = Array.from({ length: 6 }, (_, index) => scatter(`sn-${index}`, `S-N 벌 ${index}`))
    material.mockResolvedValue({ ...DETAIL, series: many })
    seriesPoints.mockResolvedValue({ series: null, points: SN_POINTS })
    show('curves')
    await screen.findByText('S-N 벌 5')
    const { fireEvent, waitFor } = await import('@testing-library/react')
    await waitFor(() => expect(seriesPoints).toHaveBeenCalledTimes(4))
    expect(seriesPoints).not.toHaveBeenCalledWith('sn-4')
    fireEvent.click(screen.getByRole('button', { name: 'S-N 벌 4 펼치기' }))
    await waitFor(() => expect(seriesPoints).toHaveBeenCalledWith('sn-4'))
    expect(seriesPoints).toHaveBeenCalledTimes(5)
  })

  it('전체 값 탭은 물성 이름으로 거른다', async () => {
    show('values')
    await screen.findByText(/T 296\.15 K/)
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(screen.getByLabelText('물성 찾기'), { target: { value: '열전도' } })
    expect(await screen.findByText('4건 중 1건')).toBeInTheDocument()
    expect(screen.queryByText(/T 296\.15 K/)).not.toBeInTheDocument()
  })
})
