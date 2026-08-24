/**
 * 분포 화면.
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   물어보기 전엔 안 돈다      부트스트랩 999회는 물어보지도 않았는데 돌 일이 아니다
 *   실패한 후보도 보인다       안 뜨면 "안 해 봤다" 로 읽힌다
 *   모자람과 안 맞음을 가른다   한 칸에 넣으면 나중에 못 가른다
 *   못 쓴 값을 짚는다          조용히 빼면 "왜 8개죠" 를 답할 수 없다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DistributionPanel } from '@/modules/statistics/DistributionPanel'

const distributable = vi.fn()
const distributions = vi.fn()

vi.mock('@/modules/statistics/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/statistics/api')>()),
  statisticsApi: {
    distributable: (...args: unknown[]) => distributable(...args),
    distributions: (...args: unknown[]) => distributions(...args),
  },
}))

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    key: 'weibull',
    label: '와이블',
    status: 'succeeded',
    reason: null,
    parameters: [9.05, 613.5e6],
    parameter_names: ['shape', 'scale'],
    parameter_labels: ['형상 m', '척도'],
    log_likelihood: -780.1,
    aicc: 1570.2,
    delta_aicc: 0,
    anderson_darling: 0.197,
    p_value: 0.885,
    quantiles: { p05: 441.9e6, p50: 595.0e6, p95: 700.0e6 },
    ...overrides,
  }
}

function report(overrides: Record<string, unknown> = {}) {
  return {
    material_id: 'm1',
    test_type_key: 'tensile',
    orientation: 'MD',
    scalar_key: 'proof_stress',
    scalar_label: '항복강도',
    si_unit: 'Pa',
    count: 12,
    observations: [{ specimen_label: 'A_01', status: 'observed', value: 600e6 }],
    candidates: [candidate()],
    best: 'weibull',
    notes: [],
    ...overrides,
  }
}

function panel() {
  return render(<DistributionPanel materialId="m1" testTypeKey="tensile" orientation="MD" />)
}

beforeEach(() => {
  vi.clearAllMocks()
  distributable.mockResolvedValue([
    { key: 'proof_stress', label: '항복강도', si_unit: 'Pa', count: 12 },
  ])
  distributions.mockResolvedValue(report())
})

describe('분포 화면', () => {
  it('물어보기 전에는 아무것도 안 부른다', async () => {
    // **부트스트랩 999회는 물어보지도 않았는데 돌 일이 아니다.**
    panel()
    expect(distributable).not.toHaveBeenCalled()
    expect(distributions).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '흩어짐의 모양 보기' })).toBeInTheDocument()
  })

  it('항목마다 값이 몇 개인지 미리 보인다', async () => {
    // 눌러 보고 나서 "모자랍니다" 를 받는 것보다 미리 아는 것이 낫다.
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    expect(await screen.findByRole('button', { name: /항복강도/ })).toHaveTextContent('n=12')
  })

  it('고르면 후보를 나란히 보인다', async () => {
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    await waitFor(() => expect(distributions).toHaveBeenCalled())
    expect(screen.getByText('와이블')).toBeInTheDocument()
    expect(screen.getByText('1등')).toBeInTheDocument()
    // **설계가 묻는 것은 파라미터가 아니라 하위 5% 다.**
    expect(screen.getByText('하위 5%')).toBeInTheDocument()
  })

  it('모자란 것과 안 맞는 것을 가른다', async () => {
    // 한 칸에 넣으면 "와이블이 안 맞는 재료" 와 "시편이 모자란 재료" 가 같아 보인다.
    distributions.mockResolvedValue(
      report({
        best: null,
        candidates: [
          candidate({
            status: 'not_eligible',
            reason: '쓸 수 있는 값이 3개입니다 (8개 이상 필요).',
            parameters: [],
            aicc: null,
            delta_aicc: null,
            p_value: null,
            quantiles: {},
          }),
        ],
      })
    )
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    expect(await screen.findByText('표본 모자람')).toBeInTheDocument()
    expect(screen.getByText(/8개 이상 필요/)).toBeInTheDocument()
    // 1등이 없으면 1등 딱지도 없다.
    expect(screen.queryByText('1등')).not.toBeInTheDocument()
  })

  it('실패한 후보도 목록에 남는다', async () => {
    // **안 뜨면 "안 해 봤다" 로 읽힌다.**
    distributions.mockResolvedValue(
      report({
        candidates: [
          candidate(),
          candidate({
            key: 'lognormal',
            label: '로그정규',
            status: 'failed',
            reason: '파라미터가 유한하지 않습니다.',
            delta_aicc: null,
            aicc: null,
          }),
        ],
      })
    )
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    expect(await screen.findByText('로그정규')).toBeInTheDocument()
    expect(screen.getByText('실패')).toBeInTheDocument()
  })

  it('못 쓴 값을 짚는다', async () => {
    // 조용히 빼면 "왜 8개죠" 를 답할 수 없다.
    distributions.mockResolvedValue(
      report({
        count: 1,
        observations: [
          { specimen_label: 'A_01', status: 'observed', value: 600e6 },
          { specimen_label: 'A_02', status: 'missing', value: null },
        ],
      })
    )
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    expect(await screen.findByText(/쓰지 못한 값 1개/)).toBeInTheDocument()
    expect(screen.getByText(/A_02 — 그 시편에 이 항목이 없음/)).toBeInTheDocument()
  })

  it('전부 정상이면 못 쓴 값 표를 안 그린다', async () => {
    // 빈 표는 화면만 먹는다.
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    await waitFor(() => expect(screen.getByText('와이블')).toBeInTheDocument())
    expect(screen.queryByText(/쓰지 못한 값/)).not.toBeInTheDocument()
  })

  it('구별되지 않으면 그 안내를 보인다', async () => {
    distributions.mockResolvedValue(
      report({ notes: ['정규 도 AICc 차이가 2 미만이라 이 데이터로는 구별되지 않습니다.'] })
    )
    panel()
    await userEvent.click(screen.getByRole('button', { name: '흩어짐의 모양 보기' }))
    await userEvent.click(await screen.findByRole('button', { name: /항복강도/ }))
    // 표 아래 설명문도 같은 문구를 쓴다 — 서버가 준 **안내** 쪽을 짚는다.
    expect(await screen.findByText(/^정규 도 AICc 차이가/)).toBeInTheDocument()
  })
})
