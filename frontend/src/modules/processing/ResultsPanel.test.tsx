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
