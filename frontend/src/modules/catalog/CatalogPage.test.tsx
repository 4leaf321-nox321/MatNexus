/**
 * 문헌 물성 목록 — 검색·패싯·더 보기.
 *
 *   규모가 먼저 보인다        재료·값·출처 수 — 이 저수지가 얼마나 큰가
 *   분류는 우리 표기로        metal 이 아니라 Metal (CATEGORY_MAP)
 *   상한에 닿으면 말한다      더 못 보여 줄 때 「좁혀 달라」 고 말한다
 *   값 범위는 화면 단위로     MPa 로 받아 SI 로 보낸다 — 단위를 잘못 풀면 조용히 틀린다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogPage from '@/modules/catalog/CatalogPage'

const summary = vi.fn()
const materials = vi.fn()
const resolveProperty = vi.fn()

const download = vi.fn()

vi.mock('@/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/client')>()),
  downloadFile: (...args: unknown[]) => download(...args),
}))

// 계 목록은 서버가 준다(ADR 0036). **기본이 첫째가 아니다** — 순서로 고르면 통과해 버린다.
vi.mock('@/shared/api/unitSystems', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/unitSystems')>()),
  unitSystemsApi: {
    list: () =>
      Promise.resolve([
        { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
        { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
      ]),
  },
}))

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    summary: (...args: unknown[]) => summary(...args),
    materials: (...args: unknown[]) => materials(...args),
    resolveProperty: (...args: unknown[]) => resolveProperty(...args),
    material: vi.fn(),
  },
}))

const SUMMARY = {
  materials: 2663,
  values: 42209,
  sources: 3013,
  definitions: 271,
  subsystems: { pcb: 182, '': 1835 },
  categories: { metal: 320, polymer: 807 },
  domains: { mechanical: 9000 },
  materials_by_domain: { mechanical: 1452, thermal: 1528 },
  manufacturers: { POSCO: 2, '3M': 30 },
  tiers: { 1: 25949 },
}

const PAGE = {
  total: 2,
  limit: 50,
  offset: 0,
  items: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      name: 'SUS304',
      material_code: null,
      category: 'metal',
      subsystem: 'housing',
      role: 'product',
      manufacturer: 'POSCO',
      material_class: null,
      grade: null,
      value_count: 42,
    },
    {
      id: '22222222-2222-2222-2222-222222222222',
      name: 'FR-4 generic',
      material_code: null,
      category: 'composite',
      subsystem: null,
      role: null,
      manufacturer: null,
      material_class: null,
      grade: null,
      value_count: 7,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  summary.mockResolvedValue(SUMMARY)
  materials.mockResolvedValue(PAGE)
})

function show(routes: string[] = ['/catalog']) {
  render(
    <MemoryRouter initialEntries={routes}>
      <CatalogPage />
    </MemoryRouter>
  )
}

describe('문헌 물성 목록', () => {
  it('규모와 재료 줄이 뜬다', async () => {
    show()
    expect(await screen.findByText(/재료 2,663종/)).toBeInTheDocument()
    expect(await screen.findByText('SUS304')).toBeInTheDocument()
    expect(screen.getByText('FR-4 generic')).toBeInTheDocument()
    // 분류는 우리 표기(Metal), 계통 미분류는 「미분류」 로 말한다.
    expect(screen.getByText('Metal')).toBeInTheDocument()
    expect(screen.getAllByText('미분류').length).toBeGreaterThan(0)
  })

  it('전부 보여 줬으면 더 보기가 없다', async () => {
    show()
    await screen.findByText('SUS304')
    expect(screen.queryByRole('button', { name: /더 보기/ })).toBeNull()
  })

  it('남은 것이 있으면 더 보기가 뜬다', async () => {
    materials.mockResolvedValue({ ...PAGE, total: 500 })
    show()
    expect(await screen.findByRole('button', { name: /더 보기/ })).toBeInTheDocument()
  })

  it('지금 거른 조건 그대로 내보낸다', async () => {
    // **화면과 다른 것이 내려오면** 사람은 그 사실을 모른 채 그 파일로 계산한다.
    // 전부 받으면 70MB 가 넘으므로, 좁혀 놓고 받는 길이 기본이다.
    const user = userEvent.setup()
    show(['/catalog?q=SUS'])
    await screen.findByText('SUS304')

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    await user.click(
      await screen.findByRole('menuitem', { name: /matnexus_catalog_mm_n_tonne\.json/ })
    )
    await waitFor(() => expect(download).toHaveBeenCalled())
    const [url, filename] = download.mock.calls[0] as [string, string]
    const sent = new URL(url, 'http://localhost')
    expect(sent.pathname).toBe('/catalog/export')
    expect(sent.searchParams.get('q')).toBe('SUS')
    // 값은 고른 계로 나간다 — 안 고르면 서버 기본(ADR 0036).
    expect(sent.searchParams.get('units')).toBe('mm_n_tonne')
    expect(filename).toBe('matnexus_catalog_mm_n_tonne.json')
  })
})

describe('거르는 축 — 분야 · 제조사 · 값 범위 (2026-10-03)', () => {
  /** 마지막으로 목록에 물은 조건. */
  function asked(): Record<string, unknown> {
    return (materials.mock.calls.at(-1)?.[0] ?? {}) as Record<string, unknown>
  }

  it('커버리지 칸에서 온 분야로 묻고, 내보내기도 같은 조건으로 받는다', async () => {
    const user = userEvent.setup()
    show(['/catalog?subsystem=pcb&domain=thermal'])
    await screen.findByText('SUS304')
    expect(asked()).toMatchObject({ subsystem: 'pcb', domain: 'thermal' })
    expect(screen.getByRole('combobox', { name: '물성 분야로 필터' })).toHaveValue('thermal')

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    await user.click(
      await screen.findByRole('menuitem', { name: /matnexus_catalog_mm_n_tonne\.json/ })
    )
    await waitFor(() => expect(download).toHaveBeenCalled())
    const sent = new URL(download.mock.calls[0][0] as string, 'http://localhost')
    expect(sent.searchParams.get('domain')).toBe('thermal')
    expect(sent.searchParams.get('subsystem')).toBe('pcb')
  })

  it('제조사는 많은 것부터 늘어서고, 고르면 그 이름으로 묻는다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('SUS304')
    await user.click(screen.getByRole('button', { name: '제조사: 전체' }))
    const options = await screen.findAllByRole('button', { name: /^(3M|POSCO)/ })
    expect(options.map((one) => one.textContent)).toEqual(['3M30', 'POSCO2'])
    await user.click(options[1])
    await waitFor(() => expect(asked()).toMatchObject({ manufacturer: 'POSCO' }))
  })

  it('값 범위는 화면 단위(MPa)로 받아 SI 로 보내고, 걸린 값을 그 단위의 열로 세운다', async () => {
    const user = userEvent.setup()
    resolveProperty.mockResolvedValue({
      query: '항복',
      candidates: [
        {
          key: 'mechanical.yield_strength',
          name: '항복강도',
          domain: 'mechanical',
          si_unit: 'Pa',
          symbol: null,
          value_count: 486,
          internal_items: [],
          measured_keys: [],
          deprecated: false,
        },
      ],
    })
    materials.mockImplementation((params: Record<string, unknown>) =>
      Promise.resolve(
        params.value_key
          ? {
              ...PAGE,
              total: 1,
              items: [{ ...PAGE.items[0], matched: { count: 3, low: 2.1e8, high: 2.5e8, unit: 'Pa' } }],
            }
          : PAGE
      )
    )
    show()
    await screen.findByText('SUS304')

    await user.type(screen.getByLabelText('값으로 거를 물성'), '항복')
    await user.click(await screen.findByRole('button', { name: /항복강도/ }))
    await user.type(screen.getByLabelText('최솟값'), '200')
    await user.type(screen.getByLabelText('최댓값'), '300')
    await user.click(screen.getByRole('button', { name: '걸기' }))

    await waitFor(() => expect(asked().value_key).toBe('mechanical.yield_strength'))
    // **SI 단위와 SI 값으로** — 「200」 을 그대로 보내면 서버는 Pa 로 읽는다.
    expect(asked().value_unit).toBe('Pa')
    expect(asked().value_min as number).toBeCloseTo(2e8, -1)
    expect(asked().value_max as number).toBeCloseTo(3e8, -1)

    // 걸린 값은 화면 단위로, 열 이름에 그 단위가 선다(단위표에서 읽는다).
    expect(await screen.findByRole('columnheader', { name: '항복강도 (MPa)' })).toBeInTheDocument()
    expect(screen.getByText('210 ~ 250 (3건)')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('항복강도 200 ~ 300 MPa 인 값이 있는 재료만')

    await user.click(screen.getByRole('button', { name: '풀기' }))
    await waitFor(() => expect(asked().value_key).toBeUndefined())
    expect(screen.queryByRole('columnheader', { name: '항복강도 (MPa)' })).not.toBeInTheDocument()
  })

  it('최솟값이 최댓값보다 크면 걸지 않고 그렇다고 말한다', async () => {
    const user = userEvent.setup()
    resolveProperty.mockResolvedValue({
      query: '밀도',
      candidates: [
        {
          key: 'physical.density',
          name: '밀도',
          domain: 'physical',
          si_unit: 'kg/m3',
          symbol: 'rho',
          value_count: 900,
          internal_items: [],
          measured_keys: [],
          deprecated: false,
        },
      ],
    })
    show()
    await screen.findByText('SUS304')
    const before = materials.mock.calls.length
    await user.type(screen.getByLabelText('값으로 거를 물성'), '밀도')
    await user.click(await screen.findByRole('button', { name: /밀도/ }))
    await user.type(screen.getByLabelText('최솟값'), '9')
    await user.type(screen.getByLabelText('최댓값'), '2')
    await user.click(screen.getByRole('button', { name: '걸기' }))
    expect(screen.getByRole('alert')).toHaveTextContent('최솟값이 최댓값보다 큽니다.')
    expect(materials.mock.calls.length).toBe(before)
  })
})
