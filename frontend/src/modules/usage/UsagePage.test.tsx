/**
 * 사용 현황 — **실제로 얼마나 잘 쓰고 있나**(관리 → 사용 현황).
 *
 *   숫자는 서버가 센 그대로     화면이 다시 더하지 않는다
 *   MCP 숫자가 한눈에           도구 호출 · 사용자 · 도구 순위 · 토큰
 *   안 센 날을 안 쓴 날로 안 읽게  집계가 쌓이기 전 기간이면 그렇다고 말한다
 *   기간을 바꾸면 다시 묻는다
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UsagePage from '@/modules/usage/UsagePage'
import type { UsageSummary } from '@/modules/usage/api'

const summary = vi.fn()

vi.mock('@/modules/usage/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/usage/api')>()),
  usageApi: { summary: (...args: unknown[]) => summary(...args) },
}))

// 그래프는 recharts 의 일이다 — 여기서는 자리만 본다.
vi.mock('@/modules/usage/UsageCharts', () => ({
  ActiveUsersChart: () => <div>쓴 사람 그래프</div>,
  RequestsChart: () => <div>요청 그래프</div>,
}))

const DATA: UsageSummary = {
  period: { start: '2026-09-03', end: '2026-10-02', days: 30 },
  measured_since: '2026-10-02',
  users: {
    active_accounts: 24,
    pending: 2,
    signups: 3,
    signups_by_day: [],
    recent_signups: [
      {
        name: '김신입',
        email: 'new@example.com',
        workspace: '금속재료팀',
        status: 'pending',
        created_at: '2026-10-01T01:00:00Z',
      },
    ],
  },
  activity: {
    any_users: 12,
    web_users: 10,
    mcp_users: 4,
    both_users: 2,
    average_daily: 3.4,
    by_day: [],
    logins: 40,
    login_users: 11,
  },
  requests: {
    total: 1500,
    reads: 1300,
    writes: 200,
    errors: 9,
    by_client: { web: 1200, mcp: 300 },
    by_day: [],
    by_area: [{ area: 'materials', label: '재료', reads: 600, writes: 40, mcp: 120, errors: 1 }],
  },
  mcp: {
    calls: 321,
    failures: 5,
    users: 4,
    average_ms: 180.5,
    tools_used: 17,
    writes_recorded: 33,
    by_tool: [
      { tool: 'resolve_property', calls: 90, failures: 0, users: 4, average_ms: 40 },
      { tool: 'property_coverage', calls: 60, failures: 2, users: 3, average_ms: 220 },
    ],
    by_user: [{ name: '박연구', calls: 200, tools: 12, last_day: '2026-10-02' }],
    tokens: { active: 6, users: 5, used_in_period: 4 },
  },
  views: {
    total: 410,
    materials: [
      { id: 'm1', label: 'M-000001 · SECC_MDOI_1.0', views: 55, viewers: 7, mcp_views: 12 },
    ],
    catalog_materials: [],
    test_runs: [],
    cards: [],
    guides: [{ id: 'platform-usage', label: '플랫폼 사용 안내', views: 9, viewers: 5, mcp_views: 0 }],
  },
  content: [
    { key: 'materials', label: '재료', created: 14 },
    { key: 'cards_published', label: '확정한 카드', created: 3 },
  ],
  people: [
    {
      user_id: 'u1',
      name: '박연구',
      email: 'park@example.com',
      workspace: '금속재료팀',
      last_day: '2026-10-02',
      active_days: 18,
      web_requests: 500,
      writes: 60,
      mcp_calls: 200,
      views: 90,
    },
  ],
}

function show() {
  render(
    <MemoryRouter>
      <UsagePage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  summary.mockResolvedValue(DATA)
})

describe('사용 현황', () => {
  it('쓴 사람 · MCP 도구 호출 · 가입 · 토큰이 한눈에 선다', async () => {
    show()
    const users = await screen.findByLabelText('쓴 사람')
    expect(users).toHaveTextContent('12명')
    expect(users).toHaveTextContent('MCP 4')
    expect(screen.getByLabelText('MCP 도구 호출')).toHaveTextContent('321건')
    expect(screen.getByLabelText('가입')).toHaveTextContent('승인 대기 2')
    expect(screen.getByLabelText('MCP · 연동 토큰')).toHaveTextContent('5명')
  })

  it('MCP 도구 순위와 사용자가 표로 선다', async () => {
    show()
    const tools = await screen.findByRole('table', { name: 'MCP 도구별' })
    const rows = within(tools).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('resolve_property')
    expect(rows[2]).toHaveTextContent('property_coverage')
    expect(within(screen.getByRole('table', { name: 'MCP 사용자별' })).getByText('박연구')).toBeInTheDocument()
  })

  it('많이 본 재료는 그 재료로 가는 링크다', async () => {
    show()
    const link = await screen.findByRole('link', { name: 'M-000001 · SECC_MDOI_1.0' })
    expect(link).toHaveAttribute('href', '/materials/m1')
  })

  it('집계가 쌓이기 전 기간이면 안 센 것이라고 말한다', async () => {
    show()
    expect(await screen.findByText(/2026-10-02 부터 쌓였습니다/)).toBeInTheDocument()
  })

  it('승인 대기가 있으면 계정 관리로 보낸다', async () => {
    show()
    expect(await screen.findByRole('link', { name: /승인 대기 2명/ })).toHaveAttribute(
      'href',
      '/admin/accounts'
    )
  })

  it('기간을 바꾸면 그 기간으로 다시 묻는다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('쓴 사람')
    expect(summary).toHaveBeenLastCalledWith(30)

    await user.click(screen.getByRole('button', { name: '7일' }))

    expect(summary).toHaveBeenLastCalledWith(7)
  })
})
