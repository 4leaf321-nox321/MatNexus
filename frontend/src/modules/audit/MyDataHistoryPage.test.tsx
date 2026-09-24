/**
 * 내 자료 변경 이력 — **내가 등록한 자료에 남이 한 일**(2026-09-25).
 *
 *   누가 · 한 일 · 대상 · 내용          남의 자료 고침은 근거·건수·대상을 사람 말로
 *   열어 볼 수 있는 대상에는 링크       지운 것에는 안 건다 — 누르면 없는 화면이다
 *   내 이름으로 AI 가 한 일              「AI(MCP) 경유」
 *   쪽 넘기기                           서버가 준 전체 수로
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MyDataHistoryPage from '@/modules/audit/MyDataHistoryPage'

const mine = vi.fn()

vi.mock('@/modules/audit/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/audit/api')>()),
  auditApi: { mine: (...args: unknown[]) => mine(...args) },
}))

function entry(over: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    action: 'data.edited_by_other',
    actor_id: 'u2',
    actor_label: '보라',
    target_table: 'materials',
    target_id: 'm1',
    target_label: 'SECC_MDOI_1.0',
    workspace_id: null,
    changes: { basis: '자료 관리자', count: 1 },
    reason: null,
    request_id: 'r1',
    client: '',
    created_at: '2026-09-25T01:00:00Z',
    ...over,
  }
}

function page(items: unknown[], total = items.length) {
  return { items, total, limit: 50, offset: 0 }
}

function show() {
  render(
    <MemoryRouter>
      <MyDataHistoryPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('내 자료 변경 이력', () => {
  it('남이 고친 일을 근거와 함께 사람 말로 적고, 대상은 열어 볼 수 있다', async () => {
    mine.mockResolvedValue(
      page([
        entry(),
        entry({
          id: 'e2',
          target_table: 'specimens',
          target_id: 's1',
          target_label: 'SECC_MDOI_1.0__01_MD_01 외 2건',
          changes: { basis: '편집을 받은 부서(신뢰성그룹)', count: 3, targets: ['A', 'B', 'C'] },
        }),
      ])
    )
    show()
    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1)

    expect(within(rows[0]).getByText('남의 자료 고침')).toBeInTheDocument()
    expect(within(rows[0]).getByText('보라')).toBeInTheDocument()
    expect(within(rows[0]).getByText('자료 관리자')).toBeInTheDocument()
    expect(within(rows[0]).getByText('재료')).toBeInTheDocument()
    expect(within(rows[0]).getByRole('link', { name: 'SECC_MDOI_1.0' })).toHaveAttribute(
      'href',
      '/materials/m1'
    )
    // 일괄은 한 줄 — 몇 건이었고 무엇이었는지가 보인다(「없음 → 없음」 이 아니다).
    expect(within(rows[1]).getByText('3')).toBeInTheDocument()
    expect(within(rows[1]).getByText('A, B, C')).toBeInTheDocument()
    expect(within(rows[1]).getByText('편집을 받은 부서(신뢰성그룹)')).toBeInTheDocument()
    expect(within(rows[1]).queryByText(/없음/)).toBeNull()
  })

  it('지운 대상에는 링크를 걸지 않는다', async () => {
    mine.mockResolvedValue(
      page([entry({ action: 'material.deleted', changes: {}, target_label: '지운 재료' })])
    )
    show()
    const row = within(await screen.findByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('지운 재료')).toBeInTheDocument()
    expect(within(row).queryByRole('link')).toBeNull()
  })

  it('내 이름으로 AI 가 한 일은 그렇게 적는다', async () => {
    mine.mockResolvedValue(
      page([
        entry({
          action: 'values.changed_by_client',
          actor_label: '앨리스',
          client: 'mcp',
          changes: { fields: ['alias'] },
        }),
      ])
    )
    show()
    const row = within(await screen.findByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('AI 가 값 수정')).toBeInTheDocument()
    expect(within(row).getByText('AI(MCP) 경유')).toBeInTheDocument()
  })

  it('없으면 무엇이 여기 남는지 말한다', async () => {
    mine.mockResolvedValue(page([]))
    show()
    expect(await screen.findByText(/다른 사람이 내 자료를 고치거나 지우면/)).toBeInTheDocument()
  })

  it('많으면 쪽으로 넘긴다', async () => {
    const user = userEvent.setup()
    mine.mockResolvedValue(page([entry()], 120))
    show()
    await screen.findByRole('table')
    expect(screen.getByText('1–50 / 120건')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '다음' }))
    await waitFor(() => expect(mine).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }))
  })
})
