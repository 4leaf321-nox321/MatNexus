/**
 * Prony 적합 → 물성 카드.
 *
 * **DMA 는 푸아송비를 재지 않는다.** 그 사실이 화면에서 지켜지는지 본다 —
 * 빈 칸을 0 으로 보내면 그것이 잰 값인지 덱만 봐서는 알 수 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ViscoelasticCardDialog } from '@/modules/viscoelastic/ViscoelasticCardDialog'
import type { PronyFit } from '@/modules/viscoelastic/api'

const createViscoelastic = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: { createViscoelastic: (...args: unknown[]) => createViscoelastic(...args) },
}))

const FIT = {
  id: 'fit-1',
  master_curve_id: 'curve-1',
  equilibrium_pa: 1e7,
  instantaneous_pa: 1e9,
  terms: [
    { modulus_pa: 5e8, relaxation_time_s: 0.1 },
    { modulus_pa: 4e8, relaxation_time_s: 10 },
  ],
  normalized_rmse: 0.02,
  bic: -120,
  at_bound: [],
  candidates: [],
  note: null,
  created_at: '2026-08-23T00:00:00Z',
} as unknown as PronyFit

function show() {
  const onDone = vi.fn()
  render(
    <ViscoelasticCardDialog
      fit={FIT}
      suggestedLabel="점탄성 20.0 °C"
      onClose={() => {}}
      onDone={onDone}
    />
  )
  return onDone
}

beforeEach(() => {
  vi.clearAllMocks()
  createViscoelastic.mockResolvedValue({ id: 'card-1' })
})

describe('점탄성 카드 만들기', () => {
  it('이름을 미리 채워 준다', () => {
    // 같은 재료의 카드가 여럿이면 **어느 온도의 것인지**가 이름에서 보여야 한다.
    show()
    expect(screen.getByLabelText('이름')).toHaveValue('점탄성 20.0 °C')
  })

  it('시편 한 건이라는 사실을 먼저 말한다', () => {
    show()
    expect(screen.getByText(/시편 한 건/)).toBeInTheDocument()
  })

  it('빈 칸은 값 대신 비운 채로 보낸다', async () => {
    // **0 으로 채우면 그것이 잰 값인지 알 수 없다.**
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: '만들기' }))

    await waitFor(() => expect(createViscoelastic).toHaveBeenCalled())
    expect(createViscoelastic.mock.calls[0][0]).toMatchObject({
      prony_fit_id: 'fit-1',
      poisson_ratio: null,
      density: null,
    })
  })

  it('넣은 값은 숫자로 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await user.type(screen.getByLabelText('푸아송비'), '0.45')
    await user.click(screen.getByRole('button', { name: '만들기' }))

    await waitFor(() => expect(createViscoelastic).toHaveBeenCalled())
    expect(createViscoelastic.mock.calls[0][0]).toMatchObject({ poisson_ratio: 0.45 })
  })

  it('이름이 비면 못 만든다', async () => {
    const user = userEvent.setup()
    show()
    await user.clear(screen.getByLabelText('이름'))
    expect(screen.getByRole('button', { name: '만들기' })).toBeDisabled()
  })

  it('DMA 가 안 재는 값이라는 것을 적어 둔다', () => {
    show()
    expect(screen.getByText(/DMA 는 푸아송비와 밀도를 재지 않습니다/)).toBeInTheDocument()
  })
})
