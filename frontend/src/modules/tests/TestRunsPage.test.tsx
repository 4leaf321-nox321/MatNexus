/**
 * 시험 목록의 **열별 거르개** — 특히 처리, 그리고 「많으면 쳐서 찾는다」.
 *
 * ## 왜 이것만 무나
 *
 * 「진응력을 안 거친 채 채택된 시험」 은 실제로 찾는 물음이다(실측 2026-09-11:
 * 채택된 52건 중 33건). 그런데 그 물음은 **거르개 둘을 겹쳐야** 답이 나오고,
 * 겹치는 규칙이 틀리면 **목록이 늘 0건**이 된다 — 사람은 그것을 「자료가 없다」
 * 로 읽는다. 조용히 틀리는 자리라 시험으로 묶는다.
 *
 *     거친 것 / 안 거친 것    서로 다른 인자로 나간다
 *     둘을 동시에 안 건다      함께 걸면 언제나 0건이다
 *     많으면 쳐서 찾는다       102종을 눈으로 훑게 하지 않는다
 *     적으면 그냥 고른다       넷짜리 목록에 검색칸은 거추장스럽다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TestRunsPage from '@/modules/tests/TestRunsPage'

const runs = vi.fn()
const facets = vi.fn()

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', memberships: [] } }),
  useMaybeAuth: () => ({ user: { id: 'u1', memberships: [] } }),
}))

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    runs: (...args: unknown[]) => runs(...args),
    runFacets: (...args: unknown[]) => facets(...args),
  },
}))

const RUN = {
  id: 'r1',
  record_name: 'SECC_1.0__01__MD_01__TEN_01',
  material_name: 'SECC_1.0',
  material_id: 'm1',
  test_type: '인장',
  test_type_key: 'tensile',
  orientation: 'MD',
  status: 'parsed',
  result_count: 1,
  adopted_result_id: 'p1',
  master_curve_count: 0,
  temperature_step_count: null,
  row_count: 120,
  division: null,
  operator: null,
  registered_by: null,
  conditions: {},
  created_at: '2026-09-01T00:00:00Z',
  specimen_id: 's1',
  seq_no: 1,
  note: null,
  parse_error: null,
  source_filename: 'a.tra',
  source_bytes: 10,
  source_sha256: 'x',
  channels: [],
  warnings: [],
  summary: [],
}

/** 재료는 **일부러 많이 둔다** — 쳐서 좁히는 창이 서는 쪽을 보려는 것이다. */
const MATERIALS = Array.from({ length: 10 }, (_, at) => ({
  key: `m${at + 1}`,
  label: at + 1 === 7 ? 'SPCC_2.3' : `SECC_${at + 1}.0`,
  count: at + 1,
}))

const FACETS = {
  test_types: [{ key: 'tensile', label: '인장', count: 1 }],
  orientations: [],
  registrants: [],
  operators: [],
  testing_groups: [],
  divisions: [],
  statuses: [{ key: 'parsed', label: 'parsed', count: 1 }],
  processing: [
    { key: 'none', label: '처리 안 함', count: 3 },
    { key: 'adopted', label: '채택됨', count: 1 },
  ],
  steps: [
    { key: 'tensile.true_plastic', label: '진응력·진소성변형률', count: 1 },
    { key: 'curve.resample', label: '균등 격자로 재샘플', count: 1 },
  ],
  materials: MATERIALS,
}

function show() {
  render(
    <MemoryRouter>
      <TestRunsPage />
    </MemoryRouter>
  )
}

/** 마지막으로 서버에 보낸 질의. */
function asked(): Record<string, unknown> {
  return (runs.mock.calls.at(-1)?.[0] ?? {}) as Record<string, unknown>
}

beforeEach(() => {
  vi.clearAllMocks()
  runs.mockResolvedValue({ items: [RUN], total: 1, limit: 50, offset: 0 })
  facets.mockResolvedValue(FACETS)
})

describe('처리로 거르기', () => {
  it('처리 단계(안 함·채택됨)를 서버에 묻는다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    await user.selectOptions(screen.getByRole('combobox', { name: '처리 로 거르기' }), 'adopted')

    await waitFor(() => expect(asked().processing).toBe('adopted'))
  })

  it('거친 단계와 안 거친 단계를 다른 인자로 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    // **무리로 집는다.** 두 무리의 줄은 글자가 똑같고 뜻만 다르다 — 차례로
    // 집으면 걸어 둔 값이 칸에 적히는 순간 번호가 밀린다(실제로 밀렸다).
    await user.click(screen.getByRole('button', { name: /처리 단계/ }))
    const did = await screen.findByRole('group', { name: '채택된 결과가 거친 단계' })
    await user.click(within(did).getByRole('button', { name: /진응력/ }))
    await waitFor(() => expect(asked().step).toBe('tensile.true_plastic'))
    expect(asked().step_missing).toBeUndefined()

    await user.click(screen.getByRole('button', { name: /처리 단계/ }))
    const didnt = await screen.findByRole('group', { name: '그 단계를 안 거친 것' })
    await user.click(within(didnt).getByRole('button', { name: /진응력/ }))
    await waitFor(() => expect(asked().step_missing).toBe('tensile.true_plastic'))
    // **둘을 동시에 걸지 않는다.** 함께 걸면 언제나 0건이고, 사람은 그것을
    // 자료가 없는 것으로 읽는다.
    expect(asked().step).toBeUndefined()
  })

  it('채택 전 처리와 「거친 단계」 를 함께 걸지 않는다', async () => {
    // 「거친 단계」 는 **채택된 결과**만 본다. 「처리 안 함」 과 함께 걸면 그
    // 교집합은 언제나 비어 있고, 사람은 그것을 자료가 없는 것으로 읽는다.
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    await user.click(screen.getByRole('button', { name: /처리 단계/ }))
    const did = await screen.findByRole('group', { name: '채택된 결과가 거친 단계' })
    await user.click(within(did).getByRole('button', { name: /진응력/ }))
    await waitFor(() => expect(asked().step).toBe('tensile.true_plastic'))

    await user.selectOptions(screen.getByRole('combobox', { name: '처리 로 거르기' }), 'none')
    await waitFor(() => expect(asked().processing).toBe('none'))
    expect(asked().step).toBeUndefined()
  })
})

describe('많으면 쳐서 찾는다', () => {
  it('재료는 쳐서 좁혀 고르고, 이름이 아니라 식별자로 걸린다', async () => {
    // 이름은 기준정보 개명을 따라 바뀐다 — 걸어 둔 거르개가 옛 이름을 들고
    // 있으면 그 목록은 조용히 0건이 된다.
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    await user.click(screen.getByRole('button', { name: '재료 로 거르기' }))
    await user.type(await screen.findByPlaceholderText('쳐서 좁히기'), 'SPCC')
    // 친 글자에 안 맞는 줄은 사라진다 — 남은 하나를 Enter 로 집는다.
    expect(screen.queryByRole('button', { name: /SECC_1\.0/ })).toBeNull()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(asked().material_id).toBe('m7'))
  })

  it('적은 열에는 검색칸을 안 낸다', async () => {
    // 넷·다섯짜리 목록(처리·상태)에 검색칸을 달면 그것이 거추장스럽다.
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    await user.click(screen.getByRole('button', { name: /처리 단계/ }))
    expect(await screen.findByText('채택된 결과가 거친 단계')).toBeTruthy()
    expect(screen.queryByPlaceholderText('쳐서 좁히기')).toBeNull()
  })
})
