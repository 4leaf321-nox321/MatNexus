/**
 * 측정 의뢰 한 건 — **단추는 서버가 말한 것만 선다.**
 *
 *   `allowed` 에 있는 것만 단추다            받는 쪽과 낸 사람이 다르고 상태마다 다르다
 *   말이 필요한 곳은 말 없이 안 눌린다        「접수」 만 찍힌 건은 언제쯤인지 모른다
 *   항목마다 붙은 시험과 채택 수가 보인다     조건은 입력 단위로 되돌려 보인다
 *   시험 붙이기는 `can_link` 일 때만, 후보는 서버가 골라 준 것
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommissionDetailPage from '@/modules/commissions/CommissionDetailPage'

const get = vi.fn()
const event = vi.fn()
const linkRun = vi.fn()
const unlinkRun = vi.fn()
const attachSample = vi.fn()
const resolveItem = vi.fn()

vi.mock('@/modules/commissions/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/commissions/api')>()),
  commissionsApi: {
    get: (id: string) => get(id),
    event: (...args: unknown[]) => event(...args),
    linkRun: (...args: unknown[]) => linkRun(...args),
    unlinkRun: (...args: unknown[]) => unlinkRun(...args),
    assign: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    attachSample: (...args: unknown[]) => attachSample(...args),
    resolveItem: (...args: unknown[]) => resolveItem(...args),
  },
}))

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () =>
      Promise.resolve([
        {
          key: 'tensile',
          label: '인장시험',
          abbr: 'TEN',
          conditions: [
            {
              key: 'temperature',
              label: '온도',
              value_type: 'number',
              dimension: 'temperature',
              si_unit: 'K',
              choices: null,
              is_required: false,
              sort_order: 0,
            },
            {
              key: 'speed_elastic',
              label: '탄성 구간 속도',
              value_type: 'number',
              dimension: 'velocity',
              si_unit: 'm/s',
              choices: null,
              is_required: false,
              sort_order: 1,
            },
          ],
          channels: [],
        },
      ]),
  },
}))

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    blocks: () =>
      Promise.resolve([
        { key: 'elastic', label: '탄성', help: '', produces: [], rows: [], kind_priority: null },
        { key: 'hardening', label: '경화식', help: '', produces: [], rows: [], kind_priority: 10 },
      ]),
  },
}))

vi.mock('@/modules/workspaces/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workspaces/api')>()),
  workspacesApi: { options: () => Promise.resolve([]) },
}))

const run = (over: Record<string, unknown> = {}) => ({
  id: 'r-1',
  record_name: 'SECC-1.0-S01-MD-01-TEN-01',
  status: 'parsed',
  adopted: true,
  specimen_name: 'SECC-1.0-S01-MD-01',
  tested_at: null,
  ...over,
})

const item = (over: Record<string, unknown> = {}) => ({
  id: 'i-1',
  position: 0,
  test_type_key: 'tensile',
  test_type_label: '인장시험',
  property_hint: null,
  conditions: { temperature: 298.15, speed_elastic: 10 / 60000 },
  input_units: { temperature: 'degC', speed_elastic: 'mm/min' },
  orientations: ['MD', 'TD'],
  count: 3,
  deliverable: 'hardening',
  note: null,
  runs: [run(), run({ id: 'r-2', record_name: 'SECC-1.0-S01-TD-01-TEN-01', adopted: false })],
  done: 1,
  candidates: [],
  ...over,
})

const detail = (over: Record<string, unknown> = {}) => ({
  id: 'c-1',
  seq: 7,
  title: 'SECC 인장 물성',
  purpose: '성형 해석용 탄소성 카드',
  sample_plan: '원판 3장',
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
  assignee: { id: 'u-2', name: '박측정' },
  item_count: 1,
  progress: { total: 3, linked: 2, done: 1 },
  is_mine: false,
  side: 'lab',
  event_count: 1,
  items: [item()],
  events: [
    {
      id: 'e-1',
      at: '2026-09-14T01:00:00Z',
      by: '김해석',
      from_status: null,
      to_status: 'submitted',
      to_status_label: '접수 대기',
      note: null,
    },
    {
      id: 'e-2',
      at: '2026-09-14T02:00:00Z',
      by: '이측정',
      from_status: 'submitted',
      to_status: 'accepted',
      to_status_label: '접수',
      note: '10월 첫 주',
    },
  ],
  allowed: ['delivered', 'on_hold'],
  allowed_labels: { delivered: '결과 전달', on_hold: '보류' },
  note_required: ['delivered', 'on_hold'],
  can_edit: false,
  can_link: true,
  can_assign: true,
  can_resolve: true,
  can_delete: false,
  assignees: [{ id: 'u-2', name: '박측정' }],
  ...over,
})

async function show(body: unknown) {
  get.mockResolvedValue(body)
  render(
    <MemoryRouter initialEntries={['/commissions/c-1']}>
      <Routes>
        <Route path="/commissions/:id" element={<CommissionDetailPage />} />
      </Routes>
    </MemoryRouter>
  )
  await screen.findByText('SECC 인장 물성')
}

describe('측정 의뢰 상세', () => {
  beforeEach(() => {
    get.mockReset()
    event.mockReset()
    linkRun.mockReset()
    unlinkRun.mockReset()
    attachSample.mockReset()
    resolveItem.mockReset()
  })

  it('항목의 조건은 입력 단위로, 시험은 채택 여부와 함께 보인다', async () => {
    await show(detail())
    const card = await screen.findByLabelText('1번 항목')
    expect(within(card).getByText('인장시험')).toBeInTheDocument()
    expect(within(card).getByText('MD·TD')).toBeInTheDocument()
    expect(within(card).getByText('× 3')).toBeInTheDocument()
    expect(within(card).getByText('탄소성 카드')).toBeInTheDocument()
    expect(within(card).getByText('채택 1/3')).toBeInTheDocument()
    // 298.15 K → 25 °C, 10/60000 m/s → 10 mm/min.
    await waitFor(() =>
      expect(within(card).getByText(/온도 25 °C · 탄성 구간 속도 10 mm\/min/)).toBeInTheDocument()
    )
    const runs = within(card).getByLabelText('1번 항목의 시험')
    expect(within(runs).getByText('SECC-1.0-S01-MD-01-TEN-01')).toBeInTheDocument()
    expect(within(runs).getByText('채택')).toBeInTheDocument()
    expect(within(runs).getByText('채택 전')).toBeInTheDocument()
  })

  it('말이 필요한 단추는 말 없이 안 눌리고, 적으면 상태와 함께 보낸다', async () => {
    await show(detail())
    const deliver = screen.getByRole('button', { name: '결과 전달' })
    expect(deliver).toBeDisabled()
    expect(screen.queryByRole('button', { name: '접수' })).not.toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('댓글 등록'), '재료 상세 > CAE 카드')
    expect(deliver).toBeEnabled()
    event.mockResolvedValue(detail({ status: 'delivered', status_label: '결과 전달' }))
    await user.click(deliver)
    await waitFor(() =>
      expect(event).toHaveBeenCalledWith('c-1', {
        status: 'delivered',
        note: '재료 상세 > CAE 카드',
      })
    )
  })

  it('받는 쪽은 후보에서 골라 붙이고, 낸 쪽에는 붙이기가 없다', async () => {
    await show(
      detail({
        items: [item({ runs: [], done: 0, candidates: [run({ id: 'r-9', record_name: '후보-01', adopted: false })] })],
      })
    )
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('1번 항목에 붙일 시험'), 'r-9')
    linkRun.mockResolvedValue(detail())
    await user.click(screen.getByRole('button', { name: '붙이기' }))
    await waitFor(() => expect(linkRun).toHaveBeenCalledWith('c-1', 'i-1', 'r-9'))
  })

  it('종류 미정 항목은 물성 이름으로 서고, 받는 쪽이 종류를 정한다 — 붙이기는 그 뒤', async () => {
    await show(
      detail({
        items: [
          item({
            test_type_key: null,
            test_type_label: null,
            property_hint: '80 °C 탄성계수',
            conditions: {},
            input_units: {},
            runs: [],
            done: 0,
            candidates: [],
          }),
        ],
      })
    )
    const card = await screen.findByLabelText('1번 항목')
    expect(within(card).getByText('시험 종류 미정')).toBeInTheDocument()
    expect(within(card).getByText('80 °C 탄성계수')).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: '붙이기' })).not.toBeInTheDocument()
    const user = userEvent.setup()
    const pick = await within(card).findByLabelText('1번 항목의 시험 종류 정하기')
    await user.selectOptions(pick, 'tensile')
    resolveItem.mockResolvedValue(detail())
    await user.click(within(card).getByRole('button', { name: '종류 정하기' }))
    await waitFor(() => expect(resolveItem).toHaveBeenCalledWith('c-1', 'i-1', 'tensile'))
  })

  it('새 재료 의뢰는 적은 글이 서고, 받는 쪽에만 「시료 잇기」 가 있다', async () => {
    await show(detail({ sample: null, material_hint: 'SGARC440 1.2t, 포스코' }))
    expect(screen.getByText('새 재료 — 시료 미등록')).toBeInTheDocument()
    expect(screen.getByText('SGARC440 1.2t, 포스코')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '시료 잇기' })).toBeInTheDocument()
    // 시료가 없으면 항목에 붙이기도 없다.
    expect(screen.queryByRole('button', { name: '붙이기' })).not.toBeInTheDocument()
  })

  it('낸 쪽 화면에는 붙이기·담당자 선택이 없고 이력이 시간순으로 흐른다', async () => {
    await show(
      detail({
        side: 'requester',
        can_link: false,
        can_assign: false,
        can_resolve: false,
        assignees: [],
        allowed: [],
        allowed_labels: {},
        note_required: [],
      })
    )
    expect(screen.queryByRole('button', { name: '붙이기' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('담당자')).not.toBeInTheDocument()
    expect(screen.getByText('박측정')).toBeInTheDocument()
    const timeline = screen.getByLabelText('이력')
    const rows = within(timeline).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('등록 · 접수 대기')).toBeInTheDocument()
    expect(within(rows[1]).getByText('접수 로 옮김')).toBeInTheDocument()
    expect(within(rows[1]).getByText('10월 첫 주')).toBeInTheDocument()
  })
})
