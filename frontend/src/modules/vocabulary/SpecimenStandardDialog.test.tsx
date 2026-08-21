/**
 * 시편 규격 치수 — **칸을 화면이 정하지 않는다.**
 *
 * 인장 규격에는 어깨 반경이 있고 DMA 규격에는 지지 간격이 있다. 그 목록을 화면에
 * 적으면 시험 종류를 추가할 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 *
 * 그리고 **저장은 SI, 화면은 mm** 다. 규격서가 mm 로 적혀 있는데 `0.025` 를 치라고
 * 하면 누군가 `25` 를 치고, 그러면 변형률이 1000배 틀린다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenStandardDialog } from '@/modules/vocabulary/SpecimenStandardDialog'
import type { Term } from '@/modules/vocabulary/api'

const kinds = vi.fn()
const specimenFields = vi.fn()
const update = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    kinds: (...args: unknown[]) => kinds(...args),
    specimenFields: (...args: unknown[]) => specimenFields(...args),
    update: (...args: unknown[]) => update(...args),
  },
}))

const field = (
  key: string,
  label: string,
  required = false
): Record<string, unknown> => ({
  key,
  label,
  dimension: 'length',
  si_unit: 'm',
  is_required: required,
  help: null,
  sort_order: 0,
})

const TENSILE = [
  field('gauge_length', '게이지 길이', true),
  field('width', '평행부 폭', true),
  field('shoulder_radius', '어깨 반경'),
]
const DMA = [field('free_length', '자유 길이', true), field('span', '지지 간격')]

const TERM: Term = {
  id: 'term-1',
  value: 'ASTM E8 subsize',
  parent_value: null,
  usage_count: 3,
  status: 'active',
  kind: 'tensile',
  kind_label: '인장시험',
  // **저장은 SI 다** — 25 mm 는 0.025 m 로 담긴다.
  attributes: { gauge_length: 0.025, width: 0.006 },
} as Term

function show(term: Term = TERM) {
  return render(
    <SpecimenStandardDialog slug="specimen_standard" term={term} onClose={vi.fn()} onSaved={vi.fn()} />
  )
}

describe('시편 규격 치수', () => {
  beforeEach(() => {
    kinds.mockResolvedValue([
      { key: 'tensile', label: '인장시험' },
      { key: 'dma_sweep', label: 'DMA 스윕' },
    ])
    specimenFields.mockImplementation((_slug: string, kind: string) =>
      Promise.resolve(kind === 'tensile' ? TENSILE : DMA)
    )
    update.mockReset()
    update.mockResolvedValue(TERM)
  })

  it('종류가 정한 칸이 뜬다 — 목록을 화면이 갖고 있지 않다', async () => {
    show()
    expect(await screen.findByLabelText('게이지 길이')).toBeInTheDocument()
    expect(screen.getByLabelText('어깨 반경')).toBeInTheDocument()
    // DMA 의 칸은 여기 없다.
    expect(screen.queryByLabelText('지지 간격')).not.toBeInTheDocument()
  })

  it('저장된 SI 를 화면 단위로 보여 준다', async () => {
    show()
    // 0.025 m 를 25 로 보여 준다. `0.025` 를 그대로 띄우면 아무도 못 읽는다.
    await waitFor(() => expect(screen.getByLabelText('게이지 길이')).toHaveValue('25'))
    expect(screen.getByLabelText('평행부 폭')).toHaveValue('6')
  })

  it('종류를 바꾸면 칸이 통째로 바뀐다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('게이지 길이')

    await user.click(screen.getByRole('button', { name: 'DMA 스윕' }))

    expect(await screen.findByLabelText('자유 길이')).toBeInTheDocument()
    // **예전 종류의 값을 들고 넘어가지 않는다** — 서버도 그것을 거절한다.
    expect(screen.queryByLabelText('게이지 길이')).not.toBeInTheDocument()
    expect(screen.getByLabelText('자유 길이')).toHaveValue('')
  })

  it('입력한 mm 를 SI 로 바꿔 보낸다', async () => {
    const user = userEvent.setup()
    show()
    const shoulder = await screen.findByLabelText('어깨 반경')
    await user.type(shoulder, '5')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    expect(body.kind).toBe('tensile')
    // 5 mm → 0.005 m
    expect(body.attributes.shoulder_radius).toBeCloseTo(0.005, 9)
    expect(body.attributes.gauge_length).toBeCloseTo(0.025, 9)
  })

  it('빈 칸은 안 보낸다 — 0 이 아니라 없는 것이다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('어깨 반경')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    expect('shoulder_radius' in body.attributes).toBe(false)
  })

  it('종류가 없으면 칸 대신 무엇을 하면 되는지 말한다', async () => {
    show({ ...TERM, kind: null, kind_label: null, attributes: {} } as Term)
    expect(await screen.findByText(/종류를 고르면/)).toBeInTheDocument()
  })
})
