/**
 * 지식 그래프 화면 — **구조는 응답이 곧 정의, 탐색은 상한과 「+N」.**
 *
 * 여기서 지키는 것 — 구조 그림의 종류·관계 종류가 overview 에서 온다 · 종류를 고르면 관계와 수가
 * 옆 판에 선다 · 검색으로 시작점을 고르면 주소에 focus 가 적히고 이웃을 든다 · 잘린 노드는
 * 「+N」 배지를 달고 상세 판이 「여기서 확장」 을 낸다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Neighborhood, NodeDetail, Overview } from '@/modules/graph/api'

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { memberships: [], is_system_admin: true } }),
}))
vi.mock('@/shared/theme/ThemeProvider', () => ({
  useTheme: () => ({ theme: 'light', setTheme: () => undefined }),
}))
// 캔버스는 노드 이름만 적는 가짜 — force 배치는 시험할 것이 아니다.
vi.mock('@/modules/graph/GraphCanvas', () => ({
  GraphCanvas: ({
    nodes,
    onNodeClick,
    overlay,
  }: {
    nodes: { id: string; label: string; badge?: string | null }[]
    onNodeClick?: (id: string) => void
    overlay?: React.ReactNode
  }) => (
    <div data-testid="canvas">
      {nodes.map((one) => (
        <button key={one.id} type="button" onClick={() => onNodeClick?.(one.id)}>
          {one.label}
          {one.badge ? ` ${one.badge}` : ''}
        </button>
      ))}
      {overlay}
    </div>
  ),
}))

const OVERVIEW: Overview = {
  nodes: [
    {
      slug: 'material',
      label: '재료',
      icon: 'layers',
      layer: 'operations',
      count: 96,
      detail_path: '/materials',
    },
    {
      slug: 'sample',
      label: '시료',
      icon: 'package',
      layer: 'operations',
      count: 433,
      detail_path: null,
    },
    {
      slug: 'parameter_set',
      label: '파라미터 벌',
      icon: 'braces',
      layer: 'operations',
      count: 0,
      detail_path: null,
    },
  ],
  edges: [
    {
      relation: 'derived_from',
      label: '이 시료가 나온 재료',
      inverse_label: '이 재료에서 나온 시료',
      directed: true,
      src_type: 'sample',
      dst_type: 'material',
      count: 964,
    },
    {
      relation: 'set_of',
      label: '이 벌을 가진 재료',
      inverse_label: '이 재료가 받아 온 파라미터 벌',
      directed: true,
      src_type: 'parameter_set',
      dst_type: 'material',
      count: 0,
    },
  ],
  object_count: 529,
  edge_count: 964,
}

const NEIGHBORHOOD: Neighborhood = {
  focus: 'material:11111111-1111-1111-1111-111111111111',
  nodes: [
    {
      id: 'material:11111111-1111-1111-1111-111111111111',
      label: '인장',
      key: 'M-000038',
      sublabel: 'Metal · DP600',
      type_slug: 'material',
      type_label: '재료',
      status: 'active',
      owner_workspace_slug: null,
      degree: 3,
      truncated: true,
      detail_path: '/materials/11111111-1111-1111-1111-111111111111',
    },
    {
      id: 'sample:22222222-2222-2222-2222-222222222222',
      label: '6800',
      key: 'LOT-1',
      sublabel: 'POSCO',
      type_slug: 'sample',
      type_label: '시료',
      status: 'active',
      owner_workspace_slug: null,
      degree: 1,
      truncated: false,
      detail_path: null,
    },
  ],
  edges: [
    {
      id: 'derived_from:1',
      relation: 'derived_from',
      label: '이 시료가 나온 재료',
      inverse_label: '이 재료에서 나온 시료',
      directed: true,
      src: 'sample:22222222-2222-2222-2222-222222222222',
      dst: 'material:11111111-1111-1111-1111-111111111111',
    },
  ],
  depth: 1,
  fanout: 30,
  node_limit: 300,
  truncated: true,
}

const DETAIL: NodeDetail = {
  id: NEIGHBORHOOD.focus,
  label: '인장',
  key: 'M-000038',
  type_slug: 'material',
  type_label: '재료',
  status: 'active',
  detail_path: '/materials/11111111-1111-1111-1111-111111111111',
  facts: [{ label: '재료 번호', value: 'M-000038' }],
  related: [
    {
      relation: 'derived_from',
      label: '이 재료에서 나온 시료',
      outgoing: false,
      node_id: 'sample:22222222-2222-2222-2222-222222222222',
      node_label: '6800',
      node_type_label: '시료',
    },
    {
      relation: 'links_to',
      label: '이 사내 재료와 이은 문헌 재료',
      outgoing: true,
      node_id: 'catalog_material:33333333-3333-3333-3333-333333333333',
      node_label: 'DP600 (literature)',
      node_type_label: '문헌 재료',
    },
  ],
  related_total: 3,
}

const calls: string[] = []
vi.mock('@/shared/api/client', () => ({
  api: {
    get: vi.fn(async (path: string) => {
      calls.push(path)
      if (path.startsWith('/graph/overview')) return OVERVIEW
      if (path.startsWith('/graph/search')) {
        return [
          {
            id: NEIGHBORHOOD.focus,
            label: '인장',
            key: 'M-000038',
            sublabel: 'Metal · DP600',
            type_slug: 'material',
            type_label: '재료',
          },
        ]
      }
      if (path.startsWith('/graph/neighborhood')) return NEIGHBORHOOD
      if (path.startsWith('/graph/node')) return DETAIL
      if (path.startsWith('/graph/browse'))
        return { items: [], total: 0, limit: 20, offset: 0 }
      throw new Error(`unexpected ${path}`)
    }),
  },
  ApiError: class extends Error {},
}))

import GraphPage from '@/modules/graph/GraphPage'

function open(url = '/graph') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <GraphPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  calls.length = 0
})

describe('지식 그래프', () => {
  it('구조 그림은 종류와 관계 종류를 그리고, 종류를 고르면 관계와 수가 선다', async () => {
    open()
    await waitFor(() => expect(screen.getByText('시료')).toBeTruthy())
    expect(screen.getByText(/종류 3 · 관계 종류 2 · 객체 529/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '시료' }))
    // 옆 판 — 객체 수와 걸린 관계 종류.
    expect(screen.getByText('433')).toBeTruthy()
    expect(screen.getAllByText(/이 시료가 나온 재료/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /이 종류 전체 그리기/ })).toBeTruthy()
  })

  it('검색으로 시작점을 고르면 이웃을 들고, 잘린 노드에 +N 이 붙으며 상세가 확장을 낸다', async () => {
    open('/graph?focus=' + NEIGHBORHOOD.focus)
    await waitFor(() => expect(screen.getByRole('button', { name: /인장 \+2/ })).toBeTruthy())
    expect(calls.some((one) => one.startsWith('/graph/neighborhood?focus=material'))).toBe(
      true,
    )
    // 시작점은 고른 채로 뜬다 — 상세 판에 「여기서 확장 (+2)」.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /여기서 확장 \(\+2\)/ })).toBeTruthy(),
    )
    expect(screen.getByText('이 재료에서 나온 시료')).toBeTruthy()
    expect(screen.getByText(/일부만 실었습니다/)).toBeTruthy()
  })
})
