/**
 * 합성 곡선 미리보기 — **누를 때 짓고, 실측이 아니라고 말하고, 무엇으로 지었는지 단다.**
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SyntheticCurveSection } from '@/modules/catalog/SyntheticCurveSection'

const syntheticCurve = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: { syntheticCurve: (...args: unknown[]) => syntheticCurve(...args) },
}))

// 차트는 jsdom 에서 크기를 못 잰다 — 무엇을 받았는지만 글자로 뱉는다.
vi.mock('@/modules/tests/CurveChart', () => ({
  CurveChart: ({ points, xLabel, yLabel }: { points: [number, number][]; xLabel: string; yLabel: string }) => (
    <div data-testid="chart">
      {yLabel} / {xLabel} / {points.length}점 / 끝 {points.at(-1)?.[1]}
    </div>
  ),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SyntheticCurveSection', () => {
  it('누를 때 짓고, 모델 · 주의 · 입력과 출처를 단다 — 응력은 화면 단위로', async () => {
    syntheticCurve.mockResolvedValue({
      ok: true,
      model: 'elastic-perfectly plastic',
      note: 'UTS·연신율 정보 부족 — 완전소성 근사.',
      inconsistent: false,
      youngs_modulus: 193e9,
      strain: [0, 0.001, 0.05],
      stress: [0, 193e6, 215e6],
      table_points: 12,
      inputs: [{ item: '항복강도', value_si: 215e6, reference: '벤더 시트', si_unit: 'Pa' }],
      notes: ['사내 물성 항목과 이어지지 않아 못 쓴 문헌 값: 연신율'],
    })
    const user = userEvent.setup()
    render(<SyntheticCurveSection materialId="m-1" />)
    expect(screen.getByRole('heading', { name: '합성 곡선 — 실측이 아니다' })).toBeInTheDocument()
    // 상세를 열 때마다 짓지 않는다.
    expect(syntheticCurve).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /미리보기/ }))
    expect(syntheticCurve).toHaveBeenCalledWith('m-1')
    expect(await screen.findByRole('status')).toHaveTextContent(
      'elastic-perfectly plastic — UTS·연신율 정보 부족 — 완전소성 근사.'
    )
    expect(screen.getByTestId('chart')).toHaveTextContent('공칭 응력 (MPa) / 공칭 변형률 / 3점 / 끝 215')
    expect(screen.getByText(/항복강도 215 MPa — 벤더 시트/)).toBeInTheDocument()
    expect(screen.getByText(/못 쓴 문헌 값: 연신율/)).toBeInTheDocument()
  })

  it('못 지으면 이유를 말한다 — 차트는 서지 않는다', async () => {
    syntheticCurve.mockResolvedValue({
      ok: false,
      why: '곡선을 합성할 스칼라가 모자랍니다 — 탄성계수와 항복강도(또는 인장강도)가 있어야 합니다.',
    })
    const user = userEvent.setup()
    render(<SyntheticCurveSection materialId="m-2" />)
    await user.click(screen.getByRole('button', { name: /미리보기/ }))
    expect(await screen.findByRole('status')).toHaveTextContent('합성할 스칼라가 모자랍니다')
    expect(screen.queryByTestId('chart')).not.toBeInTheDocument()
  })
})
