/**
 * 측정 의뢰 게시판 — **번호·시료·부서·진행률·상태가 한 표에 서고, 범위와 상태로 거른다.**
 *
 *   범위 칩(내가 낸 것·우리 부서가 받은 것·전체)은 서버에 `scope` 로 묻는다
 *   상태 칩은 서버가 준 것으로 선다
 *   진행률은 채택/의뢰 수, 붙었지만 채택 전은 괄호에
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommissionsPage from '@/modules/commissions/CommissionsPage'

const list = vi.fn()
const statuses = vi.fn()

vi.mock('@/modules/commissions/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/commissions/api')>()),
  commissionsApi: {
    list: (...args: unknown[]) => list(...args),
    statuses: () => statuses(),
  },
}))

const row = (over: Record<string, unknown> = {}) => ({
  id: 'c-1',
  seq: 7,
  title: 'SECC 인장 물성',
  status: 'in_progress',
  status_label: '시험 중',
  priority: 'normal',
  priority_label: '보통',
  requester_workspace: { slug: 'metal', name: '금속재료팀' },
  lab_workspace: { slug: 'reliability', name: '신뢰성그룹' },
  sample: { id: 's-1', record_name: 'SECC-1.0-S01', material_id: 'm-1', material_name: 'SECC 1.0t' },
  material_hint: null,
  due_on: '2026-10-15',
  created_at: '2026-09-14T01:00:00Z',
  created_by: '김해석',
  status_at: '2026-09-14T02:00:00Z',
  status_by: '이측정',
  assignee: null,
  item_count: 1,
  progress: { total: 3, linked: 2, done: 1 },
  is_mine: true,
  side: 'requester',
  event_count: 2,
  ...over,
})

const STATUSES = [
  { key: 'draft', label: '작성 중' },
  { key: 'submitted', label: '접수 대기' },
  { key: 'in_progress', label: '시험 중' },
]

async function show(rows: unknown[]) {
  list.mockResolvedValue({ items: rows, total: rows.length, limit: 50, offset: 0 })
  render(
    <MemoryRouter initialEntries={['/commissions']}>
      <CommissionsPage />
    </MemoryRouter>
  )
  await waitFor(() => expect(list).toHaveBeenCalled())
}

describe('측정 의뢰 게시판', () => {
  beforeEach(() => {
    list.mockReset()
    statuses.mockReset()
    statuses.mockResolvedValue(STATUSES)
  })

  it('번호·시료·부서·진행률·상태가 한 줄에 선다', async () => {
    await show([row()])
    const line = (await screen.findByText('SECC 인장 물성')).closest('tr') as HTMLElement
    expect(within(line).getByText('7')).toBeInTheDocument()
    expect(within(line).getByText('SECC-1.0-S01')).toBeInTheDocument()
    expect(within(line).getByText('SECC 1.0t')).toBeInTheDocument()
    expect(within(line).getByText('금속재료팀')).toBeInTheDocument()
    expect(within(line).getByText('신뢰성그룹')).toBeInTheDocument()
    // 채택 1 / 의뢰 3, 붙었지만 채택 전 1.
    expect(within(line).getByText('1/3')).toBeInTheDocument()
    expect(within(line).getByText('(+1)')).toBeInTheDocument()
    expect(within(line).getByText('시험 중')).toBeInTheDocument()
    expect(within(line).getByText('2026-10-15')).toBeInTheDocument()
    expect(within(line).getByText('내 것')).toBeInTheDocument()
  })

  it('범위와 상태 칩은 서버에 그대로 묻는다', async () => {
    await show([row()])
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '우리 부서가 받은 것' }))
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'received' }))
    )
    await user.click(screen.getByRole('button', { name: '접수 대기' }))
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(
        expect.objectContaining({ scope: 'received', status: 'submitted' })
      )
    )
  })

  it('새 재료 의뢰는 시료 자리에 「새 재료」 와 적은 글이 선다', async () => {
    await show([row({ sample: null, material_hint: 'SGARC440 1.2t, 포스코' })])
    const line = (await screen.findByText('SECC 인장 물성')).closest('tr') as HTMLElement
    expect(within(line).getByText('새 재료')).toBeInTheDocument()
    expect(within(line).getByText('SGARC440 1.2t, 포스코')).toBeInTheDocument()
  })

  it('급한 건은 배지가 붙고, 없으면 안내가 선다', async () => {
    await show([row({ priority: 'urgent', priority_label: '급함' })])
    expect(screen.getByText('급함')).toBeInTheDocument()
    list.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '작성 중' }))
    expect(await screen.findByText('거른 조건에 맞는 것이 없습니다.')).toBeInTheDocument()
  })
})
