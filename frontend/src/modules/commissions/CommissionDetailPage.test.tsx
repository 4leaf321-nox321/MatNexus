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
const update = vi.fn()
const types = vi.fn()

vi.mock('@/modules/commissions/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/commissions/api')>()),
  commissionsApi: {
    get: (id: string) => get(id),
    event: (...args: unknown[]) => event(...args),
    linkRun: (...args: unknown[]) => linkRun(...args),
    unlinkRun: (...args: unknown[]) => unlinkRun(...args),
    assign: vi.fn(),
    update: (...args: unknown[]) => update(...args),
    remove: vi.fn(),
    attachSample: (...args: unknown[]) => attachSample(...args),
    resolveItem: (...args: unknown[]) => resolveItem(...args),
  },
}))

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { types: () => types() },
}))

/** 시험 종류 정의 — 조건 칸이 여기서 온다. 늦게 오거나 못 오는 경우를 시험마다 바꾼다. */
const TYPES = [
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
]

beforeEach(() => {
  types.mockReset()
  types.mockResolvedValue(TYPES)
})

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

const specimens = vi.fn()
const createSpecimen = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    specimens: (...args: unknown[]) => specimens(...args),
    createSpecimen: (...args: unknown[]) => createSpecimen(...args),
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
  can_comment: true,
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
  it('제3부서는 읽기만 하고 누구에게 물을지를 본다', async () => {
    // **보기는 전원, 움직이고 말하는 것은 두 쪽**(ADR 0035 3단계). 전에는 제3부서에
    // 「없다」 였다 — 「이 시료를 누가 재 달라고 했나」 를 옆 부서가 물을 데가 없었다.
    await show(
      detail({
        side: 'viewer',
        can_comment: false,
        can_link: false,
        can_assign: false,
        can_resolve: false,
        assignees: [],
        allowed: [],
        allowed_labels: {},
        note_required: [],
      })
    )
    expect(screen.queryByLabelText('댓글 등록')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '말만 남기기' })).not.toBeInTheDocument()
    expect(screen.getByText(/읽기만 됩니다/)).toBeInTheDocument()
  })
})

describe('2단계 마무리 (2026-10-03)', () => {
  beforeEach(() => {
    get.mockReset()
    specimens.mockReset()
    createSpecimen.mockReset()
    specimens.mockResolvedValue([])
    createSpecimen.mockImplementation((_sample: string, body: { orientation: string }) =>
      Promise.resolve({ id: `sp-${body.orientation}`, orientation: body.orientation })
    )
  })

  it('항목의 시험으로 만든 카드가 잇힌다 — 받을 블록이 든 것과 아닌 것을 가른다', async () => {
    await show(
      detail({
        items: [
          item({
            cards: [
              { id: 'k-1', label: 'SECC 탄소성', status: 'draft', material_id: 'm-1', has_deliverable: true },
              { id: 'k-2', label: 'SECC 탄성만', status: 'published', material_id: 'm-1', has_deliverable: false },
            ],
          }),
        ],
      })
    )
    const cards = screen.getByRole('list', { name: '1번 항목의 카드' })
    expect(within(cards).getByRole('link', { name: '카드 SECC 탄소성' })).toHaveAttribute(
      'href',
      '/materials/m-1?tab=cards'
    )
    expect(within(cards).getByText('초안')).toBeInTheDocument()
    expect(within(cards).getByText('받을 블록은 이 카드에 없음')).toBeInTheDocument()
    expect(screen.queryByText(/받을 카드가 아직 없습니다/)).not.toBeInTheDocument()
  })

  it('채택은 됐는데 받을 카드가 아직이면 그렇다고 말한다', async () => {
    await show(detail({ items: [item({ cards: [] })] }))
    expect(screen.getByText(/받을 카드가 아직 없습니다/)).toBeInTheDocument()
  })

  it('시편 만들기 — 수량을 방향에 나눈 안을 고쳐서 하나씩 만든다', async () => {
    const user = userEvent.setup()
    specimens.mockResolvedValue([{ id: 'old', orientation: 'MD' }])
    await show(detail())
    await user.click(screen.getByRole('button', { name: /시편 만들기/ }))
    const dialog = await screen.findByRole('dialog')
    // 수량 3 을 MD · TD 에 — 나머지는 앞 방향부터.
    expect(within(dialog).getByLabelText('MD 시편 수')).toHaveValue(2)
    expect(within(dialog).getByLabelText('TD 시편 수')).toHaveValue(1)
    expect(await within(dialog).findByText('이 시료에 이미 1개')).toBeInTheDocument()

    await user.clear(within(dialog).getByLabelText('TD 시편 수'))
    await user.type(within(dialog).getByLabelText('TD 시편 수'), '2')
    await user.click(within(dialog).getByRole('button', { name: '시편 4개 만들기' }))

    await waitFor(() => expect(createSpecimen).toHaveBeenCalledTimes(4))
    expect(createSpecimen.mock.calls.map((call) => (call[1] as { orientation: string }).orientation)).toEqual([
      'MD',
      'MD',
      'TD',
      'TD',
    ])
    expect(await screen.findByText(/시편 4개를 만들었습니다/)).toBeInTheDocument()
  })

  it('여러 파일은 일괄 등록으로 — 시료 · 의뢰 · 항목을 실어 보내고, 의뢰의 시험 목록으로도 간다', async () => {
    await show(detail())
    expect(screen.getByRole('link', { name: /여러 파일 한꺼번에/ })).toHaveAttribute(
      'href',
      '/tests/upload?material=m-1&sample=s-1&commission=c-1&item=i-1'
    )
    expect(screen.getByRole('link', { name: /이 의뢰의 시험 목록/ })).toHaveAttribute(
      'href',
      '/tests?commission=c-1'
    )
  })
})

