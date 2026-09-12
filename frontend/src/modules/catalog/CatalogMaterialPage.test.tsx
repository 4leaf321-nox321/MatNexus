/**
 * 문헌 재료 상세 — **진 후보를 숨기지 않는다.**
 *
 *   대표가 먼저, 후보 수와 함께     「대표값 · 후보 2」
 *   진 후보는 밀린 자리와 함께      「대안 · 등급」
 *   가정값은 가정이라고 말한다      tier4 + assumption → 「가정」 배지 (제외는 안 한다)
 *   출처가 값 옆에 산다            제목·연도·DOI 링크
 *   직접 넣은 값은 그렇게 보인다     「직접 넣음 · 누구」, 넣은 사람만 지우기 단추
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogMaterialPage from '@/modules/catalog/CatalogMaterialPage'

const material = vi.fn()
const deleteValue = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    summary: vi.fn(),
    materials: vi.fn(),
    material: (...args: unknown[]) => material(...args),
    deleteValue: (...args: unknown[]) => deleteValue(...args),
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
  me = { id: 'u1', email: 'hong', display_name: '홍길동', is_system_admin: false, memberships: [] }
  // 단위 모드가 브라우저에 남는다 — 시험끼리 새지 않게 지운다.
  localStorage.clear()
})

function show() {
  render(
    <MemoryRouter initialEntries={['/catalog/11111111-1111-1111-1111-111111111111']}>
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
