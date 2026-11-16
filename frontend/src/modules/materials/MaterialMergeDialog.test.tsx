/**
 * 재료 합치기(2026-11-17, VOC 59) — 무엇이 어디로 가는지 · 어느 값이 다른지 · 무엇이 막는지는 서버가
 * 센다. 창은 그것을 그대로 보이고, 막힌 것이 있으면 합치지 않는다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MaterialMergeDialog } from '@/modules/materials/MaterialMergeDialog'

const mergePlan = vi.fn()
const merge = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    mergePlan: (...args: unknown[]) => mergePlan(...args),
    merge: (...args: unknown[]) => merge(...args),
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
  source_id: 'm1',
  source_name: 'SECC_MDOI_1.0',
  target_id: 'm2',
  target_name: 'SECC_EG_1.0',
  samples: 2,
  specimens: 1,
  test_runs: 3,
  cards: 1,
  groups: 0,
  ensembles: 0,
  parameter_sets: 0,
  catalog_link: true,
  workbench_items: 0,
  bom_aliases: 0,
  parts: 0,
  taken: ['밀도 7850 kg/m³', '선언 물성 「비열」'],
  kept: ['푸아송비: 받는 재료 0.3 유지(합칠 재료 0.29)'],
  left: [],
  blocked: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  mergePlan.mockResolvedValue(PLAN)
  merge.mockResolvedValue({ ...PLAN, merged: true })
})

function show(onDone = vi.fn()) {
  render(
    <MaterialMergeDialog
      open
      materialId="m1"
      materialName="SECC_MDOI_1.0"
      onClose={() => {}}
      onDone={onDone}
    />
  )
  return onDone
}

describe('재료 합치기', () => {
  it('옮기는 것 · 가져오는 값 · 다른 값을 보이고 합친다', async () => {
    const onDone = show()
    await userEvent.click(screen.getByRole('button', { name: '받을 재료 고르기' }))
    // 계획이 그려진 것을 기다린다 — 틀보다 데이터로.
    const moving = await screen.findByRole('region', { name: '옮기는 것' })
    expect(within(moving).getByText('시료 2개(시편 1개 · 시험 3건)')).toBeInTheDocument()
    expect(within(moving).getByText('카드 1장')).toBeInTheDocument()
    expect(within(moving).getByText('문헌 연결')).toBeInTheDocument()
    expect(within(moving).queryByText(/묶음 기록/)).not.toBeInTheDocument()
    expect(screen.getByText('선언 물성 「비열」')).toBeInTheDocument()
    const kept = screen.getByRole('region', { name: '값이 달라 받는 재료의 것을 두는 칸' })
    expect(within(kept).getByText(/푸아송비: 받는 재료 0.3 유지/)).toBeInTheDocument()
    expect(mergePlan).toHaveBeenCalledWith('m1', 'm2')

    await userEvent.type(screen.getByLabelText('합치기 코멘트'), '두 번 등록함')
    await userEvent.click(screen.getByRole('button', { name: '합치기' }))
    await waitFor(() => expect(merge).toHaveBeenCalledWith('m1', 'm2', '두 번 등록함'))
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ merged: true, target_id: 'm2' }))
  })

  it('막힌 까닭이 있으면 보이고 합치지 않는다', async () => {
    mergePlan.mockResolvedValue({
      ...PLAN,
      blocked: ['분류가 다른 재료는 합치지 않습니다(Metal · Steel · SECC → Metal · Steel · SPCC)'],
    })
    show()
    await userEvent.click(screen.getByRole('button', { name: '받을 재료 고르기' }))
    const why = await screen.findByRole('region', { name: '합칠 수 없는 까닭' })
    expect(within(why).getByText(/분류가 다른 재료/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '합치기' })).toBeDisabled()
  })
})
