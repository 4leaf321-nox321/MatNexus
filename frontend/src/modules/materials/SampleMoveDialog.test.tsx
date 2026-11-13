/**
 * 시료째 고른 재료로 옮기기(2026-11-14, VOC 59) — 무엇이 막히고 어느 카드가 걸리는지는 서버가 말한다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SampleMoveDialog } from '@/modules/materials/SampleMoveDialog'

const movePlan = vi.fn()
const move = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    movePlan: (...args: unknown[]) => movePlan(...args),
    move: (...args: unknown[]) => move(...args),
  },
}))
// 재료 고르기는 그 부품의 시험이 본다 — 여기서는 「골랐다」 만.
vi.mock('@/modules/materials/MaterialPicker', () => ({
  MaterialPicker: ({ onSelect }: { onSelect: (material: { id: string }) => void }) => (
    <button type="button" onClick={() => onSelect({ id: 'm2' })}>
      받을 재료 고르기
    </button>
  ),
}))

const PLAN = {
  specimens: 2,
  test_runs: 3,
  thickness: 1.2,
  thickness_unit: 'mm',
  targets: [
    {
      from_material_id: 'm1',
      from_material_name: 'SECC_MDOI_1.0',
      to_material_id: 'm2',
      to_material_name: 'SECC_EG_1.2',
      exists: true,
      specimens: 2,
      test_runs: 3,
    },
  ],
  samples: [],
  cards: [],
  records: [],
  blocked: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  movePlan.mockResolvedValue(PLAN)
  move.mockResolvedValue({ moved: 2, test_runs: 3 })
})

function show(onDone = vi.fn()) {
  render(
    <SampleMoveDialog open sampleId="s1" sampleName="SECC_MDOI_1.0__01" onClose={() => {}} onDone={onDone} />
  )
  return onDone
}

describe('시료째 고른 재료로', () => {
  it('고르면 계획을 묻고, 옮기면 고른 재료로 보낸다', async () => {
    const user = userEvent.setup()
    const onDone = show()
    expect(screen.getByRole('button', { name: '시료째 옮기기' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '받을 재료 고르기' }))
    expect(await screen.findByText('SECC_EG_1.2')).toBeInTheDocument()
    expect(movePlan).toHaveBeenCalledWith({
      sample_ids: ['s1'],
      target_material_id: 'm2',
      card_actions: {},
    })
    await user.click(screen.getByRole('button', { name: '시료째 옮기기' }))
    await waitFor(() => expect(move).toHaveBeenCalledTimes(1))
    expect(move.mock.calls[0][0]).toMatchObject({ sample_ids: ['s1'], target_material_id: 'm2' })
    expect(onDone).toHaveBeenCalled()
  })

  it('막히면 까닭을 보이고 옮기지 못하게 한다', async () => {
    movePlan.mockResolvedValue({
      ...PLAN,
      specimens: 0,
      test_runs: 0,
      targets: [],
      blocked: ['SECC_MDOI_1.0__01 — 분류가 다른 재료로는 옮기지 않습니다'],
    })
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: '받을 재료 고르기' }))
    expect(await screen.findByText(/분류가 다른 재료로는 옮기지 않습니다/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '시료째 옮기기' })).toBeDisabled()
  })
})
