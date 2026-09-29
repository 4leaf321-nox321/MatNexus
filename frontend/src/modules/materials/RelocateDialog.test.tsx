/**
 * 다른 두께로 옮기기 — **무엇을 서버에 묻고, 무엇을 싣나.**
 *
 *   두께를 적으면 계획을 묻는다        화면 단위(mm)를 함께 — 단위 없이 1.2 를 보내면 1.2 m 다
 *   걸린 카드는 코멘트가 기본이다       정리(사용 중지)는 고른 카드만 싣는다
 *   정리 못 하는 카드는 못 고른다       이유를 그 자리에 적는다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LENGTH_UNIT } from '@/modules/materials/api'
import { RelocateDialog } from '@/modules/materials/RelocateDialog'

const relocatePlan = vi.fn()
const relocate = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    relocatePlan: (...args: unknown[]) => relocatePlan(...args),
    relocate: (...args: unknown[]) => relocate(...args),
  },
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
      to_material_id: null,
      to_material_name: 'SECC_MDOI_1.2',
      exists: false,
      specimens: 2,
      test_runs: 3,
    },
  ],
  samples: [
    { sample_id: 's1', sample_name: 'SECC_MDOI_1.0__01', lot_no: 'L1', whole: false, specimens: 2 },
  ],
  cards: [
    {
      id: 'c1',
      label: 'SECC 인장 MD',
      status: 'published',
      material_name: 'SECC_MDOI_1.0',
      test_runs: 2,
      can_deprecate: true,
      reason: null,
    },
    {
      id: 'c2',
      label: 'SECC 인장 초안',
      status: 'draft',
      material_name: 'SECC_MDOI_1.0',
      test_runs: 1,
      can_deprecate: false,
      reason: '이 초안을 고칠 권한이 없습니다',
    },
  ],
  records: ['묶음 「속도별 소성 곡선」 — 구성원 2/3개가 옮겨집니다.'],
  blocked: ['SECC_MDOI_1.0__02__MD_01 — 이미 1.2 mm 재료에 있습니다'],
}

beforeEach(() => {
  vi.clearAllMocks()
  relocatePlan.mockResolvedValue(PLAN)
  relocate.mockResolvedValue({
    moved: 2,
    test_runs: 3,
    created_materials: ['SECC_MDOI_1.2'],
    joined_materials: [],
    split_samples: 1,
    cards_noted: 2,
    cards_deprecated: 1,
    blocked: [],
  })
})

function show(onDone = vi.fn()) {
  render(
    <RelocateDialog open specimenIds={['p1', 'p2']} onClose={() => {}} onDone={onDone} />
  )
  return onDone
}

describe('RelocateDialog', () => {
  it('두께를 적으면 화면 단위와 함께 계획을 묻고, 무엇이 어디로 가는지 보인다', async () => {
    const user = userEvent.setup()
    show()
    await user.type(screen.getByLabelText(`기준 두께 (${LENGTH_UNIT})`), '1.2')

    await waitFor(() => expect(relocatePlan).toHaveBeenCalled())
    expect(relocatePlan.mock.calls.at(-1)?.[0]).toEqual({
      specimen_ids: ['p1', 'p2'],
      spec_thickness: 1.2,
      spec_thickness_unit: LENGTH_UNIT,
      card_actions: {},
    })
    // 그려진 계획을 기다린다 — 옮겨 갈 재료는 서버가 준 것이다.
    expect(await screen.findByText(/없어서 새로 만듭니다/)).toBeInTheDocument()
    expect(screen.getByText(/같은 로트로 시료를 새로 만들어 붙입니다/)).toBeInTheDocument()
    expect(screen.getByText(/이미 1.2 mm 재료에 있습니다/)).toBeInTheDocument()
    // 그 시험을 쓴 묶음은 원 재료에 남는다고 미리 말한다.
    expect(screen.getByText(/구성원 2\/3개가 옮겨집니다/)).toBeInTheDocument()
  })

  it('걸린 카드는 코멘트가 기본이고, 고른 카드만 정리를 싣는다', async () => {
    const user = userEvent.setup()
    const onDone = show()
    await user.type(screen.getByLabelText(`기준 두께 (${LENGTH_UNIT})`), '1.2')

    const published = await screen.findByRole('radiogroup', { name: 'SECC 인장 MD 처리' })
    await user.click(within(published).getByRole('radio', { name: '정리(사용 중지)' }))
    // 정리할 권한이 없는 카드는 고를 수 없고, 까닭이 그 자리에 있다.
    const draft = screen.getByRole('radiogroup', { name: 'SECC 인장 초안 처리' })
    expect(within(draft).getByRole('radio', { name: '정리(사용 중지)' })).toBeDisabled()
    expect(screen.getByText('이 초안을 고칠 권한이 없습니다')).toBeInTheDocument()

    await user.type(screen.getByLabelText('카드에 남길 말(선택)'), '두께 오기')
    await user.click(screen.getByRole('button', { name: '시편 2개 옮기기' }))

    await waitFor(() => expect(relocate).toHaveBeenCalled())
    expect(relocate.mock.calls[0][0]).toEqual({
      specimen_ids: ['p1', 'p2'],
      spec_thickness: 1.2,
      spec_thickness_unit: LENGTH_UNIT,
      card_actions: { c1: 'deprecate' },
      comment: '두께 오기',
    })
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })
})
