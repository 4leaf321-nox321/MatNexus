/**
 * 처리 결과 — **채택 직전에 곡선과 숫자를 함께 본다.**
 *
 * 채택은 「이 곡선을 이 시험의 물성으로 삼는다」 는 결정이다. 그러니 그 자리에서
 * 하는 질문은 하나다 — **「이 곡선에서 이 값이 나오는 게 맞나」.** 곡선과 스칼라가
 * 세로로 쌓여 있으면 곡선을 보고 스크롤을 내려 숫자를 보고 다시 올라와야 하고,
 * 그 왕복 중에 둘을 나란히 견주지 못한다.
 *
 * 그래서 무는 자리를 「두 열이다」(그건 화면에서 눈으로 본다) 가 아니라
 * **「펼치면 둘이 함께 뜬다」** 에 둔다 — 배치를 고치다 한쪽을 떨어뜨리는 것이
 * 실제로 일어나는 사고이고(이 배치 작업이 곡선을 다른 자리로 옮겼다), jsdom 이
 * 잡을 수 있는 것도 그것이다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ResultsPanel } from '@/modules/processing/ResultsPanel'

const results = vi.fn()
const curve = vi.fn()
const removeResult = vi.fn()

vi.mock('@/modules/processing/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/processing/api')>('@/modules/processing/api')
  return {
    ...actual,
    processingApi: {
      results: (...args: unknown[]) => results(...args),
      curve: (...args: unknown[]) => curve(...args),
      adopt: vi.fn(),
      unadopt: vi.fn(),
      removeResult: (...args: unknown[]) => removeResult(...args),
    },
  }
})

const RESULT = {
  id: 'r1',
  created_at: '2026-08-30T01:00:00Z',
  created_by: '홍길동',
  is_adopted: false,
  recipe_key: null,
  recipe_label: null,
  scalars: [
    {
      key: 'tensile_strength',
      label: '인장강도',
      value: 3.1e8,
      si_unit: 'Pa',
      dimension: 'stress',
    },
  ],
  stages: [{ plugin: 'tensile.strength', label: '인장강도', version: 1, notes: [] }],
  steps: [{ plugin: 'tensile.strength', options: {} }],
  row_count: 2,
  columns: ['strain', 'stress'],
}

beforeEach(() => {
  vi.clearAllMocks()
  results.mockResolvedValue([RESULT])
  curve.mockResolvedValue({
    points: [
      [0, 0],
      [0.01, 3.1e8],
    ],
    returned: 2,
    row_count: 2,
    columns: ['strain', 'stress'],
    units: { strain: '1', stress: 'Pa' },
    x: 'strain',
    y: 'stress',
  })
})

describe('진응력이 없을 때', () => {
  it('하나도 없으면 채택하기 전에 말한다', async () => {
    // 실측(2026-09-11): 채택된 시험 52건 중 33건이 진응력 없이 채택돼 있었다.
    // 그 사실은 세 화면 건너 카드 탭에서야 드러나고, 그때는 다시 처리하는 것
    // 말고 방법이 없다(결과는 불변이다).
    results.mockResolvedValue([RESULT])
    render(<ResultsPanel testRunId="t1" />)
    expect(
      await screen.findByText(/진응력 열을 가진 결과가 하나도 없습니다/)
    ).toBeInTheDocument()
  })

  it('있으면 그 말을 안 한다', async () => {
    // 늘 뜨는 경고는 아무도 안 읽는다.
    results.mockResolvedValue([{ ...RESULT, columns: ['strain', 'stress', 'stress_true'] }])
    render(<ResultsPanel testRunId="t1" />)
    await screen.findByRole('button', { name: /채택/ })
    expect(screen.queryByText(/진응력 열을 가진 결과가 하나도 없습니다/)).toBeNull()
  })
})

describe('시도 지우기', () => {
  // 지울 길이 없어서 잘못 돌린 것까지 영원히 남았다(2026-09-11 지적).
  it('확인을 거쳐 지운다', async () => {
    const user = userEvent.setup()
    removeResult.mockResolvedValue(undefined)
    render(<ResultsPanel testRunId="t1" />)

    await user.click(await screen.findByRole('button', { name: '이 결과 삭제' }))
    // **무엇이 사라지는지 적는다.** 결과는 되살릴 데가 없다.
    expect(
      await screen.findByRole('heading', { name: '이 처리 결과를 지울까요?' })
    ).toBeInTheDocument()
    expect(screen.getByText(/휴지통이 없습니다/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(removeResult).toHaveBeenCalledWith('r1'))
  })

  it('채택된 것에는 단추가 없다', async () => {
    // 서버도 막지만, 누를 수 있게 두면 눌러 보고 거절당한 뒤에야 규칙을 안다.
    results.mockResolvedValue([{ ...RESULT, is_adopted: true }])
    render(<ResultsPanel testRunId="t1" />)

    expect(await screen.findByRole('button', { name: '채택 거두기' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '이 결과 삭제' })).toBeNull()
  })

  it('막히면 그 이유가 보인다', async () => {
    // 반복 시편 통계가 근거로 싣고 있으면 서버가 409 로 막는다 — 그 말이
    // 화면에 안 뜨면 사람은 단추가 고장 난 줄 안다.
    const user = userEvent.setup()
    removeResult.mockRejectedValue(new Error('반복 시편 통계 2건이 이 결과를 근거로 싣고 있어'))
    render(<ResultsPanel testRunId="t1" />)

    await user.click(await screen.findByRole('button', { name: '이 결과 삭제' }))
    await user.click(screen.getByRole('button', { name: '삭제' }))
    expect(await screen.findByText(/반복 시편 통계 2건/)).toBeInTheDocument()
  })
})

describe('결과 펼치기', () => {
  it('곡선과 요약값이 함께 뜬다', async () => {
    // **둘 중 하나만 뜨면 채택을 눈감고 누르게 된다.**
    const user = userEvent.setup()
    render(<ResultsPanel testRunId="run-1" />)

    await user.click(await screen.findByRole('button', { name: '펼치기' }))
    await waitFor(() => expect(curve).toHaveBeenCalledWith('r1', undefined))
    // 스칼라 칸과 단계 목록 둘 다 이 이름을 쓴다 — 하나만 세지 않는다.
    expect(screen.getAllByText('인장강도').length).toBeGreaterThan(0)
  })
})
