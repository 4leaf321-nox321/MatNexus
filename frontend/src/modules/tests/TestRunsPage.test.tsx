/**
 * 시험 목록의 **열별 거르개** — 특히 처리.
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
 *     거르면 첫 쪽으로         2쪽을 보다 거르면 빈 쪽이 뜬다
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
  materials: [{ key: 'm1', label: 'SECC_1.0', count: 1 }],
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

    await user.click(screen.getByRole('button', { name: /처리/ }))
    await user.click(await screen.findByRole('button', { name: /채택됨/ }))

    await waitFor(() => expect(asked().processing).toBe('adopted'))
  })

  it('거친 단계와 안 거친 단계를 다른 인자로 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    // **무리로 집는다.** 두 무리의 줄은 글자가 똑같고 뜻만 다르다 — 차례로
    // 집으면 걸어 둔 값이 단추에 배지로 붙는 순간 번호가 밀린다(실제로 밀렸다).
    await user.click(screen.getByRole('button', { name: /단계/ }))
    const did = await screen.findByRole('group', { name: '채택된 결과가 거친 단계' })
    await user.click(within(did).getByRole('button', { name: /진응력/ }))
    await waitFor(() => expect(asked().step).toBe('tensile.true_plastic'))
    expect(asked().step_missing).toBeUndefined()

    await user.click(screen.getByRole('button', { name: /단계/ }))
    const didnt = await screen.findByRole('group', { name: '그 단계를 안 거친 것' })
    await user.click(within(didnt).getByRole('button', { name: /진응력/ }))
    await waitFor(() => expect(asked().step_missing).toBe('tensile.true_plastic'))
    // **둘을 동시에 걸지 않는다.** 함께 걸면 언제나 0건이고, 사람은 그것을
    // 자료가 없는 것으로 읽는다.
    expect(asked().step).toBeUndefined()
  })

  it('재료는 이름이 아니라 식별자로 거른다', async () => {
    // 이름은 기준정보 개명을 따라 바뀐다 — 걸어 둔 거르개가 옛 이름을 들고
    // 있으면 그 목록은 조용히 0건이 된다.
    const user = userEvent.setup()
    show()
    await screen.findByText(/SECC_1.0__01__MD_01__TEN_01/)

    await user.click(screen.getByRole('button', { name: /재료/ }))
    await user.click(await screen.findByRole('button', { name: /SECC_1\.0/ }))

    await waitFor(() => expect(asked().material_id).toBe('m1'))
  })
})
