/**
 * 「결과」 탭의 점탄성 요약 — **건너뛴 것이 드러나는가.**
 *
 * 값 쪽은 「만들고 → 채택하고 → 재료가 가져간다」 인데 점탄성만 다른 탭에서
 * 만들어지고 결과를 여기 안 남긴다. 그래서 통째로 건너뛴 채 재료 화면에서 물성이
 * 비었다고 여기는 일이 생겼다. 이 상자가 그 자리를 메운다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ViscoelasticSummary } from '@/modules/viscoelastic/ViscoelasticSummary'

const masterCurves = vi.fn()

vi.mock('@/modules/viscoelastic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/viscoelastic/api')>()),
  viscoelasticApi: { masterCurves: (...args: unknown[]) => masterCurves(...args) },
}))

const CURVE = {
  id: 'curve-1',
  test_run_id: 'run-1',
  reference_temperature_k: 293.15,
  method: 'wlf',
  parameters: {},
  shifts: [],
  notes: [],
  is_primary: true,
  point_count: 20,
  minimum_frequency_hz: 0.01,
  maximum_frequency_hz: 100,
  source_curve_keys: [],
  created_at: '2026-08-31T00:00:00Z',
}

function show(fitCount = 1) {
  const onGo = vi.fn()
  render(<ViscoelasticSummary testRunId="run-1" fitCount={fitCount} onGo={onGo} />)
  return onGo
}

beforeEach(() => {
  vi.clearAllMocks()
  masterCurves.mockResolvedValue([CURVE])
})

describe('마스터커브가 없을 때', () => {
  it('건너뛴 것을 말하고 만들러 보낸다', async () => {
    // **이 문장이 이 상자의 존재 이유다.** 없으면 「결과」 탭이 빈 것을 보고
    // 이 시험은 할 일이 없다고 여긴다.
    masterCurves.mockResolvedValue([])
    const onGo = show(0)
    expect(await screen.findByText(/아직 마스터커브가 없습니다/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '점탄성 탭에서 만들기' }))
    expect(onGo).toHaveBeenCalled()
  })

  it('어디에 쓰이는지 함께 적는다', async () => {
    masterCurves.mockResolvedValue([])
    show(0)
    // 머리말과 빈 상태 안내에 둘 다 나온다 — 하나라도 있으면 된다.
    expect((await screen.findAllByText(/글로벌 피팅/)).length).toBeGreaterThan(0)
  })
})

describe('마스터커브가 있을 때', () => {
  it('무엇이 있고 어느 것이 대표인지 보여 준다', async () => {
    show(2)
    // 줄에도, 「지금은 … 기준입니다」 안내에도 나온다.
    expect((await screen.findAllByText(/20.*기준/)).length).toBeGreaterThan(0)
    const marks = screen.getAllByText('대표')
    expect(marks.length).toBeGreaterThan(0)
  })

  it('맞춘 계수가 몇 벌인지 적는다', async () => {
    // 마스터커브만 있고 적합이 없으면 아직 카드를 만들 수 없다 — 그 상태가
    // 숫자로 보여야 다음에 할 일을 안다.
    show(0)
    expect(await screen.findByText(/맞춘 계수 0벌/)).toBeInTheDocument()
  })
})
