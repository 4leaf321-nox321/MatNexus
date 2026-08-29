/**
 * 재료 계층 요약 줄 — **펼치기 전에 무엇이 얼마나 있는지 말하는가.**
 *
 * 시료 ▸ 시편 ▸ 시험이 아코디언 3단이라, 누르기 전에는 화면이 아무것도 안 알려
 * 줬다 — 「구조가 한눈에 안 들어온다」 가 그 말이다.
 *
 * 무는 자리를 「수가 보인다」 보다 **「빠진 것을 말하는가」** 에 둔다. 시편을 잘라
 * 놓고 시험을 안 한 것이 남으면 아무도 모르는데, **그것이 다음에 할 일이다.**
 * 반대로 0 일 때도 그 칩이 뜨면 늘 켜져 있는 경고가 되어 아무도 안 본다.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MaterialDetailPage from '@/modules/materials/MaterialDetailPage'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const summary = vi.fn()
const get = vi.fn()
const samples = vi.fn()

vi.mock('@/modules/materials/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/materials/api')>(
    '@/modules/materials/api'
  )
  return {
    ...actual,
    materialsApi: {
      ...actual.materialsApi,
      get: (...a: unknown[]) => get(...a),
      samples: (...a: unknown[]) => samples(...a),
      summary: (...a: unknown[]) => summary(...a),
      list: () => Promise.resolve({ items: [], total: 0 }),
      classifications: () => Promise.resolve([]),
      workspaces: () => Promise.resolve([]),
    },
  }
})

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

const MATERIAL = {
  id: 'm1',
  record_name: 'SECC_1.0',
  alias: null,
  family: 'Metal',
  category: 'Steel',
  grade: 'SECC',
  spec_thickness: 1.0,
  spec_thickness_unit: 'mm',
  density: null,
  density_unit: 'kg/m3',
  poisson_ratio: null,
  uses: {},
  declared_properties: [],
  note: null,
  legacy_id: null,
  sample_count: 5,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
}

function show(over: Record<string, number>) {
  get.mockResolvedValue(MATERIAL)
  samples.mockResolvedValue([])
  summary.mockResolvedValue({
    sample_count: 5,
    specimen_count: 15,
    run_count: 9,
    specimens_without_run: 0,
    ...over,
  })
  render(
    <MemoryRouter initialEntries={['/materials/m1']}>
      <LeftPanelProvider>
        <LeftPanelHost />
        <MaterialDetailPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('계층 요약', () => {
  it('펼치지 않아도 세 층의 수를 말한다', async () => {
    show({})
    expect(await screen.findByText('시료 5')).toBeInTheDocument()
    expect(screen.getByText('시편 15')).toBeInTheDocument()
    expect(screen.getByText('시험 9')).toBeInTheDocument()
  })

  it('시험 없는 시편이 있으면 그것을 말한다', async () => {
    // **다음에 할 일이 그것이다.** 잘라 놓고 안 잰 시편은 아무도 안 본다.
    show({ specimens_without_run: 6 })
    expect(await screen.findByText(/시험 없는 시편 6/)).toBeInTheDocument()
  })

  it('0 이면 그 칩이 사라진다 — 늘 켜진 경고는 아무도 안 본다', async () => {
    show({ specimens_without_run: 0 })
    await screen.findByText('시료 5')
    expect(screen.queryByText(/시험 없는 시편/)).not.toBeInTheDocument()
  })
})