/**
 * 의뢰 편집 — 항목은 **통째로 갈아 끼운다.** 시험 종류 정의를 못 읽은 채 열면 조건 칸을 그릴
 * 수 없어, 전에는 조건을 버린 항목이 그대로 저장됐다 — 제목만 고쳐도 모든 항목의 조건이
 * 지워졌다(2026-10-04).
 */
describe('의뢰 편집 — 시험 종류를 못 읽었을 때', () => {
  beforeEach(() => {
    get.mockReset()
    update.mockReset()
    update.mockResolvedValue(detail())
  })

  async function openEdit() {
    const user = userEvent.setup()
    await show(detail({ can_edit: true }))
    await user.click(screen.getByRole('button', { name: '편집' }))
    const dialog = await screen.findByRole('dialog')
    return { user, dialog }
  }

  it('못 읽어도 제목만 고치면 항목 조건은 저장된 값 그대로 간다', async () => {
    types.mockRejectedValue(new Error('시험 종류를 못 읽었습니다'))
    const { user, dialog } = await openEdit()
    expect(await within(dialog).findByText(/조건 정의를 못 읽어/)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('제목'), ' (수정)')
    await user.click(within(dialog).getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, body] = update.mock.calls[0] as [string, { items: Record<string, unknown>[] }]
    // 저장된 SI 를 단위 없이 — 서버는 정의의 SI 로 읽으므로 값이 그대로 남는다.
    expect(body.items[0]).toMatchObject({
      test_type_key: 'tensile',
      conditions: { temperature: 298.15, speed_elastic: 10 / 60000 },
      condition_units: {},
    })
  })

  it('늦게 오면 그때 조건 칸을 채우고, 화면 단위로 보낸다', async () => {
    let arrive: (value: unknown) => void = () => {}
    types.mockReturnValue(new Promise((resolve) => (arrive = resolve)))
    const { user, dialog } = await openEdit()
    arrive(TYPES)

    const temperature = await within(dialog).findByLabelText(/온도/)
    await waitFor(() => expect(Number((temperature as HTMLInputElement).value)).toBeCloseTo(25))
    await user.click(within(dialog).getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, body] = update.mock.calls[0] as [
      string,
      { items: { conditions: Record<string, number>; condition_units: Record<string, string> }[] },
    ]
    expect(body.items[0].conditions.temperature).toBeCloseTo(25)
    expect(body.items[0].conditions.speed_elastic).toBeCloseTo(10)
    expect(body.items[0].condition_units).toMatchObject({ speed_elastic: 'mm/min' })
  })
})
